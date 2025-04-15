# chat_logic.py
import time
import random
import re
import traceback # Импортируем для вывода ошибок
# Используем относительный импорт
from . import web_automator # Импортируем наш модуль для работы с браузером
# Удаляем импорт Event
# from threading import Event
import redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError

# --- Каналы Redis (общие) ---
CAPTCHA_REQUEST_CHANNEL = "antichatbot:captcha_request"
CAPTCHA_SOLUTION_CHANNEL = "antichatbot:captcha_solution"
OPERATOR_NOTIFY_CHANNEL = "antichatbot:operator_notify"
# --- Шаблоны каналов Redis (специфичные для сессии) ---
SESSION_STATUS_CHANNEL_TEMPLATE = "antichatbot:session_status:{session_id}"
USER_READY_CHANNEL_TEMPLATE = "antichatbot:user_ready:{session_id}"
SESSION_CLOSE_REQUEST_TEMPLATE = "antichatbot:session_close_request:{session_id}"

# ==================================
# Вспомогательные функции
# ==================================

def perform_random_emulation(driver, site_config, emulation_options):
    """Выполняет ТОЛЬКО СКРОЛЛИНГ, если он включен в конфиге."""
    print("[DEBUG_EMU] Entering perform_random_emulation (SCROLL ONLY)")

    if not emulation_options or not emulation_options.get("enable_scrolling", True):
        print("[DEBUG_EMU] Scrolling disabled or no options, exiting.")
        return

    # Оставляем только скролл
    possible_actions = ["scroll_down", "scroll_up"]
    weights = [10, 5] # Веса для скролла

    # Выбираем действие с учетом весов
    action = random.choices(possible_actions, weights=weights, k=1)[0]

    print(f"[DEBUG_EMU] Chosen action: {action}")

    try:
        if action == "scroll_down":
            web_automator.scroll_page(driver, random.randint(200, 600), 'down')
        elif action == "scroll_up":
            if driver.execute_script("return window.pageYOffset;") > 100:
                 web_automator.scroll_page(driver, random.randint(200, 600), 'up')
        # Все остальные elif удалены

    except Exception as e:
         print(f"[DEBUG_EMU] Ошибка во время эмуляции ('{action}'): {e}")

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

def choose_unique_response(all_templates, used_responses):
    """Выбирает случайный, еще не использованный шаблон ответа из предоставленного списка."""
    if not all_templates:
        return "нужен оператор"

    available_templates = list(set(all_templates) - used_responses)

    if not available_templates:
        print("Все шаблоны ответов использованы. Начинаем цикл заново.")
        used_responses.clear()
        chosen_response = random.choice(all_templates)
    else:
        chosen_response = random.choice(available_templates)

    return chosen_response

def wait_for_captcha_solution(redis_client, pubsub, timeout=180):
    """Ожидает решения капчи из Redis канала с улучшенной обработкой ошибок."""
    print(f"Ожидание решения капчи из Telegram (канал: {CAPTCHA_SOLUTION_CHANNEL}, таймаут: {timeout} сек)...", flush=True)
    start_time = time.time()
    try:
        while time.time() - start_time < timeout:
            # Используем try-except вокруг get_message
            try:
                message = pubsub.get_message(timeout=1.0) # Проверяем раз в секунду
                if message and message['type'] == 'message':
                    solution = message['data']
                    print(f"Получено решение капчи: '{solution}'")
                    return solution
            except TimeoutError:
                # Это ожидаемый таймаут для get_message, просто продолжаем цикл
                continue
            except ConnectionError as e:
                print(f"Ошибка соединения Redis при ожидании решения капчи: {e}")
                return None # Ошибка соединения, не можем ждать дальше
            except RedisError as e:
                print(f"Ошибка Redis при ожидании решения капчи: {e}")
                return None # Другая ошибка Redis
            # Небольшая пауза, чтобы не грузить CPU
            time.sleep(0.1)
    except Exception as e:
        print(f"Непредвиденная ошибка в wait_for_captcha_solution: {e}")
        return None

    print("Таймаут ожидания решения капчи.")
    return None

# --- НОВАЯ Функция ожидания сигнала готовности пользователя ---
def wait_for_user_ready(redis_client, session_id, timeout=300):
    """Ожидает сигнала готовности пользователя из Redis."""
    user_ready_channel = USER_READY_CHANNEL_TEMPLATE.format(session_id=session_id)
    pubsub = None
    print(f"[S:{session_id}] Ожидание сигнала готовности от пользователя (канал: {user_ready_channel}, таймаут: {timeout} сек)...")
    start_time = time.time()
    try:
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(user_ready_channel)
        while time.time() - start_time < timeout:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    # Содержимое сообщения не так важно, сам факт получения - сигнал
                    print(f"[S:{session_id}] Получен сигнал готовности от пользователя.")
                    return True
            except TimeoutError:
                continue
            except (ConnectionError, RedisError) as e:
                print(f"[S:{session_id}] Ошибка Redis при ожидании сигнала готовности: {e}")
                return False # Ошибка, не можем ждать
            time.sleep(0.1)
    except Exception as e:
        print(f"[S:{session_id}] Непредвиденная ошибка в wait_for_user_ready: {e}")
        traceback.print_exc()
        return False
    finally:
        if pubsub:
            try:
                pubsub.unsubscribe(user_ready_channel)
                pubsub.close()
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки на user_ready: {e}")

    print(f"[S:{session_id}] Таймаут ожидания сигнала готовности от пользователя.")
    return False

# ==================================
# Основная функция сессии чата
# ==================================
# Обновляем сигнатуру: убираем status_callback, user_ready_event, добавляем session_id
def run_chat_session(site_name, config, session_id, redis_config):
    """Основная функция, управляющая сессией чата с публикацией статуса в Redis."""
    driver = None
    redis_client = None
    redis_pubsub_captcha = None
    redis_pubsub_close = None
    site_config = None
    emulation_options = None
    last_messages_count = 0
    operator_found = False
    gui_closed = False # <<< НОВЫЙ ФЛАГ ДЛЯ СИГНАЛА ЗАКРЫТИЯ
    attempts = 0
    used_responses = set()
    status_channel = SESSION_STATUS_CHANNEL_TEMPLATE.format(session_id=session_id)
    close_channel = SESSION_CLOSE_REQUEST_TEMPLATE.format(session_id=session_id)
    
    # --- Определяем список шаблонов ответов --- 
    response_templates_list = [] # Инициализируем пустым списком

    # Внутренняя функция для публикации статуса
    def publish_status(message):
        if redis_client:
            try:
                # Добавляем префикс сессии для логов
                print(f"[S:{session_id}] Публикация статуса: {message[:200]}...") # Лог с обрезкой
                redis_client.publish(status_channel, message)
            except (ConnectionError, TimeoutError, RedisError) as e:
                print(f"[S:{session_id}] Ошибка Redis при публикации статуса '{message[:50]}...': {e}")
            except Exception as e:
                 print(f"[S:{session_id}] Неожиданная ошибка при публикации статуса '{message[:50]}...': {e}")
        else:
            print(f"[S:{session_id}] Пропуск публикации статуса (нет Redis клиента): {message[:50]}...")

    try:
        # --- 0. Инициализация Redis ---
        publish_status("Подключение к Redis...")
        try:
            # Используем redis_config для подключения
            redis_client = redis.Redis(host=redis_config['host'], port=redis_config['port'], decode_responses=True)
            redis_client.ping()
            # Создаем pubsub ТОЛЬКО для капчи
            redis_pubsub_captcha = redis_client.pubsub(ignore_subscribe_messages=True)
            redis_pubsub_captcha.subscribe(CAPTCHA_SOLUTION_CHANNEL)
            print(f"[S:{session_id}] Успешное подключение к Redis {redis_config['host']}:{redis_config['port']} и подписка на {CAPTCHA_SOLUTION_CHANNEL}")

            # <<< СОЗДАЕМ И ПОДПИСЫВАЕМ PUBSUB ДЛЯ ЗАКРЫТИЯ >>>
            redis_pubsub_close = redis_client.pubsub(ignore_subscribe_messages=True)
            redis_pubsub_close.subscribe(close_channel)
            print(f"[S:{session_id}] Подписка на канал закрытия: {close_channel}")
            # <<< КОНЕЦ ПОДПИСКИ НА ЗАКРЫТИЕ >>>

            publish_status("Подключено к Redis.")
        except (ConnectionError, TimeoutError, RedisError) as e:
            error_msg = f"КРИТИЧЕСКАЯ ОШИБКА Redis (инициализация): {e}"
            print(f"[S:{session_id}] ### {error_msg}")
            publish_status(error_msg)
            return # Не можем продолжать без Redis
        except Exception as e:
            error_msg = f"КРИТИЧЕСКАЯ ОШИБКА (инициализация Redis): {e}"
            print(f"[S:{session_id}] ### {error_msg}")
            traceback.print_exc()
            publish_status(error_msg)
            return

        # --- 1. Загрузка конфигурации сайта ---
        publish_status(f"Загрузка конфигурации для: {site_name}")
        sites_section = config.get("sites", {}) 
        site_config = sites_section.get(site_name) 

        if not site_config:
            error_msg = f"КРИТИЧЕСКАЯ ОШИБКА: Конфигурация для '{site_name}' не найдена (внутри chat_logic)."
            publish_status(error_msg)
            return

        # Теперь используем site_config для получения дальнейших параметров
        # --- ИЗМЕНЕНО: Получаем emulation_options с fallback на _defaults --- 
        default_emulation_options = config.get("_defaults", {}).get("emulation_options", {}) # Берем из defaults
        emulation_options = site_config.get('emulation_options', default_emulation_options) # Берем из site_config или из defaults
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        max_attempts = site_config.get("max_operator_request_attempts", 15) # max_attempts можно брать и из defaults, но пока оставим так
        
        # --- Получаем response_templates С УЧЕТОМ _defaults --- 
        default_templates = config.get("_defaults", {}).get("response_templates", ["нужен оператор"]) # Берем из defaults или fallback
        response_templates_list = site_config.get("response_templates", default_templates) # Берем из site_config или из defaults/fallback
        if not response_templates_list: # Дополнительная проверка, если вдруг оба пустые
            response_templates_list = ["нужен оператор"]
        print(f"[S:{session_id}] Используемые шаблоны ответов ({len(response_templates_list)} шт.): {response_templates_list[:3]}...") # Лог для проверки
        # --- КОНЕЦ ПОЛУЧЕНИЯ ШАБЛОНОВ --- 
        
        publish_status(f"Конфигурация для '{site_name}' загружена (макс. попыток: {max_attempts}).")

        # --- 2. Инициализация драйвера ---
        publish_status("Инициализация веб-драйвера...")
        driver = web_automator.init_driver()
        if not driver:
            publish_status("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать драйвер.")
            return

        # --- 3. Переход на страницу ---
        login_url = site_config.get('login_url', 'URL не указан')
        publish_status(f"Переход на страницу: {login_url}")
        if not web_automator.navigate_to_login(driver, site_config):
            # Заменяем raise Exception на публикацию статуса и выход
            publish_status(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось перейти на страницу {login_url}.")
            return

        # --- 4. Открытие чата (и вход, если нужно) ---
        publish_status("Ожидание кнопки чата...")
        # Передаем publish_status вместо status_callback в wait_for_login_and_open_chat
        if not web_automator.wait_for_login_and_open_chat(driver, site_config, publish_status):
             # Ошибка уже опубликована в статусе из функции
             # publish_status("КРИТИЧЕСКАЯ ОШИБКА: Ошибка открытия чата или входа.") # Не нужно дублировать
             return # Заменяем raise Exception

        # --- 4.5 Ожидание действий пользователя (форма) ---
        publish_status("WAITING_FOR_FORM_INPUT") # Сигнал в GUI через Redis
        print(f"[S:{session_id}] Ожидание сигнала готовности от пользователя через Redis...")
        # Заменяем user_ready_event.wait() на вызов новой функции
        if not wait_for_user_ready(redis_client, session_id):
             publish_status("КРИТИЧЕСКАЯ ОШИБКА: Таймаут или ошибка ожидания подтверждения от пользователя.")
             return # Выходим, если пользователь не подтвердил или произошла ошибка

        publish_status("Продолжение выполнения после подтверждения пользователя...")
        print(f"[S:{session_id}] Пользователь подтвердил готовность.")

        # --- НОВЫЙ БЛОК: Эмуляция после подтверждения ---
        publish_status("Начало эмуляции действий пользователя...")
        for _ in range(random.randint(2, 4)): # Выполняем 2-4 случайных действия
             perform_random_emulation(driver, site_config, emulation_options)
             time.sleep(random.uniform(0.5, 1.5)) # Небольшая пауза между действиями
        publish_status("Эмуляция действий завершена.")
        # --- КОНЕЦ НОВОГО БЛОКА ---

        publish_status("Пауза 5 сек для инициализации интерфейса чата...") # Уменьшим паузу
        time.sleep(5)

        # --- 5. Начало диалога ---
        publish_status("Отправка первого автоматического сообщения ('Здравствуйте!')...")
        perform_random_emulation(driver, site_config, emulation_options)
        try:
            if web_automator.send_message(driver, site_config, "Здравствуйте!"):
                last_messages_count += 1
                publish_status("Первое сообщение 'Здравствуйте!' отправлено.")
                time.sleep(1.5) # <<< ПАУЗА ПОСЛЕ ОТПРАВКИ
            else:
                publish_status("Предупреждение: Не удалось отправить 'Здравствуйте!'. Продолжаем...")
                print(f"[S:{session_id}] ### Предупреждение: Не удалось отправить первое сообщение.")
        except Exception as e:
            print(f"[S:{session_id}] Ошибка при отправке первого сообщения: {e}")
            publish_status(f"Ошибка отправки первого сообщения: {e}. Продолжаем...")

        # --- 6. Цикл общения ---
        publish_status("Начало основного цикла общения...")
        print(f"[S:{session_id}] --- Начало основного цикла --- ")

        while attempts < max_attempts and not operator_found and not gui_closed: # <<< Добавили gui_closed в условие
            
            # <<< ПРОВЕРКА СИГНАЛА ЗАКРЫТИЯ В НАЧАЛЕ ЦИКЛА >>>
            try:
                close_message = None
                if redis_pubsub_close:
                     close_message = redis_pubsub_close.get_message(timeout=0.01)
                
                if close_message and close_message['type'] == 'message':
                    publish_status("Получен сигнал закрытия от GUI. Завершение сессии...")
                    print(f"[S:{session_id}] Получен сигнал закрытия от GUI.")
                    gui_closed = True # <<< УСТАНАВЛИВАЕМ ФЛАГ
                    # operator_found = False # --- УДАЛЕНО --- 
                    break # Выходим из основного цикла while
            except (ConnectionError, RedisError) as e:
                print(f"[S:{session_id}] Ошибка Redis при проверке сигнала закрытия: {e}")
            except Exception as e:
                print(f"[S:{session_id}] Неожиданная ошибка при проверке сигнала закрытия: {e}")
            
            # Если флаг установлен, выходим немедленно
            if gui_closed: break
            
            current_attempt_number = attempts + 1
            publish_status(f"Цикл {current_attempt_number}/{max_attempts}. Ожидание...")
            print(f"[S:{session_id}] \n--- Итерация {current_attempt_number}/{max_attempts} ---")
            
            # --- 6.1 Ожидание + Эмуляция --- 
            base_wait_time = random.uniform(4, 8)
            print(f"[S:{session_id}] Ожидание ~{base_wait_time:.1f} сек...")
            wait_start_time = time.time()
            loop_start_time = time.time()
            while time.time() - wait_start_time < base_wait_time:
                # <<< ПРОВЕРКА СИГНАЛА ЗАКРЫТИЯ ВНУТРИ ОЖИДАНИЯ >>>
                if time.time() - loop_start_time > 0.5: 
                     try:
                          close_message_inner = None
                          if redis_pubsub_close:
                              close_message_inner = redis_pubsub_close.get_message(timeout=0.01)
                          if close_message_inner and close_message_inner['type'] == 'message':
                              publish_status("Получен сигнал закрытия от GUI во время ожидания. Завершение...")
                              print(f"[S:{session_id}] Получен сигнал закрытия от GUI во время ожидания.")
                              gui_closed = True # <<< УСТАНАВЛИВАЕМ ФЛАГ
                              # operator_found = False # --- УДАЛЕНО --- 
                              # attempts = max_attempts # Это больше не нужно, т.к. флаг gui_closed остановит внешний цикл
                              break # Выход из внутреннего while ожидания
                     except Exception:
                          pass 
                     loop_start_time = time.time()
                # <<< КОНЕЦ ПРОВЕРКИ ВНУТРИ ОЖИДАНИЯ >>>
                
                # Если флаг установлен, выходим из внутреннего цикла
                if gui_closed: break 
                
                remaining_time = base_wait_time - (time.time() - wait_start_time)
                # Убираем условие random.random(), чтобы эмуляция выполнялась чаще
                perform_random_emulation(driver, site_config, emulation_options)
                sleep_duration = min(random.uniform(1.0, 2.5), remaining_time)
                if sleep_duration > 0.1:
                    time.sleep(sleep_duration)
                if time.time() - wait_start_time >= base_wait_time:
                    break
            
            # Если вышли из внутреннего цикла из-за сигнала закрытия, выходим из внешнего
            if gui_closed: break 
            
            # --- 6.2 Чтение ответа --- 
            publish_status(f"Цикл {current_attempt_number}/{max_attempts}. Чтение ответа...")
            print(f"[S:{session_id}] Чтение ответа из чата...")
            # get_last_message теперь возвращает СПИСОК текстов
            list_of_new_texts, captcha_base64, new_count = web_automator.get_last_message(driver, site_config, last_messages_count)

            # --- 6.3 Обработка КАПЧИ --- 
            if captcha_base64:
                publish_status("❗ Обнаружена КАПЧА! Отправка запроса в Telegram...")
                print(f"[S:{session_id}] *** Обнаружена КАПЧА! Отправка запроса в Redis... ***")
                try:
                    # Публикуем запрос капчи
                    redis_client.publish(CAPTCHA_REQUEST_CHANNEL, captcha_base64)
                    publish_status("⏳ Ожидание решения капчи из Telegram...")
                    # Ждем решения (с улучшенной обработкой ошибок), используя redis_pubsub_captcha
                    captcha_solution = wait_for_captcha_solution(redis_client, redis_pubsub_captcha)

                    if captcha_solution:
                        # Обрезаем длинные решения для лога/статуса
                        solution_preview = captcha_solution[:10] + '...' if len(captcha_solution) > 10 else captcha_solution
                        publish_status(f"Получено решение капчи: '{solution_preview}'. Отправка в чат...")
                        try:
                            if web_automator.send_message(driver, site_config, captcha_solution):
                                publish_status("Решение капчи отправлено.")
                                last_messages_count = new_count # Обновляем счетчик после получения капчи
                                last_messages_count += 1 # Считаем отправленное решение
                                # Сразу переходим к следующей итерации, чтобы проверить ответ после капчи
                                time.sleep(1.5) # <<< ПАУЗА ПОСЛЕ ОТПРАВКИ
                                continue
                            else:
                                publish_status("Ошибка отправки решения капчи.")
                                print(f"[S:{session_id}] ### Ошибка отправки решения капчи в чат.")
                                time.sleep(5) # Даем время на восстановление?
                                continue # Пробуем дальше? Или break? Пока continue.
                        except Exception as send_exc:
                             publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке решения капчи: {send_exc}")
                             print(f"[S:{session_id}] ### Ошибка selenium при отправке решения капчи: {send_exc}")
                             break # Критическая ошибка, прерываем цикл
                    else:
                        # Ошибка в wait_for_captcha_solution (таймаут или Redis error)
                        publish_status("Ошибка: Не получено решение капчи (таймаут или Redis).")
                        break # Прерываем цикл, т.к. не можем пройти капчу
                except (ConnectionError, TimeoutError, RedisError) as e:
                     publish_status(f"КРИТИЧЕСКАЯ ОШИБКА Redis (публикация капчи): {e}")
                     print(f"[S:{session_id}] ### Ошибка Redis при публикации запроса капчи: {e}")
                     break
                except Exception as e:
                    publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при обработке капчи: {e}")
                    print(f"[S:{session_id}] ### Ошибка обработки капчи: {e}")
                    traceback.print_exc()
                    break # Прерываем цикл
            # --- Конец обработки капчи ---

            # --- 6.4 Обработка НОВЫХ СООБЩЕНИЙ --- 
            elif list_of_new_texts: 
                last_messages_count = new_count # Обновляем счетчик здесь
                print(f"[S:{session_id}] Получено {len(list_of_new_texts)} новых текстовых сообщений.")
                # Показываем последнее сообщение в статусе GUI
                last_text_for_status = list_of_new_texts[-1] if list_of_new_texts[-1] is not None else "[Текст не извлечен]"
                publish_status(f"Получено: {last_text_for_status[:100]}...") # Ограничим длину статуса

                # --- ПРОВЕРКА НА ОПЕРАТОРА и МЕНЮ YOTA по ВСЕМ новым сообщениям ---
                operator_detected_in_batch = False
                yota_menu_detected = False # <<< Новый флаг
                for msg_text in list_of_new_texts:
                    if msg_text is not None: # Проверяем только если текст извлечен
                        # Сначала проверяем на оператора
                        if is_operator_joined(msg_text, site_config):
                            operator_detected_in_batch = True
                            print(f"[S:{session_id}] >>> Маркер оператора найден в сообщении: '{msg_text[:60]}...' <<< ")
                            break # Нашли оператора, выходим из цикла проверки текстов
                        
                        # <<< Если не оператор, проверяем на меню Yota >>>
                        if site_name == "Yota" and \
                           "Задайте свой вопрос" in msg_text and \
                           "Вопрос оператору" in msg_text and \
                           "отправьте мне цифру" in msg_text:
                            yota_menu_detected = True
                            print(f"[S:{session_id}] >>> Обнаружено меню Yota. Будет отправлена цифра 4. <<< ")
                            break # Нашли меню, выходим из цикла проверки текстов

                # --- Обработка результата проверки --- 
                if operator_detected_in_batch:
                    operator_found = True # Устанавливаем главный флаг
                    publish_status("✅ УСПЕХ: Оператор подключился!")
                    # Публикуем уведомление об операторе
                    try:
                        redis_client.publish(OPERATOR_NOTIFY_CHANNEL, site_name)
                        print(f"[S:{session_id}] Уведомление об операторе ({site_name}) отправлено в Redis.")
                    except (ConnectionError, TimeoutError, RedisError) as e:
                        print(f"[S:{session_id}] ### Ошибка Redis при отправке уведомления оператора: {e}")
                        # Не критично, продолжаем, но без уведомления
                    except Exception as e:
                         print(f"[S:{session_id}] ### Неожиданная ошибка при отправке уведомления оператора: {e}")
                    break # Выходим из основного цикла while, т.к. оператор найден
                
                elif yota_menu_detected: # <<< Обработка меню Yota >>>
                    response = "4"
                    publish_status("Обнаружено меню Yota. Отправка '4'...")
                    perform_random_emulation(driver, site_config, emulation_options)
                    print(f"[S:{session_id}] Отправка ответа на меню Yota: '{response}'")
                    try:
                        if web_automator.send_message(driver, site_config, response):
                            last_messages_count += 1 # Учитываем свое сообщение
                            # Не увеличиваем attempts и не добавляем в used_responses
                            publish_status(f"Ответ '4' для Yota отправлен.")
                            time.sleep(1.5)
                        else:
                            publish_status("Ошибка отправки ответа '4' для Yota. Пауза 5 сек...")
                            print(f"[S:{session_id}] ### Ошибка отправки ответа '4' для Yota.")
                            time.sleep(5)
                    except Exception as send_exc:
                        publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке ответа '4' для Yota: {send_exc}")
                        print(f"[S:{session_id}] ### Ошибка selenium при отправке ответа '4' для Yota: {send_exc}")
                        break # Критическая ошибка, прерываем

                else: # <<< Ни оператор, ни меню Yota >>>
                    # Оператор НЕ найден. Отправка стандартного запроса.
                    publish_status("Ответил бот (не меню Yota). Отправка запроса оператора...")
                    response = choose_unique_response(response_templates_list, used_responses)
                    # --- КОНЕЦ ИЗМЕНЕНИЯ ВЫЗОВА --- 
                    perform_random_emulation(driver, site_config, emulation_options)
                    print(f"[S:{session_id}] Отправка запроса оператора: '{response}'")
                    try:
                        if web_automator.send_message(driver, site_config, response):
                            last_messages_count += 1 # Учитываем свое сообщение
                            used_responses.add(response) # --- ДОБАВЛЯЕМ ОТВЕТ В ИСПОЛЬЗОВАННЫЕ ---
                            attempts += 1 # Увеличиваем попытки ТОЛЬКО при стандартном запросе
                            publish_status(f"Запрос оператора '{response}' отправлен.") # Подтверждение
                            time.sleep(1.5) # <<< ПАУЗА ПОСЛЕ ОТПРАВКИ
                        else:
                            publish_status("Ошибка отправки запроса оператора. Пауза 5 сек...")
                            print(f"[S:{session_id}] ### Ошибка отправки запроса оператора.")
                            time.sleep(5)
                    except Exception as send_exc:
                        publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке запроса оператора: {send_exc}")
                        print(f"[S:{session_id}] ### Ошибка selenium при отправке запроса оператора: {send_exc}")
                        break # Критическая ошибка, прерываем
            else:
                # Новых сообщений/капчи нет
                publish_status(f"Цикл {current_attempt_number}/{max_attempts}. Новых сообщений/капчи нет. Пауза 5 сек...") 
                # Используем time.sleep с проверкой сигнала закрытия
                sleep_start_time = time.time()
                while time.time() - sleep_start_time < 5:
                    # <<< ПРОВЕРКА СИГНАЛА ЗАКРЫТИЯ ВНУТРИ ПАУЗЫ >>>
                    try:
                        close_message_sleep = None
                        if redis_pubsub_close:
                             close_message_sleep = redis_pubsub_close.get_message(timeout=0.01)
                        if close_message_sleep and close_message_sleep['type'] == 'message':
                             publish_status("Получен сигнал закрытия от GUI во время паузы. Завершение...")
                             print(f"[S:{session_id}] Получен сигнал закрытия от GUI во время паузы.")
                             gui_closed = True # <<< УСТАНАВЛИВАЕМ ФЛАГ
                             # operator_found = False # --- УДАЛЕНО ---
                             # attempts = max_attempts # Это больше не нужно
                             break # Выход из цикла ожидания sleep
                    except Exception:
                        pass 
                    # Если флаг установлен, выходим из цикла паузы
                    if gui_closed: break 
                    time.sleep(0.1) 
                # Если вышли из-за сигнала, выходим из основного цикла
                if gui_closed: break 
                    
        # --- Конец цикла while ---

        # --- 7. Завершение --- 
        print(f"[S:{session_id}] --- Основной цикл завершен --- ")
        final_message = ""
        browser_should_be_closed = False # Флаг для управления закрытием браузера

        if not operator_found:
            # Определяем сообщение в зависимости от причины выхода
            if gui_closed:
                final_message = f"🏁 Сессия прервана по сигналу закрытия GUI. Браузер ОСТАВЛЕН ОТКРЫТЫМ."
                # НЕ устанавливаем browser_should_be_closed = True
            else: # Достигнут лимит попыток или была ошибка
                final_message = f"🏁 Завершено после {attempts}/{max_attempts} попыток. Оператор НЕ подключился."
                if attempts < max_attempts:
                     final_message += " (Возможно, из-за ошибки)"
                # Устанавливаем флаг закрытия браузера, ТОЛЬКО если сессия завершилась сама
                browser_should_be_closed = True 
            print(f"[S:{session_id}] {final_message}")
        else:
             # Оператор найден
             final_message = f"✅ ОПЕРАТОР НАЙДЕН на '{site_name}'! Окно браузера ОСТАВЛЕНО ОТКРЫТЫМ."
             if gui_closed: 
                  final_message += " (GUI был закрыт)"
             print(f"[S:{session_id}] {final_message}")
             # НЕ устанавливаем browser_should_be_closed = True
        
        # Публикуем финальный статус
        publish_status(final_message)

        # --- УСЛОВИЕ ЗАКРЫТИЯ БРАУЗЕРА ИЗМЕНЕНО --- 
        # Закрываем браузер только если установлен флаг browser_should_be_closed
        if browser_should_be_closed and driver:
             print(f"[S:{session_id}] Закрытие браузера (сессия завершена без оператора и без сигнала GUI)...")
             web_automator.close_driver(driver)
             # Обновим статус, если браузер был закрыт
             publish_status(final_message.replace(".", " и браузер закрыт.")) 
        # --- КОНЕЦ ИЗМЕНЕНИЯ --- 

    except Exception as e:
        # Эта ошибка ловится, если что-то упало ВНЕ основного цикла или до/после него
        error_msg = f"КРИТИЧЕСКАЯ ВНЕШНЯЯ ОШИБКА в процессе: {e}"
        publish_status(error_msg)
        print(f"[S:{session_id}] ### {error_msg} ###")
        traceback.print_exc()
        # Всегда стараемся закрыть браузер при ВНЕШНЕЙ ошибке
        if driver:
            print(f"[S:{session_id}] Закрытие браузера из-за внешней ошибки...")
            web_automator.close_driver(driver)
            publish_status("Браузер закрыт (из-за внешней ошибки).")

    finally:
        # --- 8. Закрытие ТОЛЬКО сетевых ресурсов ---
        print(f"[S:{session_id}] --- Блок Finally: Закрытие сетевых ресурсов (Redis) ---")
        if redis_pubsub_captcha: # Закрываем pubsub для капчи
            try:
                redis_pubsub_captcha.unsubscribe()
                redis_pubsub_captcha.close()
                print(f"[S:{session_id}] Подписка Redis (капча) закрыта.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки Redis (капча): {e}")
        if redis_pubsub_close:
            try:
                redis_pubsub_close.unsubscribe()
                redis_pubsub_close.close()
                print(f"[S:{session_id}] Подписка Redis (закрытие) закрыта.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки Redis (закрытие): {e}")
        if redis_client:
            try:
                redis_client.close()
                print(f"[S:{session_id}] Соединение с Redis закрыто.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии соединения Redis: {e}")
        # Финальный статус, если еще не был отправлен статус об успехе/неудаче
        # Можно добавить флаг, чтобы не дублировать, но пока просто отправим
        publish_status("Сессия завершена (блок finally).")
        print(f"[S:{session_id}] --- Сессия чата полностью завершена --- ")