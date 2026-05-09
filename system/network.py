# MIT License
# 
# Copyright (c) 2026 Neo Östlund Zetterberg
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

import asyncio
import struct
import msgpack
import websockets
from websockets.exceptions import ConnectionClosed

class Event:
    __slots__ = ("type", "tick", "data", "conn")

    def __init__(self, type, tick, data, conn=None):
        self.type = type
        self.tick = tick
        self.data = data
        self.conn = conn


def encode_message(msg_type, tick, **data):
    payload = {"type": msg_type, "tick": tick, "data": data}
    raw = msgpack.packb(payload, use_bin_type=True)
    return struct.pack("!I", len(raw)) + raw


def _pack_message(msg_type, tick, **data):
    """Return the raw msgpack bytes without the TCP length-prefix header.
    Used for WebSocket transport, which frames messages for us."""
    payload = {"type": msg_type, "tick": tick, "data": data}
    return msgpack.packb(payload, use_bin_type=True)


async def read_message(reader):
    """Read one length-prefixed msgpack message from a TCP StreamReader."""
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError:
        return None

    length = struct.unpack("!I", header)[0]

    try:
        payload = await reader.readexactly(length)
    except asyncio.IncompleteReadError:
        return None

    return msgpack.unpackb(payload, raw=False)

class Connection:
    __slots__ = ("reader", "writer", "queue", "running")

    def __init__(self, reader, writer, queue):
        self.reader = reader
        self.writer = writer
        self.queue = queue
        self.running = True

    async def run(self):
        try:
            while self.running:
                msg = await read_message(self.reader)
                if msg is None:
                    break

                await self.queue.put(Event(
                    type=msg["type"],
                    tick=msg["tick"],
                    data=msg["data"],
                    conn=self
                ))

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            await self.queue.put(Event(
                type="disconnect",
                tick=0,
                data={},
                conn=self
            ))
            await self.close()

    async def send(self, msg_type, tick, **data):
        if not self.running:
            return

        try:
            self.writer.write(encode_message(msg_type, tick, **data))
            await self.writer.drain()
        except ConnectionResetError:
            self.running = False

    async def close(self):
        self.running = False
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except Exception:
            pass

class WebSocketConnection:
    __slots__ = ("ws", "queue", "running")

    def __init__(self, ws, queue):
        self.ws = ws
        self.queue = queue
        self.running = True

    async def run(self):
        try:
            async for raw in self.ws:
                if not self.running:
                    break

                if isinstance(raw, str):
                    raw = raw.encode()

                msg = msgpack.unpackb(raw, raw=False)
                await self.queue.put(Event(
                    type=msg["type"],
                    tick=msg["tick"],
                    data=msg["data"],
                    conn=self
                ))

        except ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            await self.queue.put(Event(
                type="disconnect",
                tick=0,
                data={},
                conn=self
            ))
            await self.close()

    async def send(self, msg_type, tick, **data):
        if not self.running:
            return

        try:
            raw = _pack_message(msg_type, tick, **data)
            await self.ws.send(raw)
        except ConnectionClosed:
            self.running = False

    async def close(self):
        self.running = False
        try:
            await self.ws.close()
        except Exception:
            pass

class Server:
    __slots__ = ("server", "ws_server", "event_queue", "clients")

    def __init__(self):
        self.server = None
        self.ws_server = None
        self.event_queue = asyncio.Queue()
        self.clients = []

    async def start(self, host, port, ws_port=None, **kwargs):
        self.server = await asyncio.start_server(
            self._handle_tcp_client,
            host=host,
            port=port,
            **kwargs
        )
        await self.server.start_serving()

        if ws_port is not None:
            self.ws_server = await websockets.serve(
                self._handle_ws_client,
                host,
                ws_port,
            )

    async def _handle_tcp_client(self, reader, writer):
        conn = Connection(reader, writer, self.event_queue)
        self.clients.append(conn)

        await self.event_queue.put(Event(
            type="connect",
            tick=0,
            data={"transport": "tcp"},
            conn=conn
        ))

        asyncio.create_task(conn.run())

    async def _handle_ws_client(self, ws):
        conn = WebSocketConnection(ws, self.event_queue)
        self.clients.append(conn)

        await self.event_queue.put(Event(
            type="connect",
            tick=0,
            data={"transport": "websocket"},
            conn=conn
        ))

        await conn.run()

    async def broadcast(self, msg_type, tick, **data):
        await asyncio.gather(
            *(client.send(msg_type, tick, **data) for client in self.clients)
        )

    async def stop(self):
        for client in self.clients:
            await client.close()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        if self.ws_server:
            self.ws_server.close()
            await self.ws_server.wait_closed()

class Client:
    __slots__ = ("conn", "event_queue", "_ws_port", "_ws_scheme")

    def __init__(self, ws_port=None, ws_scheme="ws"):
        self.conn = None
        self.event_queue = asyncio.Queue()
        self._ws_port = ws_port
        self._ws_scheme = ws_scheme

    async def connect(self, host, port, **kwargs):
        try:
            reader, writer = await asyncio.open_connection(host, port, **kwargs)
            self.conn = Connection(reader, writer, self.event_queue)
            asyncio.create_task(self.conn.run())
            return
        except OSError as tcp_err:
            if self._ws_port is None:
                raise

        uri = f"{self._ws_scheme}://{host}:{self._ws_port}"
        try:
            ws = await websockets.connect(uri)
        except Exception as ws_err:
            raise ConnectionError(
                f"Both TCP ({host}:{port}) and WebSocket ({uri}) failed."
            ) from ws_err

        self.conn = WebSocketConnection(ws, self.event_queue)
        asyncio.create_task(self.conn.run())

    async def send(self, msg_type, tick, **data):
        if self.conn:
            await self.conn.send(msg_type, tick, **data)

    async def disconnect(self):
        if self.conn:
            await self.conn.close()