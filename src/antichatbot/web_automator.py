import time
from selenium import webdriver
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, ElementClickInterceptedException,
                                    StaleElementReferenceException, NoSuchElementException,
                                    WebDriverException)
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
import re # Для поиска капчи по тексту
import os # Для работы с файловой системой
import traceback # Для печати трассировки ошибок

# --- Константы для поиска капчи ---
CAPTCHA_TEXT_MARKER = "Люди не любят капчу"
CAPTCHA_IMG_SELECTOR = 'img.VDlHi[alt="Капча"]' # Более точный селектор

# Глобальная переменная для хранения последнего отправленного сообщения
LAST_SENT_MESSAGE = None


def scroll_page(driver, scroll_amount=300, direction='down'):
    """Плавно прокручивает страницу вверх или вниз."""
    try:
        scroll_value = scroll_amount if direction == 'down' else -scroll_amount
        driver.execute_script(f"window.scrollBy(0, {scroll_value});")
        time.sleep(random.uniform(0.5, 1.5)) # Небольшая пауза после прокрутки
        return True
    except Exception as e:
        print(f"[EMU_ERROR] Ошибка при прокрутке страницы: {e}")
        return False


def move_mouse_to_element_safe(driver, selector, element_name="элемент"):
    """Плавно перемещает курсор мыши к указанному элементу."""
    if not selector or selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
        return False
    try:
        wait = WebDriverWait(driver, 5) # Короткое ожидание
        element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.pause(random.uniform(0.5, 1.2)) # Задержка
        actions.perform()
        return True
    except TimeoutException:
        return False
    except Exception as e:
        print(f"[EMU_ERROR] Ошибка при перемещении мыши к элементу {element_name}: {e}")
        return False


def move_mouse_randomly(driver):
    """Перемещает мышь в случайные координаты видимой области окна.
    Использует execute_script для симуляции события mousemove.
    """
    try:
        viewport_width = driver.execute_script("return window.innerWidth")
        viewport_height = driver.execute_script("return window.innerHeight")
        random_x = random.randint(10, max(11, viewport_width - 10))
        random_y = random.randint(10, max(11, viewport_height - 10))

        # Скрипт для симуляции события mousemove
        js_script = f"""
        var event = new MouseEvent('mousemove', {{
            bubbles: true,
            cancelable: true,
            clientX: {random_x},
            clientY: {random_y},
            view: window
        }});
        document.dispatchEvent(event);
        """
        driver.execute_script(js_script)
        time.sleep(random.uniform(0.5, 1.0)) # Небольшая пауза после симуляции
        return True
    except Exception as e:
        print(f"[EMU_ERROR] Ошибка при случайном перемещении мыши (JS method): {e}")
        return False


def perform_random_click(driver, site_config):
    """Выполняет БЕЗОПАСНЫЙ случайный клик на странице.

    Пытается кликнуть внутри элемента 'messages_area', если селектор задан,
    иначе кликает по 'body'. Это предотвращает случайные клики по кнопкам/ссылкам.
    """
    click_target_selector = site_config.get('selectors', {}).get('messages_area')
    element_name = "область сообщений"

    if not click_target_selector or click_target_selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
        click_target_selector = 'body' # Кликаем по body, если нет специфичного селектора
        element_name = "тело страницы"

    try:
        # Находим целевой элемент (messages_area или body)
        wait = WebDriverWait(driver, 5)
        element_to_click = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, click_target_selector)))

        # Кликаем на найденный элемент
        actions = ActionChains(driver)
        # Перемещаемся к элементу перед кликом (для надежности)
        actions.move_to_element(element_to_click)
        actions.pause(random.uniform(0.3, 0.8))
        actions.click(element_to_click) # Кликаем именно на этот элемент
        actions.perform()
        time.sleep(random.uniform(0.7, 1.5))
        return True
    except TimeoutException:
        return False
    except ElementClickInterceptedException:
        return False # Считаем неудачей, если клик перехвачен
    except Exception as e:
        print(f"[EMU_ERROR] Ошибка при выполнении безопасного случайного клика по {element_name}: {e}")
        return False


def init_driver():
    """Инициализирует и возвращает веб-драйвер Chrome.
    Использует webdriver-manager для автоматической загрузки драйвера.
    Предназначен для ЛОКАЛЬНОГО запуска (не в Docker).
    """
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument('--log-level=3')



        print("Инициализация Chrome WebDriver...")
        service = ChromeService(executable_path=ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("Драйвер Chrome инициализирован.")
        return driver
    except WebDriverException as e_wd:
        print(f"КРИТИЧЕСКАЯ ОШИБКА WebDriverException при инициализации драйвера: {e_wd.msg.splitlines()[0]}")
        if "session not created" in e_wd.msg:
            print("!!! Ошибка 'session not created'. Проверьте совместимость версий Chrome и ChromeDriver.")
        elif "cannot find chrome binary" in e_wd.msg.lower():
            print("!!! Ошибка 'cannot find chrome binary'. Убедитесь, что Chrome установлен корректно.")
        return None
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА инициализации драйвера: {e}")
        traceback.print_exc()
        return None


def navigate_to_login(driver, site_config):
    """Переходит на страницу входа на сайт."""
    try:
        login_url = site_config['login_url']
        driver.get(login_url)
        print(f"Переход на страницу: {login_url}")
        return True
    except Exception as e:
        print(f"Ошибка при переходе на страницу входа {site_config.get('login_url', 'Не указан')}: {e}")
        return False


def click_button_safe(driver, selector, button_name, wait_time=10):
    """Ожидает, находит и кликает кнопку, обрабатывая исключения."""
    if not selector or selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
        print(f"Пропуск клика по кнопке '{button_name}': селектор не задан.")
        return True # Считаем успешным, если селектор не нужен
    try:
        wait = WebDriverWait(driver, wait_time)
        print(f"Ожидание кнопки '{button_name}' ({selector})...")
        button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector)),
            message=f"Кнопка '{button_name}' ('{selector}') не найдена или не кликабельна за {wait_time} сек."
        )
        print(f"Кнопка '{button_name}' найдена. Попытка клика...")
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(0.5)
            button.click()
        except ElementClickInterceptedException:
            print(f"Обычный клик по '{button_name}' перехвачен, пробую JS...")
            driver.execute_script("arguments[0].click();", button)
        print(f"Кнопка '{button_name}' нажата.")
        time.sleep(random.uniform(1.5, 3.0)) # Пауза после клика
        return True
    except TimeoutException:
        print(f"Ошибка: Кнопка '{button_name}' ({selector}) не найдена за {wait_time} сек.")
        # Для некоторых кнопок (куки, пост-чат) это может быть не критично
        return False # Возвращаем False при таймауте
    except Exception as e:
        print(f"Ошибка при клике на кнопку '{button_name}' ({selector}): {e}")
        return False


def wait_for_login_and_open_chat(driver, site_config, status_callback):
    """
    Обрабатывает до трех кнопок для открытия чата:
    1. (Опционально) Кнопка согласия с куки.
    2. Основная кнопка открытия чата.
    3. (Опционально) Кнопка внутри чата (например, "Пока нет").
    4. (Опционально) Кнопка выбора чата с поддержкой (для Альфа-банка).
    """
    cookie_selector = site_config.get('cookie_consent_button_selector')
    chat_button_selector = site_config.get('chat_button_selector')
    post_chat_selector = site_config.get('post_chat_open_button_selector')
    support_chat_selector = site_config.get('support_chat_selector')

    if not chat_button_selector or chat_button_selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
         status_callback("КРИТИЧЕСКАЯ ОШИБКА: Основной селектор кнопки чата (chat_button_selector) не заполнен!")
         return False

    try:
        # --- Шаг 1: Клик по кнопке Куки (если есть) ---
        status_callback("Проверка кнопки согласия с куки...")
        # Используем короткое время ожидания для необязательной кнопки
        if not click_button_safe(driver, cookie_selector, "Согласие с куки", wait_time=5):
             print("Кнопка куки не найдена или ошибка клика (продолжаем)...")
             # Не прерываем, если кнопка куки не найдена
        else:
            status_callback("Кнопка куки обработана.")

        # --- Шаг 2: Клик по основной кнопке Чата --- 
        status_callback("Ожидание основной кнопки чата...")
        if not click_button_safe(driver, chat_button_selector, "Основная кнопка чата", wait_time=300):
            # Если основная кнопка не найдена - это критично
            status_callback(f"КРИТИЧЕСКАЯ ОШИБКА: Основная кнопка чата '{chat_button_selector}' не найдена.")
            return False
        status_callback("Основная кнопка чата нажата. Ожидание инициализации чата...")

        # --- Шаг 3: Клик по кнопке ВНУТРИ чата (если есть) ---
        status_callback("Проверка дополнительной кнопки внутри чата...")
        # Используем среднее время ожидания, т.к. чат должен был появиться
        if not click_button_safe(driver, post_chat_selector, "Доп. кнопка в чате", wait_time=15):
             print("Дополнительная кнопка в чате не найдена или ошибка клика (продолжаем)...")
             # Не прерываем, если эта кнопка не найдена
        else:
             status_callback("Дополнительная кнопка в чате обработана.")

        # --- Шаг 4: Клик по кнопке выбора чата с поддержкой (для Альфа-банка) ---
        if support_chat_selector:
            status_callback("Ожидание кнопки чата с поддержкой...")
            if not click_button_safe(driver, support_chat_selector, "Кнопка чата с поддержкой", wait_time=15):
                status_callback("КРИТИЧЕСКАЯ ОШИБКА: Кнопка чата с поддержкой не найдена.")
                return False
            status_callback("Кнопка чата с поддержкой нажата.")

        status_callback("Этап открытия чата завершен.")
        return True

    except Exception as e:
        print(f"Непредвиденная ошибка в wait_for_login_and_open_chat: {e}")
        status_callback(f"КРИТИЧЕСКАЯ ОШИБКА при открытии чата: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_message(driver, site_config, message):
    """
    Находит поле ввода, кликает, вводит сообщение ПО СИМВОЛАМ, ждет кнопку отправки и кликает.
    """
    global LAST_SENT_MESSAGE
    try:
        input_selector = site_config.get('selectors', {}).get('input_field')
        send_button_selector = site_config.get('selectors', {}).get('send_button')

        if any(not s or s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [input_selector, send_button_selector]):
            print("[SEND_MSG_ERR] КРИТИЧЕСКАЯ ОШИБКА: Селекторы поля ввода или кнопки отправки не заполнены!")
            return False

        # Сохраняем отправляемое сообщение
        LAST_SENT_MESSAGE = message

        wait = WebDriverWait(driver, 20)
        short_wait = WebDriverWait(driver, 5)

        # --- БОЛЬШОЙ TRY/EXCEPT ВОКРУГ ВСЕГО ВЗАИМОДЕЙСТВИЯ ---
        try:
            # --- НАХОДИМ ПОЛЕ ВВОДА ---
            print("[SEND_MSG] Поиск поля ввода...")
            input_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, input_selector)))
            print("[SEND_MSG] Поле ввода найдено.")

            # --- КЛИК, ОЧИСТКА, ВВОД --- 
            print("[SEND_MSG] Клик по полю ввода...")
            try:
                 input_field.click()
            except ElementClickInterceptedException:
                 print("[SEND_MSG] Клик по полю ввода перехвачен, пробую JS...")
                 driver.execute_script("arguments[0].click();", input_field)
            time.sleep(0.5)

            print("[SEND_MSG] Очистка поля ввода...")
            input_field.clear()
            time.sleep(0.3)

            # --- Возвращаем ТОЛЬКО Посимвольный ввод send_keys --- 
            print(f"[SEND_MSG] Посимвольный ввод: '{message[:30]}...'")
            for char in message:
                # Убираем внутренний try-except, внешний обработает
                input_field.send_keys(char)
                time.sleep(random.uniform(0.07, 0.22))
            print(f"[SEND_MSG] Текст введен: '{message[:40]}...'")
            # --- КОНЕЦ ПОСИМВОЛЬНОГО ВВОДА ---
            time.sleep(0.6)

            # --- НАХОДИМ И НАЖИМАЕМ КНОПКУ ОТПРАВКИ ---
            print("[SEND_MSG] Поиск кнопки отправки...")
            send_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, send_button_selector)))
            print("[SEND_MSG] Кнопка отправки найдена. Клик...")
            try:
                send_button.click()
            except ElementClickInterceptedException:
                print("[SEND_MSG] Клик по кнопке отправки перехвачен, пробую JS...")
                driver.execute_script("arguments[0].click();", send_button)

            print(f"[SEND_MSG] Сообщение отправлено: {message}")
            return True

        # --- ОБРАБОТКА ОШИБОК ВНУТРИ ВЗАИМОДЕЙСТВИЯ ---
        except TimeoutException as e_timeout:
            # Логируем, какая именно операция вызвала таймаут
            if 'input_field' not in locals(): print(f"[SEND_MSG_ERR] TimeoutException при поиске поля ввода ('{input_selector}'): {e_timeout.msg.splitlines()[0]}")
            elif 'send_button' not in locals(): print(f"[SEND_MSG_ERR] TimeoutException при поиске кнопки отправки ('{send_button_selector}'): {e_timeout.msg.splitlines()[0]}")
            else: print(f"[SEND_MSG_ERR] TimeoutException на каком-то этапе отправки: {e_timeout.msg.splitlines()[0]}")
            return False
        except StaleElementReferenceException:
             print("[SEND_MSG_ERR] Ошибка: Элемент устарел (StaleElementRef). Повтор на след. итерации.")
             return False
        except WebDriverException as e_wd:
            # Ловим специфичную ошибку сессии или другие проблемы драйвера
            print(f"[SEND_MSG_ERR] КРИТИЧЕСКАЯ ОШИБКА WebDriverException: {e_wd.msg.splitlines()[0]}") # Первая строка ошибки
            if "invalid session id" in e_wd.msg: print("!!! Похоже, сессия браузера была потеряна !!!")
            return False
        except Exception as e_inner:
            print(f"[SEND_MSG_ERR] Непредвиденная ошибка при взаимодействии с чатом: {e_inner}")
            return False
        # --- КОНЕЦ БОЛЬШОГО TRY/EXCEPT ---

    except Exception as e_outer:
        # Ошибки до основного блока try (редко)
        print(f"[SEND_MSG_ERR] Непредвиденная внешняя ошибка в функции send_message: {e_outer}")
        return False


def get_last_message(driver, site_config, last_known_messages_count):
    """Извлекает текст последнего сообщения из чата и определяет наличие капчи.

    Args:
        driver: Экземпляр Selenium WebDriver.
        site_config: Конфигурация сайта.
        last_known_messages_count: Количество сообщений, обработанных ранее.

    Returns:
        tuple: (list[str] or None, str or None, int)
            - Первое значение: Список текстов новых сообщений (list[str]) или None.
            - Второе значение: URL капчи (str), если обнаружена, иначе None.
            - Третье значение: Обновленное количество сообщений.
    """
    global LAST_SENT_MESSAGE
    try:
        selectors = site_config.get('selectors', {})
        messages_area_selector = selectors.get('messages_area')
        message_block_selector = selectors.get('individual_message')
        bot_message_selector = selectors.get('bot_message')
        operator_message_selector = selectors.get('operator_message')
        own_message_selector = selectors.get('own_message')
        text_content_selector = selectors.get('text_content_selector')
        use_specific_text_logic = bool(text_content_selector)

        if any(not s or s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [messages_area_selector, message_block_selector]):
            print("[GET_MSG_ERR] КРИТИЧЕСКАЯ ОШИБКА: Селекторы 'messages_area' или 'individual_message' не заполнены!")
            return None, None, last_known_messages_count

        wait = WebDriverWait(driver, 10)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, messages_area_selector)))
        except TimeoutException:
            print(f"[GET_MSG_ERR] Область сообщений ('{messages_area_selector}') не найдена за 10 сек.")
            return None, None, last_known_messages_count
        time.sleep(1.8)

        try:
            all_message_elements = driver.find_elements(By.CSS_SELECTOR, message_block_selector)
        except NoSuchElementException:
            print("[GET_MSG] Блоки сообщений не найдены.")
            return None, None, last_known_messages_count

        current_messages_count = len(all_message_elements)
        print(f"[GET_MSG] Текущее количество сообщений: {current_messages_count}, Последнее известное: {last_known_messages_count}")

        if current_messages_count <= last_known_messages_count:
            print("[GET_MSG] Нет новых сообщений")
            return None, None, last_known_messages_count

        # Берем только последнее сообщение
        last_message = all_message_elements[-1]
        print("[GET_MSG] Проверка последнего сообщения...")

        extracted_texts = []
        found_captcha_src = None

        try:
            # Проверяем, не является ли сообщение нашим собственным
            if own_message_selector:
                try:
                    own_message = last_message.find_element(By.CSS_SELECTOR, own_message_selector)
                    if own_message:
                        print("[GET_MSG] Пропускаем собственное сообщение")
                        return None, None, current_messages_count
                except NoSuchElementException:
                    pass

            # Проверяем на сообщение оператора
            if operator_message_selector:
                try:
                    operator_messages = last_message.find_elements(By.CSS_SELECTOR, operator_message_selector)
                    if operator_messages:
                        print("[GET_MSG] !!! ОБНАРУЖЕНО СООБЩЕНИЕ ОПЕРАТОРА !!!")
                        operator_text = " ".join(msg.text.strip() for msg in operator_messages if msg.text.strip())
                        if operator_text:
                            print(f"[GET_MSG] Текст сообщения оператора: '{operator_text[:70]}...'")
                            # Проверяем текст сообщения на соответствие фразам оператора
                            for phrase in site_config.get("operator_phrases", []):
                                if re.search(phrase, operator_text, re.IGNORECASE):
                                    print(f"[GET_MSG] Найдено соответствие фразе оператора: '{phrase}'")
                                    extracted_texts.append("к вам подключился")
                                    extracted_texts.append(None)
                                    extracted_texts.append(current_messages_count)
                                    return extracted_texts
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

            # Проверяем на сообщение бота
            if bot_message_selector:
                try:
                    bot_message = last_message.find_element(By.CSS_SELECTOR, bot_message_selector)
                    bot_text = bot_message.text.strip()
                    # Проверяем, не является ли это нашим последним отправленным сообщением
                    if LAST_SENT_MESSAGE and bot_text == LAST_SENT_MESSAGE:
                        print("[GET_MSG] Пропускаем собственное сообщение (сравнение с кэшем)")
                        return None, None, current_messages_count
                    # Пропускаем первое приветствие бота
                    if bot_text and "Здравствуйте" in bot_text and "Могу о многом вам рассказать" in bot_text:
                        print("[GET_MSG] Пропускаем первое приветствие бота")
                        return None, None, current_messages_count
                    if bot_text:
                        print(f"[GET_MSG] Найдено сообщение бота: '{bot_text[:70]}...'")
                        extracted_texts.append(bot_text)
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

            # Если не нашли ни оператора, ни бота, используем общую логику
            if not extracted_texts and use_specific_text_logic:
                try:
                    text_element = last_message.find_element(By.CSS_SELECTOR, text_content_selector)
                    found_text = text_element.text.strip()
                    # Проверяем, не является ли это нашим последним отправленным сообщением
                    if LAST_SENT_MESSAGE and found_text == LAST_SENT_MESSAGE:
                        print("[GET_MSG] Пропускаем собственное сообщение (сравнение с кэшем)")
                        return None, None, current_messages_count
                    if found_text:
                        extracted_texts.append(found_text)
                except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
                    pass

            # Проверка на капчу
            if not found_captcha_src and extracted_texts:
                captcha_check_text = extracted_texts[0]
                if CAPTCHA_TEXT_MARKER.lower() in captcha_check_text.lower():
                    print("[GET_MSG] !!! Обнаружен текстовый маркер капчи !!!")
                    try:
                        captcha_img = last_message.find_element(By.CSS_SELECTOR, CAPTCHA_IMG_SELECTOR)
                        if captcha_img:
                            captcha_src = captcha_img.get_attribute('src')
                            if captcha_src:
                                if captcha_src.startswith('data:image'):
                                    base64_prefix_end = captcha_src.find(';base64,')
                                    if base64_prefix_end != -1:
                                        found_captcha_src = captcha_src[base64_prefix_end + len(';base64,'):]
                                    else:
                                        found_captcha_src = captcha_src
                                else:
                                    found_captcha_src = captcha_src
                    except (NoSuchElementException, StaleElementReferenceException):
                        found_captcha_src = "КАПЧА_НО_БЕЗ_IMG"

        except StaleElementReferenceException:
            print("[GET_MSG_WARN] Элемент сообщения устарел (StaleElementReferenceException)")
            return None, None, last_known_messages_count
        except Exception as e:
            print(f"[GET_MSG_ERR] Непредвиденная ошибка при обработке сообщения: {e}")
            traceback.print_exc()
            return None, None, last_known_messages_count

        return extracted_texts if extracted_texts else None, found_captcha_src, current_messages_count

    except Exception as e:
        print(f"[GET_MSG_ERR] Непредвиденная внешняя ошибка в get_last_message: {e}")
        traceback.print_exc()
        return None, None, last_known_messages_count

def close_driver(driver):
    """Закрывает веб-драйвер."""
    if driver:
        try:
            driver.quit()
            print("Драйвер Chrome закрыт.")
        except Exception as e:
            print(f"Ошибка при закрытии драйвера: {e}")