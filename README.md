# Minecraft Server Watchdog

A Python service designed to monitor and manage an `itzg/minecraft-server` Docker container, primarily through Discord commands and automated inactivity checks. It interacts directly with the Docker API to control the server container and uses a Discord bot for user interaction and status notifications.

## Core Features

-   **Discord Command Control:** Start, stop, restart, and check the status of the Minecraft server via Discord commands (e.g., `!start`, `!stop`, `!status`, `!restart`).
-   **Discord Status Notifications:** Sends messages to a configured Discord channel when the server is starting, online (ready for players), stopping, or offline.
-   **Docker Container Management:** Directly interacts with the Docker API (via the mounted Docker socket) to start and stop the target Minecraft server container.
-   **Inactivity Shutdown Integration:** Works alongside the `itzg/minecraft-server` container's built-in autostop functionality to manage server uptime based on player presence.
-   **Selective Message Processing:** Only processes messages identified as commands in the Discord channel, reducing unnecessary overhead.
-   **Configuration:** Uses `.env` for sensitive data (like Discord tokens) and `config.py` for general settings (like container names, command prefixes).
-   **Logging:** Maintains logs of its operations and significant server events in the `logs/` directory.

## Setup / Configuration

1.  **Prerequisites:** Requires Python 3.9+ and Docker.
2.  **Docker Compose:** Designed to be run as a service in a `docker-compose.yml` setup. Ensure the watchdog service definition includes:
    *   Mounting the watchdog application directory (e.g., `./watchdog:/app`).
    *   Mounting the Docker socket (`/var/run/docker.sock:/var/run/docker.sock`).
    *   Mounting the workspace root if needed for accessing other files (`.:/workspace`).
    *   Necessary environment variables (see below).
3.  **Environment Variables (`.env`):** Create a `.env` file in the watchdog directory with the following:
    *   `DISCORD_BOT_TOKEN`: Your Discord bot token.
    *   `DISCORD_CHANNEL_ID`: The ID of the Discord channel for commands and notifications.
    *   `MINECRAFT_CONTAINER_NAME`: The exact name of the Minecraft server container (e.g., `wvh`).
    *   *(Add any other variables required by `config.py`)*
4.  **Configuration (`config.py`):** Review and adjust settings like command prefixes, log levels, or specific timeouts as needed.
5.  **Dependencies (`req.txt`):** Ensure `discord.py`, `python-dotenv`, and `docker` are listed. These are typically installed via the `command` section in `docker-compose.yml`.

## Usage

Once the watchdog container is running, interact with the bot in the specified Discord channel using the configured command prefix (e.g., `!start`, `!status`). The bot will provide feedback and status updates in the same channel.