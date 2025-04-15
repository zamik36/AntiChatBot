# AntiChatBot

## Description

AntiChatBot is a Python desktop application designed to automate the initial interaction phase with website chat widgets. It aims to bypass automated bot responses and directly request a connection with a human operator. The application uses Selenium for web automation and a configuration file (`config.json`) to manage settings for different target websites.

## Features

*   **Graphical User Interface (GUI):** Built with Tkinter, allowing users to select a target website and monitor the process.
*   **Configuration Driven:** Uses a `config.json` file to define site-specific URLs, CSS selectors for chat elements, bot identification phrases, and operator request messages.
*   **Web Automation:** Leverages Selenium to interact with web pages, open chat widgets, and send messages.
*   **Human Interaction Emulation:** Includes basic emulation of human behavior like scrolling and mouse movements to potentially avoid detection.
*   **Bot Bypass Logic:** Attempts to identify bot messages based on configured phrases and sends predefined messages to request a human operator.
*   **Manual Step Handling:** Pauses execution to allow the user to manually fill in required chat initiation forms (like name, email) before proceeding automatically.

## How it Works

1.  The application starts by loading configurations from `config.json`.
2.  The main GUI window appears, allowing the user to select a target website from the configured list.
3.  Upon clicking "Начать диалог" (Start Dialogue), the application launches a web browser using Selenium.
4.  It navigates to the specified login/chat page for the selected site.
5.  It waits for the initial chat elements to appear and potentially for the user to log in if necessary.
6.  It interacts with the chat widget to initiate the conversation (e.g., clicking the chat button).
7.  **User Interaction Required:** The application signals the user via the GUI (`---> ДЕЙСТВИЕ ПОЛЬЗОВАТЕЛЯ:`) to manually fill in any required pre-chat forms in the browser window.
8.  After the user completes the form and clicks "Продолжить выполнение" (Continue Execution) in the GUI, the automation resumes.
9.  The application sends an initial message (e.g., "Здравствуйте!").
10. It enters a loop, waiting for responses, checking if they are from a bot or a human operator (based on `config.json` patterns).
11. If a bot response is detected, it sends a configured message requesting a human operator.
12. This loop continues for a set number of attempts or until an operator connection is detected.
13. Status updates are displayed in the GUI throughout the process.

## Configuration (`config.json`)

The `config.json` file is crucial for the application's operation. It contains a JSON object where each key is a site name (which appears in the GUI dropdown). The value for each site is another object containing:

*   `login_url`: The URL of the page where the chat widget is located or where login might be required.
*   `selectors`: CSS selectors for key chat elements (input field, send button, message area, initial chat button, etc.). **These need to be accurate for each target site.**
*   `bot_indicator_phrases`: A list of phrases commonly used by the site's chatbot.
*   `operator_join_patterns`: A list of phrases indicating a human operator has joined the chat.
*   `response_templates`: A list of messages the application can send to request an operator.
*   `emulation_options`: Flags to enable/disable human emulation features (scrolling, mouse movement).
*   *(Potentially other site-specific details)*

**Note:** You **must** carefully inspect each target website's chat implementation and update the selectors and phrases in `config.json` accordingly for the automation to work correctly.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd AntiChatBot
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Install WebDriver:** Download the appropriate WebDriver for the browser you intend to use (e.g., ChromeDriver for Google Chrome) and ensure it's accessible in your system's PATH or place it in the project directory. The current implementation likely uses a specific driver (check `web_automator.py`), ensure it matches your setup.
5.  **Configure `config.json`:** Edit the `config.json` file, adding or modifying entries for the websites you want to target. Pay close attention to the CSS selectors and identifying phrases.

## Usage

1.  Ensure your virtual environment is activated.
2.  Run the application:
    ```bash
    python main.py
    ```
3.  Select the desired website from the dropdown menu in the GUI.
4.  Click the "Начать диалог" button.
5.  A browser window will open and navigate to the target site.
6.  Follow the instructions displayed in the application's status area. When prompted (`---> ДЕЙСТВИЕ ПОЛЬЗОВАТЕЛЯ:`), switch to the browser window, fill out any necessary forms, and click the relevant button on the *website* to start the chat.
7.  Switch back to the AntiChatBot application and click the "Продолжить выполнение" button.
8.  The application will then attempt to interact with the chat to reach a human operator. Monitor the status updates in the GUI.
