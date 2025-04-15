# chat_logic.py
import time
import random
import re
import traceback # Импортируем для вывода ошибок
import web_automator # Импортируем наш модуль для работы с браузером
# Добавляем импорт Event для type hinting (опционально, но полезно)
from threading import Event
import redis

# --- Каналы Redis (должны совпадать с telegram_bot.py) ---
CAPTCHA_REQUEST_CHANNEL = "antichatbot:captcha_request"
CAPTCHA_SOLUTION_CHANNEL = "antichatbot:captcha_solution"
OPERATOR_NOTIFY_CHANNEL = "antichatbot:operator_notify"

# ==================================
# Вспомогательные функции
# ==================================

def perform_random_emulation(driver, site_config, emulation_options):
    """Выполняет случайное действие эмуляции, если оно включено в конфиге."""
    if not emulation_options:
        return

    possible_actions = []
    selectors = site_config.get('selectors', {})
    if emulation_options.get("enable_scrolling", False):
        possible_actions.append("scroll_down")
        possible_actions.append("scroll_up")
    if emulation_options.get("enable_mouse_movement_to_elements", False):
        if selectors.get('input_field'):
            possible_actions.append("move_mouse_input")
        if selectors.get('messages_area'):
             possible_actions.append("move_mouse_messages")

    if not possible_actions:
        return

    action = random.choice(possible_actions)
    # print(f"Эмуляция: Выполнение действия '{action}'...") # Лог убран

    try:
        if action == "scroll_down":
            web_automator.scroll_page(driver, random.randint(200, 500), 'down')
        elif action == "scroll_up":
            if driver.execute_script("return window.pageYOffset;") > 100:
                 web_automator.scroll_page(driver, random.randint(200, 500), 'up')
            # else: print("Эмуляция: Уже наверху, скролл вверх пропущен.")
        elif action == "move_mouse_input":
            web_automator.move_mouse_to_element_safe(driver, selectors.get('input_field'), "поле ввода")
        elif action == "move_mouse_messages":
             web_automator.move_mouse_to_element_safe(driver, selectors.get('messages_area'), "область сообщений")
        time.sleep(random.uniform(0.8, 2.0))
    except Exception as e:
         print(f"Ошибка во время эмуляции ('{action}'): {e}")

def is_operator_joined(message, site_config):
    """Проверяет, является ли сообщение признаком подключения оператора."""
    if message is None:
        return False
    message_lower = message.lower()

    # Сначала проверяем на явные фразы бота (негативные маркеры)
    bot_indicators = site_config.get('bot_indicator_phrases', [])
    for phrase in bot_indicators:
        if phrase.lower() in message_lower:
            # print(f"[CheckOperator] Обнаружен маркер бота: '{phrase}'")
            return False # Точно бот

    # Если не бот, ищем паттерны подключения оператора (позитивные маркеры)
    operator_patterns = site_config.get('operator_join_patterns', [])
    for pattern in operator_patterns:
        # Используем regex для более гибкого поиска (например, "оператор .* на связи")
        try:
             if re.search(pattern.lower(), message_lower):
                 print(f"[CheckOperator] Обнаружен паттерн оператора: '{pattern}'")
                 return True # Похоже на оператора
        except re.error as e:
            print(f"[CheckOperator] Ошибка regex в паттерне '{pattern}': {e}")
            # Можно просто сравнить как строку в случае ошибки regex
            if pattern.lower() in message_lower:
                 print(f"[CheckOperator] Обнаружен паттерн оператора (как строка): '{pattern}'")
                 return True

    # print("[CheckOperator] Сообщение не похоже ни на бота, ни на оператора.")
    return False

def choose_response(site_config):
    """Выбирает случайный шаблон ответа для запроса оператора."""
    templates = site_config.get('response_templates', ["нужен оператор"])
    return random.choice(templates)

def choose_unique_response(site_config, used_responses):
    """Выбирает случайный, еще не использованный шаблон ответа.
       Если все использованы, сбрасывает список использованных и выбирает снова.
    """
    all_templates = site_config.get('response_templates', ["нужен оператор"])
    if not all_templates:
        return "нужен оператор"

    # Преобразуем в множество для быстрого поиска
    available_templates = list(set(all_templates) - used_responses)

    if not available_templates:
        print("Все шаблоны ответов использованы. Начинаем цикл заново.")
        used_responses.clear() # Сбрасываем множество использованных
        chosen_response = random.choice(all_templates)
    else:
        chosen_response = random.choice(available_templates)

    return chosen_response

def wait_for_captcha_solution(redis_client, pubsub, timeout=180):
    """Ожидает решения капчи из Redis канала.
       Возвращает решение (строку) или None при таймауте.
    """
    print(f"Ожидание решения капчи из Telegram (канал: {CAPTCHA_SOLUTION_CHANNEL}, таймаут: {timeout} сек)...", flush=True)
    start_time = time.time()
    while time.time() - start_time < timeout:
        message = pubsub.get_message(timeout=1.0) # Проверяем раз в секунду
        if message and message['type'] == 'message':
            solution = message['data']
            print(f"Получено решение капчи: '{solution}'")
            return solution
        # Небольшая пауза, чтобы не грузить CPU
        time.sleep(0.1)
    print("Таймаут ожидания решения капчи.")
    return None

# ==================================
# Основная функция сессии чата
# ==================================
# Добавляем redis_config в аргументы
def run_chat_session(site_name, config, status_callback, user_ready_event: Event, redis_config):
    """Основная функция, управляющая сессией чата с интеграцией Redis."""
    driver = None
    redis_client = None
    redis_pubsub = None
    site_config = None
    emulation_options = None
    last_messages_count = 0
    operator_found = False
    attempts = 0
    used_responses = set() # --- ИНИЦИАЛИЗИРУЕМ МНОЖЕСТВО ИСПОЛЬЗОВАННЫХ ОТВЕТОВ --- 

    try:
        # --- 0. Инициализация Redis --- 
        status_callback("Подключение к Redis...")
        try:
            redis_client = redis.Redis(host=redis_config['host'], port=redis_config['port'], decode_responses=True)
            redis_client.ping()
            redis_pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
            redis_pubsub.subscribe(CAPTCHA_SOLUTION_CHANNEL) # Подписываемся на канал с решениями капчи
            print(f"Успешное подключение к Redis {redis_config['host']}:{redis_config['port']} и подписка на {CAPTCHA_SOLUTION_CHANNEL}")
            status_callback("Подключено к Redis.")
        except Exception as e:
            status_callback(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Redis ({redis_config['host']}:{redis_config['port']}): {e}")
            print(f"### Критическая ошибка подключения к Redis: {e}")
            return # Не можем продолжать без Redis

        # --- 1. Загрузка конфигурации сайта --- 
        status_callback(f"Загрузка конфигурации для: {site_name}")
        site_config = config.get(site_name)
        if not site_config:
            status_callback(f"КРИТИЧЕСКАЯ ОШИБКА: Конфигурация для '{site_name}' не найдена.")
            return

        # --- Получаем параметры ПОСЛЕ проверки site_config ---
        emulation_options = site_config.get('emulation_options')
        # Переносим присвоение max_attempts сюда
        max_attempts = site_config.get("max_operator_request_attempts", 15)
        status_callback(f"Конфигурация для '{site_name}' загружена (макс. попыток: {max_attempts}).")

        # --- 2. Инициализация драйвера --- 
        status_callback("Инициализация веб-драйвера...")
        driver = web_automator.init_driver()
        if not driver:
            status_callback("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать драйвер.")
            return

        # --- 3. Переход на страницу --- 
        login_url = site_config.get('login_url', 'URL не указан')
        status_callback(f"Переход на страницу: {login_url}")
        if not web_automator.navigate_to_login(driver, site_config):
            raise Exception(f"Ошибка: Не удалось перейти на страницу {login_url}.")

        # --- 4. Открытие чата (и вход, если нужно) --- 
        status_callback("Ожидание кнопки чата...")
        if not web_automator.wait_for_login_and_open_chat(driver, site_config, status_callback):
             # Ошибка уже выведена в status_callback из wait_for_login_and_open_chat
             raise Exception("Ошибка открытия чата или входа.")

        # --- 4.5 Ожидание действий пользователя (форма) --- 
        status_callback("WAITING_FOR_FORM_INPUT") # Сигнал в GUI
        print("Ожидание заполнения формы пользователем и нажатия 'Продолжить' в GUI...")
        user_ready_event.wait() # Блокировка до сигнала из GUI
        status_callback("Продолжение выполнения после подтверждения пользователя...")
        print("Пользователь подтвердил готовность.")
        status_callback("Пауза 10 сек для инициализации интерфейса чата...")
        time.sleep(10)

        # --- 5. Начало диалога --- 
        status_callback("Отправка первого автоматического сообщения ('Здравствуйте!')...")
        perform_random_emulation(driver, site_config, emulation_options)
        if web_automator.send_message(driver, site_config, "Здравствуйте!"):
            last_messages_count += 1
        else:
            status_callback("Предупреждение: Не удалось отправить 'Здравствуйте!'. Продолжаем...")
            print("### Предупреждение: Не удалось отправить первое сообщение.")

        # --- 6. Цикл общения --- 
        status_callback("Начало основного цикла общения...")
        print("--- Начало основного цикла --- ")

        while attempts < max_attempts and not operator_found:
            current_attempt_number = attempts + 1
            status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Ожидание...")
            print(f"\n--- Итерация {current_attempt_number}/{max_attempts} ---")

            # --- 6.1 Ожидание + Эмуляция (УМЕНЬШЕНО ВРЕМЯ) --- 
            base_wait_time = random.uniform(4, 8) # Уменьшено время ожидания
            print(f"Ожидание ~{base_wait_time:.1f} сек...")
            wait_start_time = time.time()
            while time.time() - wait_start_time < base_wait_time:
                remaining_time = base_wait_time - (time.time() - wait_start_time)
                if random.random() < 0.4: # Шанс эмуляции
                    perform_random_emulation(driver, site_config, emulation_options)
                sleep_duration = min(random.uniform(1.0, 2.5), remaining_time) # Уменьшены паузы
                if sleep_duration > 0.1:
                    time.sleep(sleep_duration)
                if time.time() - wait_start_time >= base_wait_time:
                    break

            # --- 6.2 Чтение ответа --- 
            status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Чтение ответа...")
            print("Чтение ответа из чата...")
            # get_last_message теперь возвращает СПИСОК текстов
            list_of_new_texts, captcha_base64, new_count = web_automator.get_last_message(driver, site_config, last_messages_count)

            # --- 6.3 Обработка КАПЧИ (приоритет над проверкой оператора) --- 
            if captcha_base64:
                status_callback("❗ Обнаружена КАПЧА! Отправка запроса в Telegram...")
                print("*** Обнаружена КАПЧА! Отправка запроса в Redis... ***")
                try:
                    redis_client.publish(CAPTCHA_REQUEST_CHANNEL, captcha_base64)
                    status_callback("⏳ Ожидание решения капчи из Telegram...")
                    captcha_solution = wait_for_captcha_solution(redis_client, redis_pubsub)

                    if captcha_solution:
                        status_callback(f"Получено решение капчи: '{captcha_solution}'. Отправка в чат...")
                        if web_automator.send_message(driver, site_config, captcha_solution):
                            status_callback("Решение капчи отправлено.")
                            last_messages_count = new_count # Обновляем счетчик после получения капчи
                            last_messages_count += 1 # Считаем отправленное решение
                            # Сразу переходим к следующей итерации, чтобы проверить ответ после капчи
                            continue
                        else:
                            status_callback("Ошибка: Не удалось отправить решение капчи.")
                            print("### Ошибка отправки решения капчи в чат.")
                            time.sleep(5)
                            continue # Попробуем прочитать ответ еще раз
                    else:
                        status_callback("Ошибка: Таймаут ожидания решения капчи из Telegram.")
                        print("### Таймаут ожидания решения капчи.")
                        break # Прерываем цикл
                except redis.exceptions.ConnectionError as e:
                     status_callback(f"Ошибка Redis при запросе/ожидании капчи: {e}")
                     print(f"### Ошибка Redis (капча): {e}")
                     break # Прерываем цикл
                except Exception as e:
                    status_callback(f"Ошибка при обработке капчи: {e}")
                    print(f"### Ошибка обработки капчи: {e}")
                    traceback.print_exc()
                    break # Прерываем цикл
            # --- Конец обработки капчи --- 

            # --- 6.4 Обработка НОВЫХ СООБЩЕНИЙ --- 
            elif list_of_new_texts: # Проверяем, есть ли вообще новые тексты
                last_messages_count = new_count # Обновляем счетчик здесь
                print(f"Получено {len(list_of_new_texts)} новых текстовых сообщений.")
                # Показываем последнее сообщение в статусе GUI
                last_text_for_status = list_of_new_texts[-1] if list_of_new_texts[-1] is not None else "[Текст не извлечен]"
                status_callback(f"Получено: {last_text_for_status[:100]}...")

                # --- ПРОВЕРКА НА ОПЕРАТОРА по ВСЕМ новым сообщениям ---
                operator_detected_in_batch = False
                for msg_text in list_of_new_texts:
                    if msg_text is not None: # Проверяем только если текст извлечен
                        if is_operator_joined(msg_text, site_config):
                            operator_detected_in_batch = True
                            print(f">>> Маркер оператора найден в сообщении: '{msg_text[:60]}...' <<< ")
                            break # Нашли оператора, выходим из цикла проверки текстов
                
                if operator_detected_in_batch:
                    operator_found = True # Устанавливаем главный флаг
                    status_callback("✅ УСПЕХ: Оператор подключился!")
                    # Отправляем уведомление в Telegram
                    try:
                        redis_client.publish(OPERATOR_NOTIFY_CHANNEL, site_name)
                        print(f"Уведомление об операторе ({site_name}) отправлено в Redis.")
                    except Exception as e:
                        print(f"### Ошибка отправки уведомления об операторе в Redis: {e}")
                    # Цикл while завершится сам
                else:
                    # Оператор НЕ найден ни в одном из новых сообщений
                    status_callback("Ответил бот. Отправка запроса оператора...")
                    # --- ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ ВЫБОРА ОТВЕТА ---
                    response = choose_unique_response(site_config, used_responses)
                    perform_random_emulation(driver, site_config, emulation_options)
                    print(f"Отправка запроса оператора: '{response}'")
                    if web_automator.send_message(driver, site_config, response):
                        last_messages_count += 1 # Учитываем свое сообщение
                        used_responses.add(response) # --- ДОБАВЛЯЕМ ОТВЕТ В ИСПОЛЬЗОВАННЫЕ ---
                        attempts += 1
                    else:
                        status_callback("Ошибка отправки запроса оператора. Пауза 5 сек...")
                        print("### Ошибка отправки запроса оператора.")
                        time.sleep(5)
            else:
                # Новых сообщений/капчи нет
                status_callback(f"Цикл {current_attempt_number}/{max_attempts}. Новых сообщений/капчи нет. Пауза 10 сек...")
                time.sleep(10)
        # --- Конец цикла while ---

        # --- 7. Завершение --- 
        print("--- Основной цикл завершен ---")
        if not operator_found:
            status_callback(f"🏁 Завершено после {attempts}/{max_attempts} попыток. Оператор НЕ подключился.")
            print(f"Завершено после {attempts}/{max_attempts} попыток. Оператор НЕ подключился.")
            # Закрываем браузер, только если оператор НЕ найден
            if driver:
                 print("Закрытие браузера (оператор не найден)...")
                 web_automator.close_driver(driver)
                 status_callback("Браузер закрыт.")
        else:
             status_callback(f"✅ ОПЕРАТОР НАЙДЕН на '{site_name}'! Окно браузера ОСТАВЛЕНО ОТКРЫТЫМ.")
             print(f"Оператор найден на '{site_name}'. Оставляем браузер открытым.")
             # НЕ закрываем браузер

    except Exception as e:
        status_callback(f"КРИТИЧЕСКАЯ ОШИБКА в процессе: {e}")
        print(f"### КРИТИЧЕСКАЯ ОШИБКА в run_chat_session: {e} ###")
        traceback.print_exc()
        # В случае любой ошибки, стараемся закрыть браузер
        if driver:
            print("Закрытие браузера из-за ошибки...")
            web_automator.close_driver(driver)

    finally:
        # --- 8. Закрытие ТОЛЬКО сетевых ресурсов --- 
        print("--- Блок Finally: Закрытие сетевых ресурсов (Redis) ---")
        if redis_pubsub:
            try:
                redis_pubsub.unsubscribe()
                redis_pubsub.close()
                print("Подписка Redis закрыта.")
            except Exception as e:
                print(f"Ошибка при закрытии подписки Redis: {e}")
        if redis_client:
            try:
                redis_client.close()
                print("Соединение с Redis закрыто.")
            except Exception as e:
                print(f"Ошибка при закрытии соединения Redis: {e}")
        # УБРАЛИ закрытие драйвера отсюда
        # if driver: ...
        print("--- Сессия чата полностью завершена --- ")