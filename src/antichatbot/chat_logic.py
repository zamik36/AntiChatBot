# chat_logic.py

import time
import random
import re
import traceback
# Используем относительный импорт
from . import web_automator
import redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError
import json # Возможно понадобится для загрузки конфига, если он не передается выше

# --- Каналы Redis (общие) ---
CAPTCHA_REQUEST_CHANNEL = "antichatbot:captcha_request"
CAPTCHA_SOLUTION_CHANNEL = "antichatbot:captcha_solution"
OPERATOR_NOTIFY_CHANNEL = "antichatbot:operator_notify"
# --- Шаблоны каналов Redis (специфичные для сессии) ---
SESSION_STATUS_CHANNEL_TEMPLATE = "antichatbot:session_status:{session_id}"
USER_READY_CHANNEL_TEMPLATE = "antichatbot:user_ready:{session_id}"
SESSION_CLOSE_REQUEST_TEMPLATE = "antichatbot:session_close_request:{session_id}"

# ==================================
# Вспомогательные функции (оставлены без изменений, кроме is_operator_joined)
# ==================================

def perform_random_emulation(driver, site_config, emulation_options):
    """Выполняет ТОЛЬКО СКРОЛЛИНГ, если он включен в конфиге."""
    if not emulation_options or not emulation_options.get("enable_scrolling", True):
        return

    possible_actions = ["scroll_down", "scroll_up"]
    weights = [10, 5] # Веса для скролла
    action = random.choices(possible_actions, weights=weights, k=1)[0]

    try:
        if action == "scroll_down":
            web_automator.scroll_page(driver, random.randint(200, 600), 'down')
        elif action == "scroll_up":
            if driver.execute_script("return window.pageYOffset;") > 100:
                web_automator.scroll_page(driver, random.randint(200, 600), 'up')
    except Exception as e:
        print(f"[EMULATION_ERROR] Ошибка во время эмуляции ('{action}'): {e}")

# --- ИЗМЕНЕНАЯ ФУНКЦИЯ is_operator_joined (с ДОПОЛНИТЕЛЬНЫМ ЛОГИРОВАНИЕМ И КАСКАДНОЙ ПРОВЕРКОЙ) ---
def is_operator_joined(message, site_config, config):
    """Проверяет, является ли сообщение признаком подключения оператора или явной фразой бота,
       используя каскадную проверку: сначала конфиг сайта, потом дефолты.
    """
    if message is None:
        print("[CheckOperator] Получено пустое сообщение (None). Считаем НЕ оператором.") # DEBUG
        return False

    cleaned_message = message.strip()
    message_lower = cleaned_message.lower()
    print(f"[CheckOperator DEBUG] Проверка сообщения: '{cleaned_message[:80]}...'") # DEBUG

    # --- 1. Каскадная проверка на БОТ-ИНДИКАТОРЫ (явные фразы бота) --- 
    site_bot_indicators = site_config.get('bot_indicator_phrases', None) # Получаем список сайта или None
    default_bot_indicators = config.get("_defaults", {}).get("bot_indicator_phrases", [])

    # Проверяем сначала индикаторы сайта (если они есть)
    if site_bot_indicators is not None:
        print(f"[CheckOperator DEBUG] Проверка БОТ-индикаторов сайта ({len(site_bot_indicators)} шт)") # DEBUG
        for phrase in site_bot_indicators:
            if phrase and phrase.lower() in message_lower:
                print(f"[CheckOperator] Обнаружен БОТ-индикатор сайта: '{phrase}'. Сообщение НЕ оператора.") # DEBUG
                return False # Точно бот (по правилу сайта)
    # Если индикаторы сайта не заданы ИЛИ не совпали, проверяем дефолтные
    else:
        print(f"[CheckOperator DEBUG] БОТ-индикаторы сайта не заданы или не совпали, проверка ДЕФОЛТНЫХ ({len(default_bot_indicators)} шт)") # DEBUG
        for phrase in default_bot_indicators:
             if phrase and phrase.lower() in message_lower:
                print(f"[CheckOperator] Обнаружен ДЕФОЛТНЫЙ БОТ-индикатор: '{phrase}'. Сообщение НЕ оператора.") # DEBUG
                return False # Точно бот (по дефолтному правилу)

    # --- 2. Каскадная проверка на ОПЕРАТОР-ПАТТЕРНЫ (если сообщение не было отфильтровано как бот) ---
    site_operator_patterns = site_config.get('operator_join_patterns', None)
    default_operator_patterns = config.get("_defaults", {}).get("operator_join_patterns", [])
    operator_found = False

    # Проверяем сначала паттерны сайта (если они есть)
    if site_operator_patterns is not None:
        print(f"[CheckOperator DEBUG] Проверка ОПЕРАТОР-паттернов сайта ({len(site_operator_patterns)} шт): {site_operator_patterns}") # DEBUG
        for pattern in site_operator_patterns:
            if not pattern: continue
            pattern_lower = pattern.lower()
            print(f"[CheckOperator DEBUG]   Проверка паттерна сайта: '{pattern_lower}'") # DEBUG
            try:
                if re.search(pattern_lower, message_lower):
                    print(f"[OperatorCheck] ---> СОВПАДЕНИЕ ОПЕРАТОРА (сайт, regex): '{pattern_lower}' в '{cleaned_message[:50]}...'") # DEBUG
                    operator_found = True
                    break # Нашли оператора, выходим из цикла паттернов сайта
            except re.error as e:
                print(f"[OperatorCheck] Ошибка regex в паттерне сайта '{pattern_lower}': {e}. Пробуем как строку.")
                if pattern_lower in message_lower:
                    print(f"[OperatorCheck] ---> СОВПАДЕНИЕ ОПЕРАТОРА (сайт, строка): '{pattern_lower}' в '{cleaned_message[:50]}...'") # DEBUG
                    operator_found = True
                    break # Нашли оператора
            except Exception as e:
                 print(f"[OperatorCheck] Непредвиденная ошибка при обработке паттерна сайта '{pattern_lower}': {e}")
        # Если нашли оператора по правилам сайта, возвращаем True
        if operator_found:
            return True
            
    # Если паттерны сайта не заданы ИЛИ не совпали, проверяем дефолтные
    print(f"[CheckOperator DEBUG] ОПЕРАТОР-паттерны сайта не заданы или не совпали, проверка ДЕФОЛТНЫХ ({len(default_operator_patterns)} шт): {default_operator_patterns}") # DEBUG
    for pattern in default_operator_patterns:
        if not pattern: continue
        pattern_lower = pattern.lower()
        print(f"[CheckOperator DEBUG]   Проверка ДЕФОЛТНОГО паттерна: '{pattern_lower}'") # DEBUG
        try:
            if re.search(pattern_lower, message_lower):
                print(f"[OperatorCheck] ---> СОВПАДЕНИЕ ОПЕРАТОРА (дефолт, regex): '{pattern_lower}' в '{cleaned_message[:50]}...'") # DEBUG
                operator_found = True
                break # Нашли оператора, выходим из цикла дефолтных паттернов
        except re.error as e:
            print(f"[OperatorCheck] Ошибка regex в дефолтном паттерне '{pattern_lower}': {e}. Пробуем как строку.")
            if pattern_lower in message_lower:
                print(f"[OperatorCheck] ---> СОВПАДЕНИЕ ОПЕРАТОРА (дефолт, строка): '{pattern_lower}' в '{cleaned_message[:50]}...'") # DEBUG
                operator_found = True
                break # Нашли оператора
        except Exception as e:
             print(f"[OperatorCheck] Непредвиденная ошибка при обработке дефолтного паттерна '{pattern_lower}': {e}")
        # Если нашли оператора по дефолтным правилам, выходим из цикла
        if operator_found: break 

    # Возвращаем результат после всех проверок
    if operator_found:
        return True
    else:
        print(f"[CheckOperator] Сообщение НЕ РАСПОЗНАНО как оператор (ни по сайту, ни по дефолту): '{cleaned_message[:50]}...'") # DEBUG
        return False


def choose_response(site_config):
    """Выбирает случайный шаблон ответа для запроса оператора."""
    # Эта функция больше не используется в run_chat_session
    templates = site_config.get('response_templates', ["нужен оператор"]) # Может быть, должна использовать дефолты?
    return random.choice(templates)

def choose_unique_response(all_templates, used_responses):
    """Выбирает случайный, еще не использованный шаблон ответа из предоставленного списка."""
    if not all_templates:
        return "нужен оператор"

    available_templates = list(set(all_templates) - used_responses)

    if not available_templates:
        print("Все шаблоны ответов использованы. Начинаем цикл заново.")
        used_responses.clear()
        # Используем copy() чтобы не зависеть от возможных изменений all_templates извне
        available_templates = list(all_templates).copy() 
        # Проверка на случай, если all_templates тоже был пустой
        if not available_templates:
            print("Ошибка: список шаблонов ответов пуст даже после сброса.")
            return "нужен оператор"


    chosen_response = random.choice(available_templates)

    return chosen_response

def wait_for_captcha_solution(redis_client, pubsub, timeout=180):
    """Ожидает решения капчи из Redis канала с улучшенной обработкой ошибок."""
    print(f"⏳ Ожидание решения капчи... (канал: {CAPTCHA_SOLUTION_CHANNEL}, таймаут: {timeout} сек)", flush=True)
    start_time = time.time()
    try:
        while time.time() - start_time < timeout:
            try:
                message = pubsub.get_message(timeout=1.0) # Проверяем раз в секунду
                if message and message['type'] == 'message':
                    solution = message['data']
                    print(f"✅ Получено решение капчи: '{solution}'")
                    return solution
            except TimeoutError:
                continue
            except (ConnectionError, RedisError) as e:
                print(f"❌ Ошибка соединения Redis при ожидании капчи: {e}")
                return None
            except Exception as e:
                print(f"❌ Непредвиденная ошибка в wait_for_captcha_solution (get_message): {e}")
                traceback.print_exc()
                return None
            time.sleep(0.1)
    except Exception as e:
        print(f"❌ Непредвиденная внешняя ошибка в wait_for_captcha_solution: {e}")
        traceback.print_exc()
        return None

    print("⌛ Таймаут ожидания решения капчи.")
    return None

# --- Функция ожидания сигнала готовности пользователя ---
def wait_for_user_ready(redis_client, session_id, timeout=300):
    """Ожидает сигнала готовности пользователя из Redis."""
    user_ready_channel = USER_READY_CHANNEL_TEMPLATE.format(session_id=session_id)
    pubsub = None
    print(f"[S:{session_id}] ⏳ Ожидание сигнала от пользователя... (канал: {user_ready_channel}, таймаут: {timeout} сек)")
    start_time = time.time()
    try:
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(user_ready_channel)
        while time.time() - start_time < timeout:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    print(f"[S:{session_id}] ✅ Получен сигнал готовности от пользователя.")
                    return True
            except TimeoutError:
                continue
            except (ConnectionError, RedisError) as e:
                print(f"[S:{session_id}] ❌ Ошибка Redis при ожидании сигнала: {e}")
                return False
            time.sleep(0.1)
    except Exception as e:
        print(f"[S:{session_id}] ❌ Непредвиденная ошибка в wait_for_user_ready: {e}")
        traceback.print_exc()
        return False
    finally:
        if pubsub:
            try:
                pubsub.unsubscribe(user_ready_channel)
                pubsub.close()
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки user_ready: {e}")

    print(f"[S:{session_id}] ⌛ Таймаут ожидания сигнала от пользователя.")
    return False


# ==================================
# Основная функция сессии чата (ИЗМЕНЕНА)
# ==================================
def run_chat_session(site_name, config, session_id, redis_config):
    """Основная функция, управляющая сессией чата с публикацией статуса в Redis."""
    driver = None
    redis_client = None
    redis_pubsub_captcha = None
    redis_pubsub_close = None
    site_config = None
    emulation_options = None
    last_known_messages_count = 0
    operator_found = False
    gui_closed = False # Флаг, что закрытие инициировано из GUI
    attempts = 0
    used_responses = set()
    status_channel = SESSION_STATUS_CHANNEL_TEMPLATE.format(session_id=session_id)
    close_channel = SESSION_CLOSE_REQUEST_TEMPLATE.format(session_id=session_id)

    # --- Определяем список шаблонов ответов ---
    default_templates = config.get("_defaults", {}).get("response_templates", ["нужен оператор"])
    site_response_templates = config.get("sites", {}).get(site_name, {}).get("response_templates")
    response_templates_list = site_response_templates if site_response_templates is not None else default_templates
    if not response_templates_list: response_templates_list = ["нужен оператор"]
    print(f"[S:{session_id}] Используемые шаблоны ответов ({len(response_templates_list)} шт.): {response_templates_list[:3]}...")

    # Внутренняя функция для публикации статуса
    def publish_status(message):
        if redis_client:
            try:
                # print(f"[S:{session_id}] Публикация статуса: {message[:200]}...")
                redis_client.publish(status_channel, message)
            except (ConnectionError, TimeoutError, RedisError) as e:
                print(f"[S:{session_id}] ❌ Ошибка Redis при публикации статуса '{message[:50]}...': {e}")
            except Exception as e:
                print(f"[S:{session_id}] ❌ Неожиданная ошибка при публикации статуса '{message[:50]}...': {e}")
        else:
            print(f"[S:{session_id}] ⚠️ Пропуск публикации статуса (нет Redis клиента): {message[:50]}...")


    try:
        # --- 0. Инициализация Redis ---
        publish_status("Подключение к Redis...")
        try:
            redis_client = redis.Redis(host=redis_config['host'], port=redis_config['port'], decode_responses=True)
            redis_client.ping()
            redis_pubsub_captcha = redis_client.pubsub(ignore_subscribe_messages=True)
            redis_pubsub_captcha.subscribe(CAPTCHA_SOLUTION_CHANNEL)
            redis_pubsub_close = redis_client.pubsub(ignore_subscribe_messages=True)
            redis_pubsub_close.subscribe(close_channel)

            publish_status("Подключено к Redis.")
        except (ConnectionError, TimeoutError, RedisError) as e:
            error_msg = f"КРИТИЧЕСКАЯ ОШИБКА Redis (инициализация): {e}"
            print(f"[S:{session_id}] ### {error_msg}")
            publish_status(error_msg)
            return
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

        # Получаем emulation_options с fallback на _defaults
        default_emulation_options = config.get("_defaults", {}).get("emulation_options", {})
        # Используем site_config.get(..., default_emulation_options) чтобы пустая dict на сайте ПЕРЕОПРЕДЕЛЯЛА дефолтные
        site_emulation_options = site_config.get('emulation_options')
        emulation_options = site_emulation_options if site_emulation_options is not None else default_emulation_options

        max_attempts = site_config.get("max_operator_request_attempts", 15)

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
            publish_status(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось перейти на страницу {login_url}.")
            return


        # --- 4. Открытие чата (и вход, если нужно) ---
        publish_status("Ожидание кнопки чата...")
        if not web_automator.wait_for_login_and_open_chat(driver, site_config, publish_status):
            return


        # --- 4.5 Ожидание действий пользователя (форма) ---
        publish_status("WAITING_FOR_FORM_INPUT")
        print(f"[S:{session_id}] Ожидание сигнала готовности от пользователя через Redis...")
        if not wait_for_user_ready(redis_client, session_id):
            publish_status("КРИТИЧЕСКАЯ ОШИБКА: Таймаут или ошибка ожидания подтверждения от пользователя.")
            return

        publish_status("Продолжение выполнения после подтверждения пользователя...")
        print(f"[S:{session_id}] Пользователь подтвердил готовность.")


        # --- Эмуляция после подтверждения ---
        publish_status("Начало эмуляции действий пользователя...")
        for _ in range(random.randint(2, 4)):
            perform_random_emulation(driver, site_config, emulation_options)
            time.sleep(random.uniform(0.5, 1.5))
        publish_status("Эмуляция действий завершена.")


        publish_status("Пауза 5 сек для инициализации интерфейса чата...")
        time.sleep(5)

        # --- 5. Начало диалога ---
        publish_status("Отправка первого автоматического сообщения ('Здравствуйте!')...")
        perform_random_emulation(driver, site_config, emulation_options)
        try:
            if web_automator.send_message(driver, site_config, "Здравствуйте!"):
                last_known_messages_count += 1 # Учитываем отправленное сообщение в локальном счетчике
                publish_status("Первое сообщение 'Здравствуйте!' отправлено.")
                time.sleep(1.5)
            else:
                publish_status("Предупреждение: Не удалось отправить 'Здравствуйте!'. Продолжаем...")
                print(f"[S:{session_id}] ### Предупреждение: Не удалось отправить первое сообщение.")
        except Exception as e:
            print(f"[S:{session_id}] Ошибка при отправке первого сообщения: {e}")
            publish_status(f"Ошибка отправки первого сообщения: {e}. Продолжаем...")


        # --- 6. Цикл общения ---
        publish_status("Начало основного цикла общения...")
        print(f"[S:{session_id}] --- Начало основного цикла --- ")

        # Цикл продолжается пока не найдет оператора, не закончатся попытки
        # или пока не будет получен сигнал закрытия от GUI
        while attempts < max_attempts and not operator_found and not gui_closed:

            # Проверка сигнала закрытия в начале каждой итерации
            try:
                if redis_pubsub_close:
                    close_message = redis_pubsub_close.get_message(ignore_subscribe_messages=True, timeout=0.01)
                    if close_message and close_message['type'] == 'message':
                        publish_status("Получен сигнал закрытия от GUI. Завершение сессии...")
                        print(f"[S:{session_id}] Получен сигнал закрытия от GUI.")
                        gui_closed = True # Устанавливаем флаг
            except Exception as e:
                print(f"[S:{session_id}] Ошибка Redis при проверке сигнала закрытия: {e}")
            # Если флаг установлен, выходим немедленно из внешнего цикла
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
                # Проверка сигнала закрытия внутри ожидания для быстрой остановки
                if time.time() - loop_start_time > 0.5: # Проверять не слишком часто
                    try:
                        if redis_pubsub_close:
                            close_message_inner = redis_pubsub_close.get_message(ignore_subscribe_messages=True, timeout=0.01)
                            if close_message_inner and close_message_inner['type'] == 'message':
                                publish_status("Получен сигнал закрытия от GUI во время ожидания. Завершение...")
                                print(f"[S:{session_id}] Получен сигнал закрытия от GUI во время ожидания.")
                                gui_closed = True # Устанавливаем флаг
                                break # Выход из внутреннего while ожидания
                    except Exception:
                        pass
                    loop_start_time = time.time()

                # Если флаг установлен, выходим из внутреннего цикла
                if gui_closed: break

                # Выполняем эмуляцию и небольшую паузу
                perform_random_emulation(driver, site_config, emulation_options)
                sleep_duration = min(random.uniform(0.5, 1.5), base_wait_time - (time.time() - wait_start_time))
                if sleep_duration > 0.05: # Пауза только если осталось достаточно времени
                    time.sleep(sleep_duration)

            # Если вышли из внутреннего цикла из-за сигнала закрытия, выходим из внешнего
            if gui_closed: break


            # --- 6.2 Чтение ответа ---
            publish_status(f"Цикл {current_attempt_number}/{max_attempts}. Чтение ответа...")
            print(f"[S:{session_id}] Чтение ответа из чата...")
            try:
                # get_last_message теперь возвращает СПИСОК текстов, base64 капчи, и НОВЫЙ счетчик
                list_of_new_texts, captcha_base64, new_count = web_automator.get_last_message(driver, site_config, last_known_messages_count)
                
                # <<< ИЗМЕНЕНИЕ: Обновляем счетчик СРАЗУ ПОСЛЕ вызова get_last_message >>>
                # Это гарантирует, что следующая итерация начнется с правильного места,
                # даже если на этой итерации была обработана только капча.
                last_known_messages_count = new_count
                # <<< КОНЕЦ ИЗМЕНЕНИЯ >>>

            except Exception as e:
                print(f"[S:{session_id}] ### Критическая ошибка при вызове get_last_message: {e}")
                publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при чтении сообщений: {e}")
                traceback.print_exc()
                # Устанавливаем флаг для выхода из основного цикла (изменено с operator_found на выход при ошибке)
                # operator_found = True 
                publish_status("КРИТИЧЕСКАЯ ОШИБКА ЧТЕНИЯ СООБЩЕНИЙ. ЗАВЕРШЕНИЕ.")
                break # Выходим из основного цикла while

            # Если критическая ошибка при чтении произошла, выходим
            # (уже обработано через break выше)
            # if operator_found: break 

            # --- 6.3 Обработка КАПЧИ ---
            if captcha_base64:
                publish_status("❗ Обнаружена КАПЧА! Отправка запроса в Telegram...")
                print(f"[S:{session_id}] *** Обнаружена КАПЧА! Отправка запроса в Redis... ***")
                try:
                    # <<< ДОБАВЛЕНО ЛОГИРОВАНИЕ КАПЧИ ПЕРЕД ОТПРАВКОЙ >>>
                    captcha_len = len(captcha_base64) if captcha_base64 else 0
                    print(f"[S:{session_id} CAPTCHA_DEBUG] Длина данных капчи: {captcha_len}")
                    # Выводим начало и конец строки для проверки
                    if captcha_len > 100:
                        print(f"[S:{session_id} CAPTCHA_DEBUG] Данные капчи (начало): {captcha_base64[:50]}...")
                        print(f"[S:{session_id} CAPTCHA_DEBUG] Данные капчи (конец): ...{captcha_base64[-50:]}")
                    else:
                        print(f"[S:{session_id} CAPTCHA_DEBUG] Данные капчи (полностью): {captcha_base64}")
                    # <<< КОНЕЦ ЛОГИРОВАНИЯ >>>
                    
                    redis_client.publish(CAPTCHA_REQUEST_CHANNEL, captcha_base64)
                    publish_status("⏳ Ожидание решения капчи из Telegram...")
                    captcha_solution = wait_for_captcha_solution(redis_client, redis_pubsub_captcha)

                    if captcha_solution:
                        solution_preview = captcha_solution[:10] + '...' if len(captcha_solution) > 10 else captcha_solution
                        publish_status(f"Получено решение капчи: '{solution_preview}'. Отправка в чат...")
                        try:
                            if web_automator.send_message(driver, site_config, captcha_solution):
                                # last_known_messages_count обновится в следующей итерации через get_last_message
                                publish_status("Решение капчи отправлено.")
                                time.sleep(1.5)
                                # После отправки капчи, переходим к следующей итерации, чтобы прочитать ответ
                                continue # Переход к следующей итерации внешнего цикла
                            else:
                                publish_status("Ошибка отправки решения капчи.")
                                print(f"[S:{session_id}] ### Ошибка отправки решения капчи в чат.")
                                time.sleep(5)
                                continue # Пробуем дальше? Или break? Пока continue.
                        except Exception as send_exc:
                            publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке решения капчи: {send_exc}")
                            print(f"[S:{session_id}] ### Ошибка selenium при отправке решения капчи: {send_exc}")
                            operator_found = True # Критическая ошибка, прерываем цикл
                            break # Выходим из текущей итерации (и внешний цикл завершится)
                    else:
                        # Ошибка в wait_for_captcha_solution (таймаут или Redis error)
                        publish_status("Ошибка: Не получено решение капчи (таймаут или Redis).")
                        operator_found = True # Считаем критичным, не можем пройти капчу
                        break # Выходим из текущей итерации (и внешний цикл завершится)
                except Exception as e:
                    publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при обработке капчи: {e}")
                    print(f"[S:{session_id}] ### Ошибка обработки капчи: {e}")
                    traceback.print_exc()
                    operator_found = True # Прерываем цикл
                    break # Выходим из текущей итерации

            # Если в ходе обработки капчи произошла критическая ошибка, выходим
            if operator_found or gui_closed: break # Проверяем оба флага выхода

            # --- 6.4 Обработка НОВЫХ СООБЩЕНИЙ ---
            operator_detected_in_batch = False
            sent_specific_bot_response_this_iter = False

            if list_of_new_texts:
                print(f"[S:{session_id}] Получено {len(list_of_new_texts)} новых текстовых сообщений.")
                last_text_for_status = list_of_new_texts[-1] if list_of_new_texts and list_of_new_texts[-1] is not None else "[Текст не извлечен]"
                publish_status(f"Получено: {last_text_for_status[:100]}...")

                for msg_text in list_of_new_texts:
                    if msg_text is None: continue
                    cleaned_msg_lower = msg_text.strip().lower() # Очищаем и приводим к нижнему регистру

                    # 1. Проверка на оператора
                    if is_operator_joined(msg_text, site_config, config):
                        operator_detected_in_batch = True
                        print(f"[S:{session_id}] >>> Маркер оператора найден: '{msg_text[:60]}...' <<< ")
                        break # Выходим из цикла по сообщениям

                    # <<< НАЧАЛО НОВОЙ ЛОГИКИ: Проверка specific_bot_replies >>>
                    specific_replies = site_config.get("specific_bot_replies", [])
                    found_specific_question = False
                    for reply_config in specific_replies:
                        pattern = reply_config.get("pattern")
                        response_to_send = reply_config.get("response")
                        if pattern and response_to_send:
                            try:
                                # Ищем совпадение паттерна (без учета регистра)
                                if re.search(pattern.lower(), cleaned_msg_lower, re.IGNORECASE | re.DOTALL):
                                    print(f"[S:{session_id}] >>> Обнаружен специфический вопрос бота (pattern: '{pattern}'). Ответ: '{response_to_send}' <<< ")
                                    publish_status(f"Обнаружен спец. вопрос. Отправка '{response_to_send}'...")
                                    perform_random_emulation(driver, site_config, emulation_options)
                                    try:
                                        if web_automator.send_message(driver, site_config, response_to_send):
                                            publish_status(f"Ответ '{response_to_send}' отправлен.")
                                            time.sleep(1.5)
                                            sent_specific_bot_response_this_iter = True
                                            found_specific_question = True # Устанавливаем флаг
                                            break # Выходим из цикла по specific_replies
                                        else:
                                            publish_status(f"Ошибка отправки ответа '{response_to_send}'. Пауза 5 сек...")
                                            print(f"[S:{session_id}] ### Ошибка отправки ответа '{response_to_send}'.")
                                            time.sleep(5)
                                    except Exception as send_exc:
                                        publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке ответа '{response_to_send}': {send_exc}")
                                        print(f"[S:{session_id}] ### Ошибка selenium при отправке ответа '{response_to_send}': {send_exc}")
                                        operator_found = True # Считаем критичным
                            except re.error as e:
                                print(f"[S:{session_id}] Ошибка regex в specific_bot_replies (pattern: '{pattern}'): {e}")
                            except Exception as e:
                                print(f"[S:{session_id}] Непредвиденная ошибка при обработке specific_bot_replies: {e}")
                                traceback.print_exc()
                        # Если нашли вопрос ИЛИ оператора ИЛИ GUI закрыт, выходим из цикла по specific_replies
                        if found_specific_question or operator_detected_in_batch or operator_found or gui_closed: break
                    # Если нашли вопрос ИЛИ оператора ИЛИ GUI закрыт, выходим из цикла по сообщениям
                    if found_specific_question or operator_detected_in_batch or operator_found or gui_closed: break
                    # <<< КОНЕЦ НОВОЙ ЛОГИКИ >>>


                    # 2. Проверка на меню Yota (если не оператор и не спец.вопрос)
                    yota_menu_config = site_config.get('yota_menu_detection')
                    # Проверяем только если сайт Yota И НЕ был отправлен специфический ответ выше
                    if not sent_specific_bot_response_this_iter and site_name == "Yota" and yota_menu_config:
                        menu_pattern = yota_menu_config.get('pattern')
                        menu_response = yota_menu_config.get('response')
                        if menu_pattern and menu_response:
                            try:
                                if re.search(menu_pattern.lower(), cleaned_msg_lower, re.IGNORECASE | re.DOTALL):
                                    print(f"[S:{session_id}] >>> Обнаружен паттерн меню Yota. Ответ: '{menu_response}'. <<< ")
                                    publish_status(f"Обнаружено меню Yota. Отправка '{menu_response}'...")
                                    perform_random_emulation(driver, site_config, emulation_options)
                                    try:
                                        if web_automator.send_message(driver, site_config, menu_response):
                                            publish_status(f"Ответ '{menu_response}' для Yota отправлен.")
                                            time.sleep(1.5)
                                            sent_specific_bot_response_this_iter = True
                                            break # Нашли и отправили, выходим из цикла по сообщениям
                                        else:
                                             publish_status(f"Ошибка отправки ответа '{menu_response}' для Yota. Пауза 5 сек...")
                                             print(f"[S:{session_id}] ### Ошибка отправки ответа '{menu_response}' для Yota.")
                                             time.sleep(5)
                                    except Exception as send_exc:
                                         publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке ответа '{menu_response}' для Yota: {send_exc}")
                                         print(f"[S:{session_id}] ### Ошибка selenium при отправке ответа '{menu_response}' для Yota: {send_exc}")
                                         operator_found = True # Считаем критичным
                                # else: # Убрано логирование ненахода для чистоты
                                #      print(f"[S:{session_id}] Паттерн меню Yota не найден в сообщении: '{msg_text[:60]}...'")
                            except re.error as e:
                                print(f"[S:{session_id}] Ошибка regex в паттерне меню Yota '{menu_pattern}': {e}")
                            except Exception as e:
                                print(f"[S:{session_id}] Непредвиденная ошибка при обработке yota_menu_detection: {e}")
                                traceback.print_exc()

                    # Если нашли оператора или отправили специфический ответ (любой), выходим из цикла по сообщениям
                    if operator_detected_in_batch or sent_specific_bot_response_this_iter or operator_found or gui_closed:
                        break

            # --- Решение, что делать после обработки пакета сообщений ---
            if operator_detected_in_batch:
                operator_found = True # Устанавливаем основной флаг выхода
                publish_status("✅ УСПЕХ: Оператор подключился!")
                try: # Уведомляем другие сервисы
                    redis_client.publish(OPERATOR_NOTIFY_CHANNEL, site_name)
                    print(f"[S:{session_id}] Уведомление об операторе ({site_name}) отправлено в Redis.")
                except Exception as e:
                    print(f"[S:{session_id}] ### Ошибка Redis при отправке уведомления оператора: {e}")
                # Выходим из основного цикла while
                break

            elif sent_specific_bot_response_this_iter:
                # Если был отправлен специфический ответ боту, просто продолжаем следующую итерацию
                print(f"[S:{session_id}] Отправлен специфический ответ боту. Переход к след. итерации.")
                continue # <<< Переходим к следующему циклу while

            # <<< ИЗМЕНЕНО УСЛОВИЕ: отправляем стандартный запрос ТОЛЬКО ЕСЛИ: >>>
            # 1. Были новые сообщения от бота (list_of_new_texts не пустой)
            # 2. Не был найден оператор (operator_detected_in_batch == False)
            # 3. Не был отправлен специфический ответ (sent_specific_bot_response_this_iter == False)
            elif list_of_new_texts:
                # Если были новые сообщения, но это не оператор и не спец. вопрос/меню
                publish_status("Ответил бот (стандартный случай). Отправка запроса оператору...")
                response = choose_unique_response(response_templates_list, used_responses)
                perform_random_emulation(driver, site_config, emulation_options)
                print(f"[S:{session_id}] Отправка запроса оператора: '{response}'")
                try:
                    if web_automator.send_message(driver, site_config, response):
                        used_responses.add(response)
                        attempts += 1 # Увеличиваем попытки ТОЛЬКО при стандартном запросе
                        publish_status(f"Запрос оператора '{response}' ({current_attempt_number}/{max_attempts}) отправлен.")
                        time.sleep(1.5)
                    else:
                        publish_status("Ошибка отправки запроса оператора. Пауза 5 сек...")
                        print(f"[S:{session_id}] ### Ошибка отправки запроса оператора.")
                        time.sleep(5)
                except Exception as send_exc:
                    publish_status(f"КРИТИЧЕСКАЯ ОШИБКА при отправке запроса оператора: {send_exc}")
                    print(f"[S:{session_id}] ### Ошибка selenium при отправке запроса оператора: {send_exc}")
                    traceback.print_exc()
                    operator_found = True # Считаем критичным
                    break # Выходим из цикла while

            else: # list_of_new_texts был пуст
                publish_status(f"Цикл {current_attempt_number}/{max_attempts}. Новых сообщений/капчи нет.")
                print(f"[S:{session_id}] Нет новых сообщений или капчи. Продолжаем ожидание.")
                # Не увеличиваем attempts, если не было ответа/действия

            # Проверяем флаги выхода еще раз в конце цикла
            if operator_found or gui_closed:
                break

        # --- Конец основного цикла while ---
        print(f"[S:{session_id}] --- Основной цикл завершен --- ")
        final_message = ""
        # <<< ИЗМЕНЕНА ЛОГИКА ОПРЕДЕЛЕНИЯ ЗАКРЫТИЯ БРАУЗЕРА >>>
        browser_should_be_closed = False # По умолчанию НЕ закрываем

        if operator_found: # Оператор найден (неважно, закрыт GUI или нет)
            final_message = f"✅ Сессия успешно завершена: Оператор подключился ({attempts} попыток)."
            # browser_should_be_closed остается False
        elif not gui_closed: # Если GUI НЕ закрыт, но оператор НЕ найден (лимит или ошибка)
            final_message = f"❌ Сессия завершена: Оператор не найден ({attempts}/{max_attempts} попыток)."
            browser_should_be_closed = True # Закрываем при неудаче, если GUI не закрывали
        else: # gui_closed == True (оператор не найден, т.к. вышли бы по первому if)
            final_message = f"🏁 Сессия прервана пользователем через GUI ({attempts} попыток)."
            # browser_should_be_closed остается False, т.к. GUI закрыт
        # <<< КОНЕЦ ИЗМЕНЕННОЙ ЛОГИКИ >>>

        print(f"[S:{session_id}] {final_message}")
        publish_status(final_message)

    except Exception as e:
        # Ловим ошибки, которые могли произойти ВНЕ основного цикла
        error_msg = f"🚨 КРИТИЧЕСКАЯ ВНЕШНЯЯ ОШИБКА в процессе: {e}"
        print(f"[S:{session_id}] ### {error_msg} ###")
        traceback.print_exc()
        publish_status(error_msg)
        browser_should_be_closed = True # Всегда закрываем браузер при внешней ошибке

    finally:
        print(f"[S:{session_id}] Выполнение finally блока...")
        publish_status("Завершение сессии и очистка...")

        # Закрываем подписки Redis
        if redis_pubsub_captcha:
            try:
                redis_pubsub_captcha.unsubscribe()
                redis_pubsub_captcha.close()
                print(f"[S:{session_id}] Подписка на капчу закрыта.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки капчи: {e}")
        if redis_pubsub_close:
            try:
                redis_pubsub_close.unsubscribe()
                redis_pubsub_close.close()
                print(f"[S:{session_id}] Подписка на закрытие закрыта.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии подписки закрытия: {e}")

        # Закрываем клиент Redis
        if redis_client:
            try:
                redis_client.close()
                print(f"[S:{session_id}] Соединение с Redis закрыто.")
            except Exception as e:
                print(f"[S:{session_id}] Ошибка при закрытии соединения Redis: {e}")

        # --- ФИНАЛЬНАЯ ЛОГИКА ЗАКРЫТИЯ ДРАЙВЕРА --- 
        if browser_should_be_closed and driver:
            print(f"[S:{session_id}] Закрытие браузера (сессия завершена неудачно без закрытия GUI)...")
            web_automator.close_driver(driver)
            publish_status("Браузер закрыт (сессия завершена неудачно).")
        elif driver: # Во всех остальных случаях (оператор найден ИЛИ GUI закрыт)
            print(f"[S:{session_id}] Драйвер оставлен открытым.")
            # Не отправляем статус здесь, т.к. он уже был отправлен (успех или прервано GUI)
            # publish_status("Браузер оставлен открытым.")

        print(f"[S:{session_id}] --- Сессия чата полностью завершена --- ")