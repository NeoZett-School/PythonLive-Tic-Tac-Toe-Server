import system.network as network
from system.processes import set_appid, redirect_except
import logging
import asyncio
import sys, os
import socket
import json
import time
import math

import warnings
warnings.simplefilter("always")

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import pygame_gui

MAX_EVENTS_PER_TICK = 50

LOG_FILE = r'log\server_log.txt'
CONFIG_FILE = r'config\server_config.json'
APP_CONFIG = r'config\app_config.json'

with open(APP_CONFIG, "r") as f:
    app_config = json.load(f)

APP_ID = fr'PythonLive.{app_config["app_name"]}.Server.{app_config["app_version"]}'

logging.basicConfig(
    filename=LOG_FILE, 
    filemode="a", 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
redirect_except()
set_appid(APP_ID)

pygame.init()

with open(CONFIG_FILE, "r") as f:
    server_config = json.load(f)

pygame.display.set_caption(server_config['window_title'])
pygame.display.set_icon(pygame.image.load(app_config['window_icon']))
WIDTH, HEIGHT = app_config['screen_dimensions'].values()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
manager = pygame_gui.UIManager((WIDTH, HEIGHT), "theme.json")

CENTERX, CENTERY = (WIDTH // 2, HEIGHT // 2)

MUSIC_TRACKS = [
    "assets/sounds/music/track1.mp3",
    "assets/sounds/music/track2.mp3",
    "assets/sounds/music/track3.mp3",
]
music_index = 0

MUSIC_END = pygame.USEREVENT + 1
pygame.mixer.music.set_endevent(MUSIC_END)

def play_next_track():
    global music_index
    pygame.mixer.music.load(MUSIC_TRACKS[music_index])
    pygame.mixer.music.play()
    music_index = (music_index + 1) % len(MUSIC_TRACKS)

play_next_track()

version = app_config["version"]

fill_color = app_config["fill_color"]
board_size = app_config["board_size"]
max_pieces = app_config["max_pieces"]
pieces_limited = app_config["pieces_limited"]
max_messages = app_config["max_messages"]
win_delay = app_config["win_delay"]
move_duration = app_config["move_duration"]
piece_size = board_size // 3
half_piece_size = piece_size // 2

piece_image_size = piece_size - 40

def round_corners(surface, radius):
    width, height = surface.get_size()

    mask = pygame.Surface((width, height), pygame.SRCALPHA)

    pygame.draw.rect(
        mask,
        (255, 255, 255, 255),
        (0, 0, width, height),
        border_radius=radius
    )

    rounded = pygame.Surface((width, height), pygame.SRCALPHA)
    rounded.blit(surface, (0, 0))
    rounded.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    return rounded

class Assets:
    class Fonts:
        header1 = pygame.font.Font("assets/fonts/Georama-Bold.ttf", 24)
        paragraph1 = pygame.font.Font("assets/fonts/Montserrat-Regular.ttf", 18)
        paragraph2 = pygame.font.Font("assets/fonts/FiraCode-Regular.ttf", 14)
    class Images:
        background = pygame.transform.scale(pygame.image.load("assets/images/background.png"), (WIDTH, HEIGHT))
        _board = pygame.transform.scale(pygame.image.load("assets/images/board.png"), (board_size, board_size))
        board = round_corners(_board, 30)
        o_piece = pygame.transform.smoothscale(pygame.image.load("assets/images/o.png"), (piece_image_size, piece_image_size))
        x_piece = pygame.transform.smoothscale(pygame.image.load("assets/images/x.png"), (piece_image_size, piece_image_size))
    class Sounds:
        connection = pygame.mixer.Sound("assets/sounds/connection.mp3")
        disconnection = pygame.mixer.Sound("assets/sounds/disconnection.mp3")
        restart = pygame.mixer.Sound("assets/sounds/restart.mp3")
        placing = pygame.mixer.Sound("assets/sounds/placing.mp3")
        win = pygame.mixer.Sound("assets/sounds/win.mp3")

board_rect = Assets.Images.board.get_rect(center=(CENTERX, CENTERY))

first_slot_x = board_rect.left + half_piece_size
first_slot_y = board_rect.top + half_piece_size

possible_wins = [
    *[[(0, i), (1, i), (2, i)] for i in range(3)],  # Vertical wins
    *[[(i, 0), (i, 1), (i, 2)] for i in range(3)],  # Horizontal wins
    [(0, 0), (1, 1), (2, 2)],                       # Diagonal 1
    [(2, 0), (1, 1), (0, 2)]                        # Diagonal 2
]

def create_text_element(font, text, center_pos, color=(50, 50, 50)):
    surface = font.render(text, True, color)
    rect = surface.get_rect(center=center_pos)
    return surface, rect

def wrap_text(text, font, max_width):
    """Wraps text into a list of lines that fit within max_width."""
    words = text.split(' ')
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        width, _ = font.size(test_line)
        
        if width <= max_width:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

def draw_messages(screen, font, messages, static_bottom_y, left_x, max_width=150):
    padding_x = 10
    padding_y = 6
    bubble_gap = 5
    corner_radius = 10
    current_y = static_bottom_y

    for message in reversed(messages):
        wrapped_lines = wrap_text(message, font, max_width)

        if message.startswith("Invalid command"):
            color_top = (180, 60, 60, 200)
            color_bottom = (120, 30, 30, 180)
            text_color = (255, 200, 200)
        elif message.startswith("To"):
            color_top = (80, 60, 160, 200)
            color_bottom = (50, 35, 120, 180)
            text_color = (200, 185, 255)
        elif message.startswith("From"):
            color_top = (40, 130, 80, 200)
            color_bottom = (25, 85, 50, 180)
            text_color = (185, 255, 210)
        elif message.startswith("Note"):
            color_top = (80, 60, 160, 200)
            color_bottom = (50, 35, 120, 180)
            text_color = (200, 185, 255)
        else:
            color_top = (110, 80, 120, 190)
            color_bottom = (55, 60, 110, 170)
            text_color = (225, 220, 235)

        line_surfaces = [font.render(line, True, text_color) for line in wrapped_lines]
        bubble_w = max(s.get_width() for s in line_surfaces) + padding_x * 2
        bubble_h = sum(s.get_height() for s in line_surfaces) + padding_y * 2 + (len(line_surfaces) - 1) * 2

        current_y -= bubble_h + bubble_gap

        if current_y < 0:
            return

        halo_inflate = 3
        halo_surf = pygame.Surface((bubble_w + halo_inflate * 2, bubble_h + halo_inflate * 2), pygame.SRCALPHA)
        halo_color = (*color_bottom[:3], 40)
        pygame.draw.rect(halo_surf, halo_color,
                         halo_surf.get_rect(), border_radius=corner_radius + halo_inflate)
        screen.blit(halo_surf, (left_x - halo_inflate, current_y - halo_inflate))

        bubble_surf = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
        for i in range(bubble_h):
            t = i / max(bubble_h - 1, 1)
            r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
            g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
            b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
            a = int(color_top[3] + (color_bottom[3] - color_top[3]) * t)
            pygame.draw.line(bubble_surf, (r, g, b, a), (0, i), (bubble_w, i))

        mask_surf = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
        pygame.draw.rect(mask_surf, (255, 255, 255, 255),
                         mask_surf.get_rect(), border_radius=corner_radius)
        bubble_surf.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        highlight_surf = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
        pygame.draw.rect(highlight_surf, (255, 255, 255, 30),
                         pygame.Rect(0, 0, bubble_w, bubble_h // 3),
                         border_radius=corner_radius)
        bubble_surf.blit(highlight_surf, (0, 0))

        pygame.draw.rect(bubble_surf, (*color_top[:3], 45),
                         bubble_surf.get_rect(), 1, border_radius=corner_radius)

        screen.blit(bubble_surf, (left_x, current_y))

        text_y = current_y + padding_y
        for surf in line_surfaces:
            screen.blit(surf, (left_x + padding_x, text_y))
            text_y += surf.get_height() + 2

def clear_input_without_placeholder(ui_element):
    """Manually clears the text entry without triggering the 
    internal placeholder rendering logic as it does in the pygame-gui source code."""
    ui_element.text = ""
    ui_element.edit_position = 0
    
    if ui_element.drawable_shape is not None and ui_element.drawable_shape.text_box_layout is not None:
        # We call the underlying drawable_shape directly with an empty string
        # This bypasses the 'if len(display_text) > 0 else placeholder' check
        ui_element.drawable_shape.set_text("")
        
        ui_element.drawable_shape.text_box_layout.set_cursor_position(0)
        ui_element.drawable_shape.apply_active_text_changes()

class UIElements:
    text_input = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect((10, HEIGHT-35), (200, 25)), 
        manager=manager,
        placeholder_text="Send a message"
    )

class Surfaces:
    title, title_rect = create_text_element(
        Assets.Fonts.header1, 
        f"{app_config['window_title']} - Server", 
        (CENTERX, 30)
    )

    subtitle, subtitle_rect = create_text_element(
        Assets.Fonts.paragraph1, 
        "Waiting for players...", 
        (CENTERX, HEIGHT - 50)
    )

    game_over_text, game_over_text_rect = create_text_element(
        Assets.Fonts.paragraph1, 
        "Press space to restart", 
        (CENTERX, CENTERY)
    )

class GameContext:
    players = {
        "o": None,
        "x": None
    }
    turn = "o"
    board_state = [[None, None, None], [None, None, None], [None, None, None]]

    winner = None
    win_time = None
    win_ff = False # flip-flop

    moving_piece = None
    piece_counts = {
        "o": 0, 
        "x": 0
    }

    last_placed_piece = None
    last_placed_time = None

    messages = [
        "Server has started listening."
    ]

    @classmethod
    def reset(cls):
        cls.board_state = [[None, None, None], [None, None, None], [None, None, None]]
        cls.piece_counts = {"o": 0, "x": 0}
        cls.turn = "o"
        cls.winner = None
        cls.moving_piece = None
        cls.win_ff = False

def quit():
    pygame.event.post(pygame.event.Event(pygame.QUIT))

async def main():
    server = network.Server()
    await server.start(
        host=server_config["host"], 
        port=server_config["port"], 
        ws_port=server_config["ws_port"],
        reuse_address=True, 
        family=socket.AF_INET
    )

    async def update_board():
        await server.broadcast(
            msg_type="update", 
            tick=frame_counter, 
            board_state=GameContext.board_state, 
            piece_counts=GameContext.piece_counts,
            last_placed_piece=GameContext.last_placed_piece,
            turn=GameContext.turn
        )
    
    async def update_messages():
        while len(GameContext.messages) > max_messages:
            GameContext.messages.pop(0)
        await server.broadcast(
            msg_type="update_messages",
            tick=frame_counter,
            messages=GameContext.messages
        )

    running = True

    delta_time = 1 / 60
    accumulator = 0.0
    last_time = time.perf_counter()

    frame_counter = 0

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                await server.stop()
                running = False
            
            # Handle pygame events
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and not UIElements.text_input.is_focused and GameContext.winner is not None:
                    GameContext.reset()

                    Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                        Assets.Fonts.paragraph1, 
                        f"It is {GameContext.turn}'s turn to place.",
                        (CENTERX, HEIGHT - 50)
                    )

                    await server.broadcast(
                        msg_type="restart",
                        tick=frame_counter
                    )

                    await update_board()
                    Assets.Sounds.restart.play()
            
            elif event.type == MUSIC_END:
                play_next_track()
            
            manager.process_events(event)

            # Handle "Enter" key or finished input
            if event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
                if event.ui_element == UIElements.text_input:
                    entered_text = event.text.strip()
                    
                    command = entered_text
                    if command == "/clear":
                        GameContext.messages = [
                            "Server has cleared all messages."
                        ]
                    elif command == "/kick":
                        for client in server.clients:
                            await client.send(
                                msg_type="disallowed",
                                tick=frame_counter,
                                msg="You were kicked by the server."
                            )
                            client.close()
                            client.running = False
                        GameContext.messages.append(
                            "All clients have been kicked from the session."
                        )
                    elif command.startswith("/set-turn"):
                        turn = command.removeprefix("/set-turn").strip().upper()
                        if turn in ("O", "X"):
                            GameContext.turn = turn.lower()
                            Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                                Assets.Fonts.paragraph1, 
                                f"It is {GameContext.turn}'s turn to place.",
                                (CENTERX, HEIGHT - 50)
                            )
                            await update_board()
                            GameContext.messages.append(
                                f"Server has enforced {GameContext.turn}'s turn."
                            )
                        else:
                            GameContext.messages.append(
                                "Invalid command: you must specifically state 'o' or 'x' after '/set-turn' in order of setting their turn."
                            )
                    elif command.startswith("/note"):
                        note = command.removeprefix("/note").strip()
                        GameContext.messages.append(
                            f"Note: {note}"
                        )
                    elif command.startswith("/msg"):
                        following = command.removeprefix("/msg").strip()
                        to = following.split(" ")[0]
                        text = following.removeprefix(to).strip()
                        to = to.upper()

                        if to not in ("O", "X") or not text:
                            GameContext.messages.append("Invalid command; Usage: /msg <o|x> <message>")
                        else:
                            GameContext.messages.append(f"To {to}: {text}")
                    elif command == "/reset":
                        GameContext.reset()

                        Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                            Assets.Fonts.paragraph1, 
                            f"It is {GameContext.turn}'s turn to place." if len(server.clients) > 0 else "Waiting for players...",
                            (CENTERX, HEIGHT - 50)
                        )

                        await server.broadcast(
                            msg_type="restart",
                            tick=frame_counter
                        )

                        await update_board()
                        Assets.Sounds.restart.play()
                        GameContext.messages.append(
                            "Server has reset the board."
                        )
                    elif entered_text:
                        message = f"Server: {entered_text}"
                        GameContext.messages.append(message)

                    clear_input_without_placeholder(UIElements.text_input)
                    manager.set_focus_set(set())
                    
                    await update_messages()
        
        for _ in range(MAX_EVENTS_PER_TICK):
            try:
                event = server.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if event.conn not in server.clients:
                continue

            if event.type == "sync":
                if not event.data["version"] == version:
                    await event.conn.send(
                        msg_type="disallowed",
                        tick=frame_counter,
                        msg="Wrong version; The server and client were not the same version."
                    )
                    event.conn.close()
                    event.conn.running = False
                    GameContext.messages.append("Client did not have matching versions.")
                    await update_messages()
                    continue

                character = None
                for char in ("o", "x"):
                    conn = GameContext.players[char]
                    if conn is None or conn not in server.clients:
                        character = char
                        break

                if character is None:
                    await event.conn.send(
                        msg_type="disallowed",
                        tick=frame_counter,
                        msg="Not allowed entrance: All characters have been taken."
                    )
                    event.conn.close()
                    event.conn.running = False
                    GameContext.messages.append("Client could not be given any character.")
                    await update_messages()
                    continue

                GameContext.players[character] = event.conn
                await event.conn.send(
                    msg_type="sync", 
                    tick=frame_counter, 
                    character=character
                )

                GameContext.messages.append(f"Character {character.upper()} was given.")
                await update_messages()

                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    f"It is {GameContext.turn}'s turn to place.",
                    (CENTERX, HEIGHT - 50)
                )
                
                await update_board()
                await update_messages()
            
            elif event.type == "connect":
                GameContext.messages.append("A new client has connected.")
                await update_messages()
                Assets.Sounds.connection.play()

            elif event.type == "disconnect":
                GameContext.messages.append(f"A client disconnected.")

                for char in ("o", "x"):
                    if event.conn == GameContext.players[char]:
                        GameContext.players[char] = None
                        GameContext.messages.append(f"Character {char.upper()} has been reset.")
                
                await update_messages()
                
                if len(server.clients) == 1:
                    Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                        Assets.Fonts.paragraph1, 
                        "Waiting for players...",
                        (CENTERX, HEIGHT - 50)
                    )
                    GameContext.reset()
                    Assets.Sounds.restart.play()
                
                server.clients.remove(event.conn)
                Assets.Sounds.disconnection.play()
            
            # Handle network events
            elif event.type == "click":
                if GameContext.winner is not None:
                    continue

                if not event.conn == GameContext.players[GameContext.turn]:
                    continue

                row, col = event.data["row"], event.data["col"]

                occupation = GameContext.board_state[row][col]
                if occupation is not None:
                    if occupation == GameContext.turn:
                        GameContext.moving_piece = row, col
                    continue

                current_count = GameContext.piece_counts[GameContext.turn]

                if pieces_limited and current_count >= max_pieces:
                    if GameContext.moving_piece is None:
                        continue

                    old_row, old_col = GameContext.moving_piece
                    GameContext.board_state[old_row][old_col] = None
                    GameContext.piece_counts[GameContext.turn] -= 1

                GameContext.board_state[row][col] = GameContext.turn
                GameContext.piece_counts[GameContext.turn] += 1
                GameContext.moving_piece = None

                GameContext.last_placed_piece = (row, col)
                GameContext.last_placed_time = time.perf_counter()

                winner_found = None

                for win in possible_wins:
                    values = [GameContext.board_state[r][c] for r, c in win]
                    if values[0] is not None and all(v == values[0] for v in values):
                        winner_found = values[0]
                        break

                if not winner_found and not any(None in row for row in GameContext.board_state):
                    winner_found = "draw"

                if winner_found:
                    GameContext.winner = winner_found
                    GameContext.win_time = time.perf_counter()
                    
                    text = "Nobody won; it is a draw." if winner_found == "draw" else f"Player {winner_found} won!"
                    Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                        Assets.Fonts.paragraph1, text, (CENTERX, HEIGHT - 50)
                    )

                    await update_board()
                    await server.broadcast(
                        msg_type="game_over",
                        tick=frame_counter,
                        winner=GameContext.winner
                    )
                    continue

                GameContext.turn = "o" if GameContext.turn == "x" else "x"

                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    f"It is {GameContext.turn}'s turn to place.",
                    (CENTERX, HEIGHT - 50)
                )

                await update_board()
                Assets.Sounds.placing.play()
            
            elif event.type == "new_message":
                GameContext.messages.append(event.data["message"])
                await update_messages()

        now = time.perf_counter()
        frame_time = min(now - last_time, 0.25)
        last_time = now

        accumulator += frame_time

        while accumulator >= delta_time:

            # Update your game state using dt
            manager.update(delta_time)

            accumulator -= delta_time

        screen.fill(fill_color)

        alpha = accumulator / delta_time

        # Render the game state
        screen.blit(Assets.Images.background, (0, 0))
        
        screen.blit(Surfaces.title, Surfaces.title_rect)
        screen.blit(Surfaces.subtitle, Surfaces.subtitle_rect)

        manager.draw_ui(screen)
        draw_messages(screen, Assets.Fonts.paragraph2, GameContext.messages, HEIGHT - 45, 10)

        if GameContext.winner is None or now - GameContext.win_time < win_delay:
            screen.blit(Assets.Images.board, board_rect)
            for x, row in enumerate(GameContext.board_state):
                for y, col in enumerate(row):
                    if col is None:
                        continue

                    center = (
                        first_slot_x + piece_size * x,
                        first_slot_y + piece_size * y
                    )

                    base_surface = (
                        Assets.Images.o_piece
                        if col == "o"
                        else Assets.Images.x_piece
                    )

                    if GameContext.last_placed_piece == (x, y):
                        elapsed = now - GameContext.last_placed_time
                        t = min(elapsed / move_duration, 1.0)

                        t = 1 - pow(1 - t, 3)

                        scale = pygame.math.lerp(1.22, 1.0, t)

                        alpha = pygame.math.lerp(120, 255, t)

                        scaled_size = int(piece_image_size * scale)

                        surface = pygame.transform.smoothscale(
                            base_surface,
                            (scaled_size, scaled_size)
                        ).convert_alpha()

                        surface.set_alpha(int(alpha))

                        rect = surface.get_rect(center=center)

                        glow_size = scaled_size + int((1 - t) * 20)

                        glow_surface = pygame.Surface(
                            (glow_size, glow_size),
                            pygame.SRCALPHA
                        )

                        glow_color = (
                            (120, 170, 255, 45)
                            if col == "o"
                            else (255, 140, 140, 45)
                        )

                        pygame.draw.circle(
                            glow_surface,
                            glow_color,
                            (glow_size // 2, glow_size // 2),
                            glow_size // 2
                        )

                        glow_rect = glow_surface.get_rect(center=center)

                        screen.blit(glow_surface, glow_rect)
                        screen.blit(surface, rect)

                    else:
                        screen.blit(
                            base_surface,
                            base_surface.get_rect(center=center)
                        )

            if pieces_limited and GameContext.moving_piece:
                m_row, m_col = GameContext.moving_piece
                color = (200, 200, 255) if GameContext.turn == "o" else (255, 200, 200)
                m_center = (first_slot_x + piece_size * m_row, first_slot_y + piece_size * m_col)
                highlight_rect = Assets.Images.o_piece.get_rect(center=m_center).inflate(20, 20)
                thickness = 3 + int(math.sin(time.perf_counter() * 10) * 2)
                pygame.draw.rect(screen, color, highlight_rect, thickness, 8)
            
            if GameContext.winner and GameContext.winner != "draw":
                time_passed = now - GameContext.win_time
                
                if time_passed < win_delay:
                    for win in possible_wins:
                        values = [GameContext.board_state[r][c] for r, c in win]
                        if all(v == GameContext.winner for v in values):
                            color = (100, 255, 100) if GameContext.winner == "o" else (255, 100, 100)
                            pulse = (math.sin(now * 6) + 1) * 0.5
                            progress = min(time_passed / win_delay, 1.0)
                            shrink = pygame.math.lerp(0, piece_size * 0.9, progress)

                            for r, c in win:
                                pos_x = first_slot_x + piece_size * r
                                pos_y = first_slot_y + piece_size * c

                                base_size = piece_size * 0.82
                                animated_size = base_size + (pulse * 8)
                                final_size = max(8, animated_size - shrink)

                                rect = pygame.Rect(0, 0, final_size, final_size)
                                rect.center = (pos_x, pos_y)

                                glow_rect = rect.inflate(18, 18)

                                glow_surface = pygame.Surface(
                                    (glow_rect.width, glow_rect.height),
                                    pygame.SRCALPHA
                                )

                                pygame.draw.rect(
                                    glow_surface,
                                    (*color, 40),
                                    glow_surface.get_rect(),
                                    border_radius=18
                                )

                                screen.blit(glow_surface, glow_rect.topleft)

                                border_width = 3 + int(pulse * 2)
                                pygame.draw.rect(
                                    screen,
                                    color,
                                    rect,
                                    width=border_width,
                                    border_radius=14
                                )

                                inner_rect = rect.inflate(-12, -12)

                                if inner_rect.width > 0:
                                    pygame.draw.rect(
                                        screen,
                                        (255, 255, 255),
                                        inner_rect,
                                        width=2,
                                        border_radius=10
                                    )
                            
                            break
        else:
            if not GameContext.win_ff:
                Assets.Sounds.win.play()
                GameContext.win_ff = True
            screen.blit(Surfaces.game_over_text, Surfaces.game_over_text_rect)

        pygame.display.flip()

        await asyncio.sleep(0)
        frame_counter += 1

if __name__ == "__main__":
    asyncio.run(main())

logging.info("Server closed")

pygame.quit()
sys.exit()