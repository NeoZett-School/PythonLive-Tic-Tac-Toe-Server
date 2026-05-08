# 🎮 PythonLive Tic-Tac-Toe Server

A high-performance, asynchronous **Tic-Tac-Toe** game featuring real-time networking, arcade-style animations, and a unique "Limited Pieces" mechanic. Built with **Pygame** and **Asyncio**.

## 🚀 Features

- **Asynchronous Networking:** Built on a custom `system.network` layer for low-latency server-client communication, featured in the [LivePython project](https://github.com/NeoZett-School/LivePython).

- **Limited Piece Mechanic:** If configured, players are limited to a max_pieces count. Placing a new piece once the limit is reached requires moving an existing one, adding a strategic layer to the classic game.

- **Arcade Visuals:** Dynamic "Flashy" win indicators with pulsing neon frames.

  - Smooth scaling for game assets.

  - Interactive UI with real-time status updates.

- **Robust Game Logic:** Server-side win/draw validation.

  - Version synchronization to ensure client-server compatibility.

  - Automatic cleanup and session reset on player disconnect.

## 🛠️ Configuration

The game behavior is controlled via `config/client_config.json`, `config/server_config.json` and `config/app_config.json`. 

Key settings include:

| Setting | Description |
| ------- | ----------- |
| `max_pieces` | The maximum number of pieces a player can have on the board. |
| `pieces_limited` | Boolean toggle for the limited piece movement mechanic. |
| `win_delay` | Duration (in seconds) the winning animation plays before reset. |
| `board_size` | The pixel dimensions of the game board. |

## 🕹️ How to Play

1. **Start the Server:** Run the `server.bat` launcher to begin listening for connections.

2. **Connect Clients:** Launch two instances of the client.

3. **Gameplay:**

  - Click an empty slot to place a piece.

  - **Moving:** If you hit your piece limit, click one of your **existing pieces** to select it (indicated by a colored highlight), then click an empty slot to move it.

4. **Restart:** Once a game ends, press **SPACE** on the server to reset the board.

## 📂 Project Structure

- `Assets/`: Contains images (`o.png`, `x.png`, `board.png`) and audio.

- `config/`: JSON files for window titles, networking ports, and game rules.

- `system/`: Core libraries for networking and process management.

- `log/`: Automated server logging for debugging connection events.

## 💻 Requirements

- **Python 3.8+**

*Most packages should automatically be installed along with a virtual environment for consistent compatability.*

## 📝 Development Notes

The server uses a **Fixed Timestep with Accumulator** pattern to ensure game logic remains consistent regardless of framerate:

```python
delta_time = 1 / 60
while accumulator >= delta_time:
    # Logic update
    accumulator -= delta_time
```

This ensures that network messages and game-over timers are processed reliably across different hardware.

## 🤝 Contributing

Feel free to fork this repository and submit pull requests for new flashy animations or networking optimizations.