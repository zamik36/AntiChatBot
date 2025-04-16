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
*   Contains a `redis` section (`host`, `port`).
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
    *   Redis is used for communication between the GUI/ChatService and the optional Telegram Bot.
    *   The easiest way to run Redis is using Docker. Open your terminal and run:
        ```bash
        docker run --name redis-antichatbot -p 6379:6379 -d redis
        ```
    *   **Explanation:**
        *   `docker run`: Creates and starts a container.
        *   `--name redis-antichatbot`: Gives the container a specific name (you can change it).
        *   `-p 6379:6379`: Maps port 6379 on your machine to port 6379 inside the container (this is the default Redis port).
        *   `-d`: Runs the container in the background (detached mode).
        *   `redis`: Specifies the official Redis image from Docker Hub (will be downloaded if not present).
    *   **To check logs:** `docker logs redis-antichatbot`
    *   **To stop:** `docker stop redis-antichatbot`
    *   **To remove:** `docker rm redis-antichatbot` (stop it first)
    *   Ensure this Docker container is running before starting the application components.

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
    *   Review/update Redis host/port if not using defaults.
    *   Add/modify entries in the `sites` section. Pay close attention to all CSS selectors. Use the optional selectors (`cookie_consent_button_selector`, `post_chat_open_button_selector`, `text_content_selector`) as needed for specific site behavior.
    *   Refine `operator_join_patterns` and `bot_indicator_phrases` in `_defaults` or add site-specific overrides for better accuracy.

## Usage

1.  **Ensure Redis server is running.**

2.  **(If using Telegram) Start the Telegram Bot Helper:**
    *   Open a **separate terminal** in the project directory.
    *   Activate the virtual environment (`venv\Scripts\activate` or `source venv/bin/activate`).
    *   Run the bot script:
        ```bash
        python telegram_bot.py
        ```
    *   Keep this terminal running in the background.
    *   **Important:** Send the `/start` command to your bot in Telegram at least once to initiate the chat.

3.  **Start the Main Application:**
    *   Open **another terminal** in the project directory.
    *   Activate the virtual environment.
    *   Run the main script:
        ```bash
        python main.py
        ```

4.  **Interact with the GUI:**
    *   Select the desired website.
    *   Click "Начать диалог".
    *   A Chrome browser window will open.
    *   Log in to the website in the browser if necessary.
    *   Wait for the GUI prompt `ACTION REQUIRED / ТРЕБУЕТСЯ ДЕЙСТВИЕ` (if applicable for the site).
    *   Switch to the browser, fill any required pre-chat forms, and submit the form *on the website*.
    *   Switch back to the AntiChatBot GUI and click "Продолжить (после формы)".

5.  **Monitor the process:**
    *   The application will attempt to reach an operator.
    *   Status updates appear in the GUI.
    *   **If CAPTCHA appears:** You will receive the image in Telegram from your bot. Reply to the bot with the text from the image.
    *   **If operator connects:** You will receive a notification in Telegram. The browser window will remain open.

6.  **Close the application window when finished.** If the operator was not found, the browser will close automatically. If the operator *was* found, you need to close the browser manually.
