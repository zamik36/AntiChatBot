# AntiChatBot

## Description

AntiChatBot is a Python desktop application designed to automate the initial interaction phase with website chat widgets. It aims to bypass automated bot responses and directly request a connection with a human operator. The application uses Selenium for web automation, a configuration file (`config.json`) for site settings, and optionally integrates with a Telegram bot via Redis for operator notifications and CAPTCHA solving assistance.

## Features

*   **Graphical User Interface (GUI):** Built with Tkinter for site selection and status monitoring.
*   **Configuration Driven:** Uses `config.json` for site URLs, selectors, bot phrases, etc.
*   **Web Automation:** Uses Selenium to interact with web chats.
*   **Human Emulation:** Basic scrolling and mouse movements.
*   **Improved Operator Detection:** Checks all new messages for operator patterns, uses site-specific patterns and configurable bot phrases.
*   **Unique Responses:** Cycles through available operator request templates to avoid repetition.
*   **Multi-step Chat Opening:** Handles sites requiring multiple button clicks to initiate chat (e.g., cookie consent, post-open buttons).
*   **Manual Step Handling:** Pauses for user input on pre-chat forms.
*   **Browser Persistence:** Option to keep the browser window open after an operator is found.
*   **(Optional) Telegram Integration via Redis:**
    *   Sends notifications to your Telegram when an operator connects.
    *   Sends CAPTCHA images to your Telegram and waits for you to send back the solution.
*   **Support for multiple sites:** Pre-configured for Tele2, Beeline, Yota.

## How it Works (with Telegram Integration)

1.  Loads configurations from `config.json` and secrets from `.env`.
2.  The GUI appears.
3.  A separate `telegram_bot.py` script connects to Telegram and listens to Redis channels.
4.  User selects a site and clicks "Начать диалог".
5.  Selenium browser starts, navigates, and handles preliminary button clicks (e.g., cookies).
6.  User might need to log in manually in the browser.
7.  The app clicks the main chat button and any subsequent required buttons (e.g., "Пока нет" on Yota).
8.  **User Interaction (Form):** GUI prompts user (`ACTION REQUIRED`) to fill the pre-chat form in the browser, if applicable.
9.  User fills the form and clicks "Продолжить (после формы)" in the GUI.
10. The app sends an initial message.
11. The app enters a loop:
    *   Waits for responses (reduced wait time).
    *   **If CAPTCHA detected:** Publishes the image data to Redis. `telegram_bot.py` receives it, sends the image to the user via Telegram. The main app waits for the user to send the solution text to the Telegram bot. `telegram_bot.py` publishes the solution back via Redis. The main app receives it and sends it to the web chat.
    *   **Checks *all* new messages:** Iterates through all new messages received since the last check.
    *   **If operator message detected in *any* new message:** Publishes a notification to Redis. `telegram_bot.py` receives it and sends a notification to the user via Telegram. The main app loop finishes, leaving the browser window open.
    *   **If only bot messages detected:** Chooses a **unique**, not recently used template from `response_templates` and sends it.
12. Loop continues until operator found or max attempts reached.
13. Status updates displayed in GUI.

## Configuration (`config.json`)

*   Contains `_defaults` for common patterns (operator/bot phrases, response templates, emulation).
*   Contains a `sites` section where each key is a site name (e.g., `Tele2`, `Beeline`, `Yota`):
    *   `login_url`: Chat/login page URL.
    *   `cookie_consent_button_selector` (Optional): CSS selector for the cookie consent button.
    *   `chat_button_selector`: CSS selector for the primary chat initiation button.
    *   `post_chat_open_button_selector` (Optional): CSS selector for a button that needs to be clicked *after* the main chat button (e.g., "Пока нет" on Yota).
    *   `selectors`: Dictionary of CSS selectors for chat interaction:
        *   `input_field`: The text input area.
        *   `send_button`: The message send button.
        *   `messages_area`: The container for all messages.
        *   `individual_message`: Selector for a single message bubble/element.
        *   `text_content_selector` (Optional): A more specific selector *within* `individual_message` to extract only the message text (useful for sites like Beeline where the default text includes sender/time).
    *   `operator_join_patterns` (Optional): List of site-specific regex patterns indicating an operator joined. Overrides `_defaults`.
    *   `bot_indicator_phrases` (Optional): List of site-specific phrases indicating a bot message. Checked *before* `operator_join_patterns`. Overrides `_defaults`.
    *   `max_operator_request_attempts` (Optional): Maximum attempts to request an operator. Overrides `_defaults`.

**Note:** Accurate selectors are crucial. Use browser developer tools (F12) to find them.

## Setup

1.  **Prerequisites:**
    *   Python 3.8+
    *   Google Chrome browser
    *   Docker Desktop (Windows/macOS) or Docker Engine (Linux) installed and running.

2.  **Redis Setup (using Docker):**
    *   Redis is used for communication between the GUI, Chat Service, and the Telegram Bot.
    *   The easiest way to run Redis is using the provided `docker-compose.yml` file.
    *   Open your terminal in the project root directory and run:
        ```bash
        docker-compose up -d
        ```
    *   This will start a Redis container in the background.
    *   **To check logs:** `docker-compose logs redis`
    *   **To stop:** `docker-compose down`
    *   Ensure Redis is running via Docker Compose before starting the application components.

3.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd AntiChatBot
    ```

4.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

5.  **Install dependencies:**
    ```bash
    # Ensure you have the job queue extra for the Telegram bot
    python -m pip install --upgrade "python-telegram-bot[job-queue]"
    pip install -r requirements.txt
    ```
    *(Installs Selenium, webdriver-manager, redis-py, python-dotenv, python-telegram-bot, etc.)*

6.  **(Optional but Recommended) Telegram Bot Setup:**
    *   Open Telegram and talk to `BotFather`.
    *   Create a new bot using `/newbot` command and follow instructions.
    *   **Copy the BOT TOKEN** provided by BotFather.
    *   Talk to `userinfobot` (or similar) in Telegram to **get your numerical USER ID**.
    *   Create a file named `.env` in the project root directory.
    *   Add the following lines to `.env`, replacing the placeholders with your actual token and ID:
        ```dotenv
        TELEGRAM_BOT_TOKEN=12345:your_actual_bot_token_here
        TELEGRAM_USER_ID=987654321
        # Optional: Specify Redis connection if not localhost:6379
        # REDIS_HOST=your_redis_host
        # REDIS_PORT=your_redis_port
        ```
    *   **Ensure `.env` is listed in your `.gitignore` file!**

7.  **Configure `config.json`:**
    *   Add/modify entries in the `sites` section. Pay close attention to all CSS selectors. Use the optional selectors (`cookie_consent_button_selector`, `post_chat_open_button_selector`, `text_content_selector`) as needed for specific site behavior.
    *   Refine `operator_join_patterns` and `bot_indicator_phrases` in `_defaults` or add site-specific overrides for better accuracy.

## Usage

The application now runs as three separate components that communicate via Redis. You will need **three separate terminal windows** open in the project root directory.

1.  **Start Redis:**
    *   Make sure Docker Desktop is running.
    *   In one terminal, run:
        ```bash
        docker-compose up -d
        ```
    *   Leave this running. You only need to do this once unless you stop it with `docker-compose down`.

2.  **Start the Chat Service:**
    *   Open a **second terminal**.
    *   Activate the virtual environment:
        ```bash
        # Windows
        .\venv\Scripts\activate
        # macOS/Linux
        source venv/bin/activate
        ```
    *   Run the Chat Service script. This service listens for session requests from the GUI and manages the browser automation.
        ```bash
        python chat_service.py
        ```
    *   Keep this terminal running.

3.  **(Optional) Start the Telegram Bot:**
    *   If you configured the `.env` file for Telegram integration, open a **third terminal**.
    *   Activate the virtual environment.
    *   Run the Telegram Bot script. This bot handles CAPTCHA requests and operator notifications.
        ```bash
        python telegram_bot.py
        ```
    *   Keep this terminal running.
    *   **Important:** Send the `/start` command to your bot in Telegram at least once to initiate the chat if you haven't already.

4.  **Start the GUI Client:**
    *   Open a **fourth terminal** (or reuse one if not running the Telegram bot).
    *   Activate the virtual environment.
    *   Run the GUI script. This is the user interface you interact with.
        ```bash
        python gui.py
        ```

5.  **Interact with the GUI:**
    *   Select the desired website from the dropdown.
    *   Click "Начать диалог".
    *   The Chat Service (running in its terminal) will launch a Chrome browser window.
    *   Follow the status updates in the GUI.
    *   If prompted with `ACTION REQUIRED / ТРЕБУЕТСЯ ДЕЙСТВИЕ`:
        *   Switch to the browser window.
        *   Fill any required pre-chat forms and submit the form *on the website*.
        *   Switch back to the AntiChatBot GUI and click "Продолжить (после формы)".

6.  **Monitor the process:**
    *   The application will attempt to reach an operator.
    *   **If CAPTCHA appears:** (Requires Telegram Bot running) You will receive the image in Telegram. Reply to the bot with the text from the image.
    *   **If operator connects:** (Requires Telegram Bot running) You will receive a notification in Telegram. The main GUI will also indicate success. The browser window controlled by the Chat Service will remain open.

7.  **Closing:**
    *   To stop a session, simply close the GUI window. This will send a signal to the Chat Service to attempt a clean shutdown of that specific session.
    *   If the operator was found or the GUI was closed manually, the Chat Service will leave the browser open.
    *   If the session failed (timeout, errors, operator not found without manual closure), the Chat Service will automatically close the browser for that session.
    *   To stop all components: Close the GUI window, press `Ctrl+C` in the `chat_service.py` and `telegram_bot.py` terminals, and run `docker-compose down` in the terminal where you started Redis.
