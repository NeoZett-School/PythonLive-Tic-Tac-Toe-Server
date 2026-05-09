"""The `network` module provides classes and functions for 
creating a simple TCP server and client using asyncio. 

It defines an `Event` class for representing events, a 
`Connection` class for managing individual client connections, a 
`Server` class for handling multiple clients and broadcasting 
messages, and a `Client` class for connecting to the server 
and sending/receiving messages. 

The module also includes utility functions for encoding and 
reading messages in a specific format."""

import asyncio
from typing import (
    Any, Self, List, Dict, Optional, AsyncGenerator
)
from websockets.server import ServerConnection

class Event:
    """Represents an event that occurs in the server or client."""
    
    type: str
    tick: int
    data: Dict[str, Any]
    conn: Optional["Connection"]

    def __init__(self: Self, type: str, tick: int, data: Dict[str, Any], conn: Optional["Connection"] = None) -> None: ...

def encode_message(msg_type: str, tick: int, **data: Any) -> bytes: 
    """Encodes a message with a type and associated data into bytes for transmission."""
async def read_message(reader: asyncio.StreamReader) -> Optional[Dict[str, Any]]: 
    """Reads a message from the given StreamReader and decodes it into a dictionary. 
    Returns None if the connection is closed."""

class Connection:
    """Class representing a client connection to the server."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    queue: asyncio.Queue
    running: bool

    def __init__(self: Self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, queue: asyncio.Queue) -> None: ...
    async def run(self: Self) -> None: ...
    async def send(self: Self, msg_type: str, tick: int, **data: Any) -> None: ...
    async def close(self: Self) -> None: ...

class WebSocketConnection:
    """A websocket connection that retains a connection over a websocket."""

    ws: ServerConnection
    queue: asyncio.Queue
    running: bool

    def __init__(self: Self, ws: ServerConnection, queue: asyncio.Queue): ...
    async def run(self: Self): ...
    async def send(self: Self, msg_type: str, tick: int, **data: Any): ...
    async def close(self: Self): ...

class Server:
    """Class representing the TCP server that can handle multiple client connections and broadcast messages to them."""

    server: Optional[asyncio.AbstractServer]
    ws_server: Optional[ServerConnection]
    event_queue: asyncio.Queue[Event]
    clients: List["Connection"]

    def __init__(self: Self) -> None: ...
    async def start(self, host: str, port: int, *args: Any, **kwargs: Any) -> None: ...
    async def broadcast(self: Self, msg_type: str, tick: int, **data: Any) -> None: ...
    async def get_events(self: Self) -> AsyncGenerator[Event, None]: ...
    async def stop(self: Self) -> None: ...

class Client:
    """Class representing a TCP client that can connect to the server, send messages, and receive events from the server."""

    conn: Optional[Connection]
    event_queue: asyncio.Queue[Event]

    def __init__(self: Self) -> None: ...
    async def connect(self, host: str, port: int, *args: Any, **kwargs: Any) -> None: ...
    async def send(self, msg_type: str, tick: int, **data: Any) -> None: ...
    async def get_events(self) -> AsyncGenerator[Event, None]: ...
    async def disconnect(self) -> None: ...