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

# Селекторы для Beeline
# FALLBACK_TEXT_SELECTOR_BEELINE = 'p.Q5yDq' # Запасной 1: параграф - УДАЛЕНО, НЕ ИСПОЛЬЗУЕТСЯ?
# ULTRA_FALLBACK_SELECTOR_BEELINE = 'div.AEfjo' # Запасной 2: обертка контента - УДАЛЕНО, НЕ ИСПОЛЬЗУЕТСЯ?

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
        # Стандартные опции для локального запуска
        options.add_argument("--start-maximized")
        # Убираем опции, которые могут мешать локальному запуску или не нужны
        # options.add_experimental_option('excludeSwitches', ['enable-automation'])
        # options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--log-level=3')

        # --- ОПЦИИ ДЛЯ DOCKER/HEADLESS УДАЛЕНЫ ---
        # options.add_argument("--headless=new") 
        # options.add_argument("--no-sandbox")
        # options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--disable-gpu")
        # options.add_argument("--window-size=1920x1080")
        # options.add_argument("--disable-features=VizDisplayCompositor")
        # options.add_argument(f"--user-data-dir=...")
        # options.binary_location = ...
        # -----------------------------------------

        print("Инициализация Chrome WebDriver...")
        # Используем Service с webdriver-manager
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
    """
    cookie_selector = site_config.get('cookie_consent_button_selector')
    chat_button_selector = site_config.get('chat_button_selector')
    post_chat_selector = site_config.get('post_chat_open_button_selector')

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
    try:
        input_selector = site_config.get('selectors', {}).get('input_field')
        send_button_selector = site_config.get('selectors', {}).get('send_button')

        if any(not s or s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [input_selector, send_button_selector]):
            print("[SEND_MSG_ERR] КРИТИЧЕСКАЯ ОШИБКА: Селекторы поля ввода или кнопки отправки не заполнены!")
            return False

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
    """Извлекает текст последнего сообщения из чата, определяет наличие капчи.

    Args:
        driver: Экземпляр Selenium WebDriver.
        site_config: Конфигурация сайта.
        last_known_messages_count: Количество сообщений, обработанных ранее.

    Returns:
        tuple: (str or None, bool)
            - Первое значение: Текст сообщения (str) или URL капчи (str), или None, если новых сообщений нет или ошибка.
            - Второе значение: True, если обнаружена капча, иначе False.
    """
    try:
        selectors = site_config.get('selectors', {})
        messages_area_selector = selectors.get('messages_area')
        message_block_selector = selectors.get('individual_message')
        text_content_selector = selectors.get('text_content_selector') # Для Beeline
        use_specific_text_logic = bool(text_content_selector) # Флаг сложной логики

        if any(not s or s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [messages_area_selector, message_block_selector]):
            print("КРИТИЧЕСКАЯ ОШИБКА: Селекторы 'messages_area' или 'individual_message' не заполнены!")
            return None, False

        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, messages_area_selector)))
        time.sleep(1.8) # Пауза

        all_message_elements = driver.find_elements(By.CSS_SELECTOR, message_block_selector)
        current_messages_count = len(all_message_elements)

        if current_messages_count <= last_known_messages_count:
            return None, False

        new_messages_count = current_messages_count - last_known_messages_count
        if new_messages_count <= 0:
            return None, False

        # print(f"Найдено новых сообщений: {new_messages_count}")
        # Берем последнее сообщение из всего списка (самое новое)
        last_message_element = all_message_elements[-1]

        # --- Логика извлечения текста (упрощена) ---
        extracted_text = None
        if use_specific_text_logic:
            try:
                # print(f"Поиск текста по селектору: {text_content_selector}")
                text_element = last_message_element.find_element(By.CSS_SELECTOR, text_content_selector)
                found_text = text_element.text.strip()
                if found_text:
                    # print(f"Текст извлечен (метод 1 - text_content_selector): '{found_text[:50]}...'")
                    extracted_text = found_text
            except (NoSuchElementException, TimeoutException):
                # print("text_content_selector не найден, пробуем метод 2...")
                pass # Пробуем следующий метод

        # Метод 2: Получить весь текст блока и убрать имя/время (если селекторы есть)
        if not extracted_text:
            full_text = last_message_element.text
            # print(f"Текст извлечен (метод 2 - весь блок): '{full_text[:50]}...'")
            author_selector = site_config.get('selectors', {}).get('message_author_selector')
            time_selector = site_config.get('selectors', {}).get('message_time_selector')
            # Удаление имени автора
            if author_selector:
                try:
                    author_element = last_message_element.find_element(By.CSS_SELECTOR, author_selector)
                    full_text = full_text.replace(author_element.text, '', 1)
                    # print(f"Удален автор: {author_element.text}")
                except NoSuchElementException:
                    pass
            # Удаление времени
            if time_selector:
                try:
                    time_element = last_message_element.find_element(By.CSS_SELECTOR, time_selector)
                    full_text = full_text.replace(time_element.text, '', 1)
                    # print(f"Удалено время: {time_element.text}")
                except NoSuchElementException:
                    pass
            extracted_text = full_text.strip() # Обновляем extracted_text

        # --- Проверка на капчу --- 
        captcha_check_text = extracted_text if extracted_text else "" # Используем извлеченный текст
        # print(f"Анализ текста на капчу: {captcha_check_text[:50]}...")
        if CAPTCHA_TEXT_MARKER.lower() in captcha_check_text.lower():
            # print(f"Обнаружен текстовый маркер капчи: '{CAPTCHA_TEXT_MARKER}'")
            # --- Поиск изображения капчи --- #
            try:
                captcha_img = last_message_element.find_element(By.CSS_SELECTOR, CAPTCHA_IMG_SELECTOR)
                captcha_src = captcha_img.get_attribute('src')
                # print(f"Найдено изображение капчи, src: {captcha_src[:50]}...")
                return captcha_src, True # Возвращаем URL капчи и флаг True
            except NoSuchElementException:
                # print("Текстовый маркер есть, но изображение капчи не найдено.")
                return "КАПЧА_НО_БЕЗ_IMG", True # Возвращаем маркер и флаг
            except Exception as img_e:
                print(f"Ошибка при поиске/получении src изображения капчи: {img_e}")
                return "КАПЧА_НО_ОШИБКА_IMG", True
        # else:
            # print("Текстовый маркер капчи не найден.")
            
        return extracted_text if extracted_text is not None else "", False # Возвращаем текст и флаг False

    except (NoSuchElementException, TimeoutException):
        # print("Новые сообщения или элементы сообщений не найдены.")
        return None, False
    except StaleElementReferenceException:
        print("Элемент сообщения устарел (StaleElementReferenceException), пропуск чтения.")
        return None, False
    except Exception as e:
        print(f"Непредвиденная ошибка при получении последнего сообщения: {e}")
        traceback.print_exc()
        return None, False

def close_driver(driver):
    """Закрывает веб-драйвер."""
    if driver:
        try:
            driver.quit()
            print("Драйвер Chrome закрыт.")
        except Exception as e:
            print(f"Ошибка при закрытии драйвера: {e}")