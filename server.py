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

MAX_EVENTS_PER_TICK = 50

LOG_FILE = r'log\server_log.txt'
CONFIG_FILE = r'config\server_config.json'
APP_CONFIG = r'config\app_config.json'

app_config = json.load(open(APP_CONFIG, "r"))

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

server_config = json.load(open(CONFIG_FILE, "r"))

pygame.display.set_caption(server_config['window_title'])
pygame.display.set_icon(pygame.image.load(app_config['window_icon']))
WIDTH, HEIGHT = app_config['screen_dimensions'].values()
screen = pygame.display.set_mode((WIDTH, HEIGHT))

CENTERX, CENTERY = (WIDTH // 2, HEIGHT // 2)

version = app_config["version"]

fill_color = app_config["fill_color"]
board_size = app_config["board_size"]
max_pieces = app_config["max_pieces"]
pieces_limited = app_config["pieces_limited"]
win_delay = app_config["win_delay"]
piece_size = board_size // 3
half_piece_size = piece_size // 2

piece_image_size = piece_size - 40

class Assets:
    class Fonts:
        header1 = pygame.font.SysFont("Georgia", 24)
        paragraph1 = pygame.font.SysFont("Georgia", 18)
        paragraph2 = pygame.font.SysFont("Verdana", 10)
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
    await server.start(server_config["host"], server_config["port"], reuse_address=True, family=socket.AF_INET)

    async def update_board():
        await server.broadcast(
            msg_type="update", 
            tick=frame_counter, 
            board_state=GameContext.board_state, 
            piece_counts=GameContext.piece_counts,
            turn=GameContext.turn
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
                if event.key == pygame.K_SPACE:
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
                    continue

                GameContext.players[character] = event.conn
                await event.conn.send(
                    msg_type="sync", 
                    tick=frame_counter, 
                    character=character
                )

                Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                    Assets.Fonts.paragraph1, 
                    f"It is {GameContext.turn}'s turn to place.",
                    (CENTERX, HEIGHT - 50)
                )
                
                await update_board()

            elif event.type == "disconnect":
                for char in ("o", "x"):
                    if event.conn == GameContext.players[char]:
                        GameContext.players[char] = None
                
                if len(server.clients) == 1:
                    Surfaces.subtitle, Surfaces.subtitle_rect = create_text_element(
                        Assets.Fonts.paragraph1, 
                        "Waiting for players...",
                        (CENTERX, HEIGHT - 50)
                    )
                    GameContext.reset()
                
                server.clients.remove(event.conn)
            
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

        now = time.perf_counter()
        frame_time = min(now - last_time, 0.25)
        last_time = now

        accumulator += frame_time

        while accumulator >= delta_time:

            # Update your game state using dt

            accumulator -= delta_time

        screen.fill(fill_color)

        alpha = accumulator / delta_time

        # Render the game state
        screen.blit(Surfaces.title, Surfaces.title_rect)
        screen.blit(Surfaces.subtitle, Surfaces.subtitle_rect)

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