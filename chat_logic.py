# chat_logic.py
import time
import random
import re
import traceback # Импортируем для вывода ошибок
import web_automator # Импортируем наш модуль для работы с браузером
# Добавляем импорт Event для type hinting (опционально, но полезно)
from threading import Event

# ==================================
# Вспомогательные функции
# ==================================

def perform_random_emulation(driver, site_config, emulation_options):
    """Выполняет случайное действие эмуляции, если оно включено в конфиге."""
    # --- Исправлены отступы ---
    if not emulation_options:
        return # Нет настроек эмуляции

    possible_actions = []
    if emulation_options.get("enable_scrolling", False):
        possible_actions.append("scroll_down")
        possible_actions.append("scroll_up")
    if emulation_options.get("enable_mouse_movement_to_elements", False):
        possible_actions.append("move_mouse_input")
        possible_actions.append("move_mouse_messages")

    if not possible_actions:
        return # Эмуляция выключена

    action = random.choice(possible_actions)
    print(f"Эмуляция: Выполнение действия '{action}'...")

    if action == "scroll_down":
        web_automator.scroll_page(driver, random.randint(200, 500), 'down')
    elif action == "scroll_up":
        # Прокручиваем вверх, только если не у самого верха
        if driver.execute_script("return window.pageYOffset;") > 100:
             web_automator.scroll_page(driver, random.randint(200, 500), 'up')
        else:
            print("Эмуляция: Уже наверху, прокрутка вверх пропущена.")
    elif action == "move_mouse_input":
        selector = site_config.get('selectors', {}).get('input_field')
        if selector and selector != "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
            web_automator.move_mouse_to_element_safe(driver, selector, "поле ввода")
    elif action == "move_mouse_messages":
        selector = site_config.get('selectors', {}).get('messages_area')
        if selector and selector != "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
             web_automator.move_mouse_to_element_safe(driver, selector, "область сообщений")

    time.sleep(random.uniform(1.0, 2.5)) # Дополнительная пауза после эмуляции

def is_operator_joined(message, site_config):
    """
    Улучшенная проверка на оператора: сначала ищет явные маркеры бота,
    затем ищет паттерны присоединения оператора.
    """
    # --- Исправлены отступы ---
    if message is None:
        return False

    message_lower = message.lower() # Сравниваем в нижнем регистре

    # 1. Проверка на негативные маркеры (явные признаки бота)
    bot_indicators = site_config.get('bot_indicator_phrases', [])
    for phrase in bot_indicators:
        if phrase.lower() in message_lower:
            print(f"[CheckOperator] Обнаружен маркер бота: '{phrase}'")
            return False # Точно бот

    # 2. Если негативных маркеров нет, ищем позитивные паттерны присоединения
    operator_patterns = site_config.get('operator_join_patterns', [])
    for pattern in operator_patterns:
        # Используем простое вхождение строки или можно добавить поддержку regex
        # Для простоты пока используем 'in'
        # Если нужен regex: if re.search(pattern.lower(), message_lower):
        if pattern.lower() in message_lower:
            print(f"[CheckOperator] Обнаружен паттерн присоединения оператора: '{pattern}'")
            return True # Похоже на оператора

    # 3. Если ни один паттерн не сработал
    print("[CheckOperator] Сообщение не похоже ни на явного бота, ни на присоединение оператора.")
    return False

def choose_response(site_config):
    """Выбирает случайный шаблон ответа для запроса оператора."""
    # --- Исправлены отступы ---
    templates = site_config.get('response_templates', ["нужен оператор"])
    return random.choice(templates)

# ==================================
# Основная функция сессии чата
# ==================================
def run_chat_session(site_name, config, status_callback, user_ready_event: Event):
    """
    Основная функция, управляющая сессией чата.
    """
    # --- Исправлены отступы ---
    # Инициализация переменных ДО блока try
    driver = None
    site_config = None # Инициализируем здесь как None
    emulation_options = None # Инициализируем здесь как None
    last_message_text = None
    last_messages_count = 0
    operator_found = False # Флаг успешного подключения оператора
    attempts = 0 # Счетчик попыток запроса оператора
    max_attempts = 10 # Максимальное количество попыток

    try:
        # --- 1. Загрузка конфигурации ---
        status_callback(f"Загрузка конфигурации для: {site_name}")
        site_config = config.get(site_name) # Получаем конфиг для сайта

        # --- ПРОВЕРКА КОНФИГУРАЦИИ ---
        if not site_config:
            status_callback(f"Ошибка: Конфигурация для '{site_name}' не найдена в config.json.")
            print(f"### Ошибка: Конфигурация для '{site_name}' не найдена.")
            return # Завершаем выполнение этой сессии

        # --- ПОЛУЧЕНИЕ ОПЦИЙ ЭМУЛЯЦИИ (ПОСЛЕ успешной загрузки site_config) ---
        # !!! ИСПРАВЛЕНО: Эта строка теперь на правильном месте !!!
        emulation_options = site_config.get('emulation_options')
        status_callback(f"Конфигурация для '{site_name}' загружена.")
        print(f"Конфигурация для '{site_name}' загружена. Опции эмуляции: {emulation_options}")

        # --- 2. Инициализация драйвера ---
        status_callback("Инициализация веб-драйвера...")
        driver = web_automator.init_driver()
        if not driver:
            status_callback("Критическая ошибка: Не удалось инициализировать драйвер.")
            return

        # --- 3. Переход на страницу ---
        login_url = site_config.get('login_url', 'URL не указан')
        status_callback(f"Переход на страницу: {login_url}")
        if not web_automator.navigate_to_login(driver, site_config):
            status_callback(f"Ошибка: Не удалось перейти на страницу {login_url}.")
            raise Exception("Navigation failed") # Используем raise для перехода в finally

        # --- 4. Ожидание входа пользователя (ЕСЛИ ТРЕБУЕТСЯ) и КЛИК по ПЕРВОЙ кнопке чата ---
        status_callback("Ожидание первой кнопки чата (и входа, если нужно)...")
        if not web_automator.wait_for_login_and_open_chat(driver, site_config, status_callback):
            raise Exception("Chat open failed (initial button or login)")

        # --- 4.5 Ожидание заполнения формы пользователем ---
        status_callback("WAITING_FOR_FORM_INPUT") # Сигнал в GUI
        print("Программа ожидает, пока пользователь заполнит форму в браузере и нажмет 'Продолжить выполнение' в программе...")
        user_ready_event.wait() # Блокируем поток здесь
        status_callback("Продолжение выполнения после подтверждения пользователя...")
        print("Пользователь подтвердил готовность, продолжаем...")
        status_callback("Ожидание инициализации интерфейса чата (10 сек)...")
        time.sleep(10)

        # --- 5. Начало АВТОМАТИЧЕСКОГО диалога ---
        status_callback("Отправка первого автоматического сообщения...")
        perform_random_emulation(driver, site_config, emulation_options) # Эмуляция перед отправкой
        if not web_automator.send_message(driver, site_config, "Здравствуйте!"):
             status_callback("Предупреждение: Не удалось отправить первое сообщение 'Здравствуйте!'. Продолжаем...")
             print("### Предупреждение: Не удалось отправить первое сообщение.")
             # Не критично, продолжаем попытки общаться
        else:
            last_messages_count += 1 # Считаем свое сообщение

        # --- 6. Цикл общения с ботом ---
        status_callback("Начало цикла общения с ботом...")
        print("--- Начало основного цикла ---")

        while attempts < max_attempts and not operator_found:
            current_attempt_number = attempts + 1
            status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Ожидание ответа + эмуляция...")
            print(f"\n--- Итерация цикла {current_attempt_number}/{max_attempts} ---")

            # --- 6.1 Ожидание с эмуляцией ---
            base_wait_time = random.uniform(8, 15) # Уменьшим немного макс. ожидание
            print(f"Базовое ожидание {base_wait_time:.1f} секунд...")
            wait_start_time = time.time()
            while time.time() - wait_start_time < base_wait_time:
                remaining_time = base_wait_time - (time.time() - wait_start_time)
                if random.random() < 0.4: # Шанс 40% на эмуляцию
                    perform_random_emulation(driver, site_config, emulation_options)

                sleep_duration = min(random.uniform(2, 5), remaining_time)
                if sleep_duration > 0.1: # Не спим слишком мало
                    time.sleep(sleep_duration)
                if time.time() - wait_start_time >= base_wait_time:
                    break # Время вышло

            # --- 6.2 Чтение ответа из чата ---
            # !!! ИСПРАВЛЕНО: Этот блок теперь ВНУТРИ цикла while !!!
            status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Чтение ответа...")
            print("Чтение ответа из чата...")
            new_message, new_count = web_automator.get_last_message(driver, site_config, last_messages_count)

            if new_message is not None:
                # Новое сообщение получено
                last_message_text = new_message
                last_messages_count = new_count
                status_callback(f"Бот/Оператор: {last_message_text[:100]}...") # GUI статус
                print(f"Получено ({last_messages_count}): {last_message_text}") # Консоль лог

                # Проверка на оператора
                if is_operator_joined(last_message_text, site_config):
                    operator_found = True # Устанавливаем флаг
                    status_callback("УСПЕХ: Оператор подключился!")
                    print(">>> Обнаружено подключение оператора!")
                    # Цикл завершится сам на следующей проверке условия while
                else:
                    # Если это бот, готовим ответ
                    status_callback("Ответил бот. Отправка запроса оператора...")
                    print("Ответил бот, готовим запрос оператора...")
                    response = choose_response(site_config)

                    # Эмуляция перед отправкой ответа
                    perform_random_emulation(driver, site_config, emulation_options)

                    # Отправляем ответ боту
                    print(f"Отправка сообщения: '{response}'")
                    if web_automator.send_message(driver, site_config, response):
                        # Успешная отправка
                        print(f"Запрос оператора '{response}' успешно отправлен.")
                        last_messages_count += 1 # Учитываем свое отправленное сообщение
                        attempts += 1 # Увеличиваем счетчик УСПЕШНЫХ попыток запроса
                    else:
                        # Ошибка отправки
                        status_callback("Ошибка: Не удалось отправить сообщение боту. Пауза 5 сек...")
                        print("### Ошибка отправки сообщения боту.")
                        time.sleep(5) # Пауза перед следующей попыткой цикла
            else:
                # Новых сообщений нет или ошибка чтения
                status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Новых сообщений нет. Пауза 10 сек...")
                print("Новых сообщений не обнаружено, ждем 10 секунд...")
                time.sleep(10) # Ждем еще перед следующей попыткой чтения
            # --- Конец блока обработки сообщения ---
        # --- Конец цикла while ---

        # --- 7. Завершение после цикла ---
        print("--- Основной цикл завершен ---")
        if not operator_found:
            status_callback(f"Завершено после {max_attempts} попыток. Оператор НЕ подключился.")
            print(f"Завершено после {max_attempts} попыток. Оператор НЕ подключился.")
        else:
             status_callback("Работа с чатом завершена (оператор был найден).")
             print("Работа с чатом завершена (оператор был найден).")

    except Exception as e:
        status_callback(f"Критическая ошибка в процессе: {e}")
        print(f"### Критическая ошибка в run_chat_session: {e}")
        # Выводим полную трассировку ошибки для детальной диагностики
        traceback.print_exc()

    finally:
        # Гарантированно закрываем браузер
        status_callback("Завершение сессии, закрытие браузера...")
        print("Блок finally: закрытие драйвера...")
        if driver: # Проверяем, что драйвер был создан перед закрытием
             web_automator.close_driver(driver)
        status_callback("--- Сеанс завершен ---") # Финальное сообщение
        print("--- Сеанс чата завершен ---")