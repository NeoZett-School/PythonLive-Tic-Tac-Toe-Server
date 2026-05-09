import system.network as network
from system.processes import set_appid, redirect_except
import logging
import asyncio
import sys, os
import socket
import json
import time
import math

import win32event
import win32api
import winerror

import warnings
warnings.simplefilter("always")

import psutil

def is_local_address(ip_to_check):
    interfaces = psutil.net_if_addrs()
    for interface_name, interface_addresses in interfaces.items():
        for address in interface_addresses:
            if address.address == ip_to_check:
                return True
    return False

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import pygame_gui

MAX_EVENTS_PER_TICK = 50

LOG_FILE = r'log\client_log.txt'
CONFIG_FILE = r'config\client_config.json'
APP_CONFIG = r'config\app_config.json'

app_config = json.load(open(APP_CONFIG, "r"))

APP_ID = fr'PythonLive.{app_config["app_name"]}.Client.{app_config["app_version"]}'

logging.basicConfig(
    filename=LOG_FILE, 
    filemode="a", 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
redirect_except()
set_appid(APP_ID)

mutex = win32event.CreateMutex(None, False, APP_ID)
last_error = win32api.GetLastError()
has_another_client = last_error == winerror.ERROR_ALREADY_EXISTS

pygame.init()

client_config = json.load(open(CONFIG_FILE, "r"))

is_device_server = is_local_address(client_config["host"])

sounds_active = not (has_another_client or is_device_server)

pygame.display.set_caption(app_config['window_title'])
pygame.display.set_icon(pygame.image.load(app_config['window_icon']))
WIDTH, HEIGHT = app_config['screen_dimensions'].values()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
manager = pygame_gui.UIManager((WIDTH, HEIGHT), "theme.json")

CENTERX, CENTERY = (WIDTH // 2, HEIGHT // 2)

version = app_config["version"]

fill_color = app_config["fill_color"]
board_size = app_config["board_size"]
max_pieces = app_config["max_pieces"]
pieces_limited = app_config["pieces_limited"]
max_messages = app_config["max_messages"]
win_delay = app_config["win_delay"]
piece_size = board_size // 3
half_piece_size = piece_size // 2

piece_image_size = piece_size - 40

class Assets:
    class Fonts:
        header1 = pygame.font.SysFont("Georgia", 24)
        paragraph1 = pygame.font.SysFont("Georgia", 18)
        paragraph2 = pygame.font.SysFont("Segoe UI", 14)
    class Images:
        board = pygame.transform.scale(pygame.image.load("assets/images/board.png"), (board_size, board_size))
        o_piece = pygame.transform.smoothscale(pygame.image.load("assets/images/o.png"), (piece_image_size, piece_image_size))
        x_piece = pygame.transform.smoothscale(pygame.image.load("assets/images/x.png"), (piece_image_size, piece_image_size))
    class Sounds:
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

def draw_messages(screen, font, messages, static_bottom_y, left_x, max_width=200):
    current_y = static_bottom_y
    padding = 5

    linesize = 3 # font.get_linesize()

    for message in reversed(messages):
        wrapped_lines = wrap_text(message, font, max_width)
        
        for line in reversed(wrapped_lines):
            text_surface = font.render(line, True, (50, 50, 50))
            msg_height = text_surface.get_height()
            
            current_y -= (msg_height + padding)
            screen.blit(text_surface, (left_x, current_y))

            if current_y < 0:
                return 
        
        current_y -= linesize

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
        f"{app_config['window_title']} - Client", 
        (CENTERX, 30)
    )

    subtitle, subtitle_rect = create_text_element(
        Assets.Fonts.paragraph1, 
        "Synchronizing...", 
        (CENTERX, HEIGHT - 50)
    )

    game_over_text, game_over_text_rect = create_text_element(
        Assets.Fonts.paragraph1, 
        "Ask server to restart", 
        (CENTERX, CENTERY)
    )

class GameContext:
    board_state = [[None, None, None], [None, None, None], [None, None, None]]
    character = None
    turn = "o"

    disallowed = False

    winner = None
    win_time = None
    win_ff = False # flip-flop

    moving_piece = None
    piece_counts = {
        "o": 0, 
        "x": 0
    }

    messages = []

    @classmethod
    def opponent(cls):
        return 'x' if cls.character == 'o' else 'o'

    @classmethod
    def personalize(cls, message):
        return (message
            .replace(f"{cls.character} ", "You ")
            .replace(f" {cls.character}", " You"))

    @classmethod
    def skip_prefixes(cls):
        return ("Invalid command", "Note", f"To {cls.opponent().upper()}", "To Server")

screen.fill((fill_color))
loading_text = Assets.Fonts.paragraph1.render("Connecting...", True, (50, 50, 50))
screen.blit(loading_text, loading_text.get_rect(center=(CENTERX, CENTERY)))
pygame.display.flip()

def quit():
    pygame.event.post(pygame.event.Event(pygame.QUIT))

async def main():
    client = network.Client()
    await client.connect(client_config["host"], client_config["port"], family=socket.AF_INET)

    await client.send(
        msg_type="sync", 
        tick=0, version=version)
    
    async def send_message(message):
        await client.send(
            msg_type="new_message",
            tick=frame_counter,
            message=message
        )

    running = True

    delta_time = 1 / 60
    accumulator = 0.0
    last_time = time.perf_counter()

    frame_counter = 0

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                await client.disconnect()
            
            # Handle pygame events
            if event.type == pygame.MOUSEBUTTONDOWN:
                if board_rect.collidepoint(event.pos):
                    rel_x = event.pos[0] - board_rect.left
                    rel_y = event.pos[1] - board_rect.top
                    
                    row, col = (rel_x // piece_size, rel_y // piece_size)

                    row = max(0, min(2, row))
                    col = max(0, min(2, col))

                    if GameContext.character is None:
                        GameContext.moving_piece = row, col
                        continue

                    if GameContext.board_state[row][col] == GameContext.character:
                        GameContext.moving_piece = row, col
                    else:
                        GameContext.moving_piece = None

                    await client.send(
                        msg_type="click", 
                        tick=frame_counter, 
                        row=row, col=col
                    )
                    
                    if sounds_active:
                        Assets.Sounds.placing.play()
                else:
                    GameContext.moving_piece = None
            
            if not GameContext.disallowed:
                manager.process_events(event)

            # Handle "Enter" key or finished input
            if event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
                if event.ui_element == UIElements.text_input:
                    entered_text = event.text.strip()
                    
                    command = entered_text
                    if command.startswith("/to-server"):
                        message = f"To Server: {command.removeprefix("/to-server").strip()}"
                    elif entered_text:
                        message = f"{GameContext.character.upper()}: {entered_text}"

                    clear_input_without_placeholder(UIElements.text_input)
                    manager.set_focus_set(set())
                    
                    await send_message(message)

        for _ in range(MAX_EVENTS_PER_TICK):
            try:
                event = client.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if event.type == "disconnect":
                running = False

            # Handle network events
            elif event.type == "sync":
                GameContext.character = event.data["character"]
                Surfaces.title, Surfaces.title_rect = create_text_element(
                    Assets.Fonts.header1, 
                    f"{app_config['window_title']} - {GameContext.character.upper()}", 
                    (CENTERX, 30)
                )
            
            elif event.type == "disallowed":
                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    event.data["msg"], 
                    (CENTERX, HEIGHT - 50)
                )
                GameContext.disallowed = True
            
            elif event.type == "restart":
                GameContext.board_state = [[None, None, None], [None, None, None], [None, None, None]]
                GameContext.winner = None
                GameContext.win_ff = False
                GameContext.moving_piece = None

                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    "Restarting...", 
                    (CENTERX, HEIGHT - 50)
                )
            
            elif event.type == "update":
                GameContext.board_state = event.data["board_state"]
                GameContext.piece_counts = event.data["piece_counts"]
                GameContext.turn = event.data["turn"]
                if not GameContext.turn == GameContext.character:
                    text = f"It is {GameContext.turn}'s turn to place." 
                else:
                    text = "It is your turn to place."
                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    text, 
                    (CENTERX, HEIGHT - 50)
                )
            
            elif event.type == "game_over":
                GameContext.winner = event.data["winner"]
                GameContext.win_time = time.perf_counter()
                if GameContext.winner == GameContext.character:
                    supportive_message = "Congrats! You won." 
                elif GameContext.winner == "draw":
                    supportive_message = "It is a draw. You will win next time!"
                else:
                    supportive_message = "Oh no! Seems like you failed."
                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    f"Game over. {supportive_message}", 
                    (CENTERX, HEIGHT - 50)
                )
            
            elif event.type == "update_messages":
                GameContext.messages.clear()
                GameContext.messages.extend(
                    GameContext.personalize(message)
                    for message in event.data["messages"]
                    if not message.startswith(GameContext.skip_prefixes())
                )
        
        now = time.perf_counter()
        frame_time = min(now - last_time, 0.25)
        last_time = now

        accumulator += frame_time

        while accumulator >= delta_time:

            # Update your game state using delta_time
            if not GameContext.disallowed:
                manager.update(delta_time)

            accumulator -= delta_time

        screen.fill(fill_color)

        alpha = accumulator / delta_time

        # Render the game state
        screen.blit(Surfaces.title, Surfaces.title_rect)
        screen.blit(Surfaces.subtitle, Surfaces.subtitle_rect)

        if not GameContext.disallowed:
            manager.draw_ui(screen)
            draw_messages(screen, Assets.Fonts.paragraph2, GameContext.messages, HEIGHT - 45, 10)

        if GameContext.winner is None or now - GameContext.win_time < win_delay:
            screen.blit(Assets.Images.board, board_rect)
            for x, row in enumerate(GameContext.board_state):
                for y, col in enumerate(row):
                    if col is None: continue
                    surface = Assets.Images.o_piece if col == "o" else Assets.Images.x_piece
                    center = (
                        first_slot_x + piece_size * x, 
                        first_slot_y + piece_size * y
                    )
                    screen.blit(surface, surface.get_rect(center=center))
            
            if pieces_limited and GameContext.moving_piece:
                m_row, m_col = GameContext.moving_piece
                if GameContext.character == "o":
                    color = (200, 200, 255)
                elif GameContext.character == "x":
                    color = (255, 200, 200)
                else:
                    color = (200, 200, 200)
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
                            pulse = (math.sin(now * 15) + 1) / 2 
                            
                            for r, c in win:
                                pos_x = first_slot_x + piece_size * r
                                pos_y = first_slot_y + piece_size * c
                                
                                frame_size = piece_size * 0.8 + (pulse * 10)
                                rect = pygame.Rect(0, 0, frame_size, frame_size)
                                rect.center = (pos_x, pos_y)
                                
                                remaining_ratio = 1.0 - (time_passed / win_delay)
                                shrink_amount = -int((1.0 - remaining_ratio) * piece_size)
                                draw_rect = rect.inflate(shrink_amount, shrink_amount)
                                
                                if draw_rect.width > 5:
                                    pygame.draw.rect(screen, color, draw_rect, 3, border_radius=12)
                                    
                                    inner_rect = draw_rect.inflate(-10, -10)
                                    if inner_rect.width > 0:
                                        pygame.draw.rect(screen, (255, 255, 255), inner_rect, 1, border_radius=8)
                            
                            break
        else:
            if not GameContext.win_ff:
                if sounds_active:
                    Assets.Sounds.win.play()
                GameContext.win_ff = True

            screen.blit(Surfaces.game_over_text, Surfaces.game_over_text_rect)

        pygame.display.flip()

        await asyncio.sleep(0)
        frame_counter += 1

if __name__ == "__main__":
    asyncio.run(main())

logging.info("Client closed")

pygame.quit()
sys.exit()