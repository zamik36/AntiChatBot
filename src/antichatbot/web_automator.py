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
FALLBACK_TEXT_SELECTOR_BEELINE = 'p.Q5yDq' # Запасной 1: параграф
ULTRA_FALLBACK_SELECTOR_BEELINE = 'div.AEfjo' # Запасной 2: обертка контента

def scroll_page(driver, scroll_amount=300, direction='down'):
    """Плавно прокручивает страницу вверх или вниз."""
    print(f"[DEBUG_EMU] Attempting scroll_page (direction: {direction})")
    try:
        scroll_value = scroll_amount if direction == 'down' else -scroll_amount
        driver.execute_script(f"window.scrollBy(0, {scroll_value});")
        time.sleep(random.uniform(0.5, 1.5)) # Небольшая пауза после прокрутки
        # print(f"Страница прокручена {'вниз' if direction == 'down' else 'вверх'}.") # Убрал лог
        return True
    except Exception as e:
        print(f"[DEBUG_EMU] Ошибка при прокрутке страницы: {e}")
        return False


def move_mouse_to_element_safe(driver, selector, element_name="элемент"):
    """Плавно перемещает курсор мыши к указанному элементу."""
    print(f"[DEBUG_EMU] Attempting move_mouse_to_element_safe (element: {element_name}, selector: {selector})")
    if not selector or selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
        # print(f"Пропуск перемещения мыши: селектор для '{element_name}' не задан.")
        return False
    try:
        wait = WebDriverWait(driver, 5) # Короткое ожидание
        element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.pause(random.uniform(0.5, 1.2)) # Задержка
        actions.perform()
        # print(f"Курсор перемещен к элементу: {element_name} ('{selector}')") # Убрал лог
        return True
    except TimeoutException:
        # print(f"Элемент для перемещения мыши не найден: {element_name} ('{selector}')")
        return False
    except Exception as e:
        print(f"[DEBUG_EMU] Ошибка при перемещении мыши к элементу {element_name}: {e}")
        return False


def move_mouse_randomly(driver):
    """Перемещает мышь в случайные координаты видимой области окна.
    Использует execute_script для симуляции события mousemove.
    """
    print("[DEBUG_EMU] Attempting move_mouse_randomly (JS method)")
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
        # print(f"JS mousemove event dispatched to ({random_x}, {random_y})")
        time.sleep(random.uniform(0.5, 1.0)) # Небольшая пауза после симуляции
        return True
    except Exception as e:
        print(f"[DEBUG_EMU] Ошибка при случайном перемещении мыши (JS method): {e}")
        return False


def perform_random_click(driver, site_config):
    """Выполняет БЕЗОПАСНЫЙ случайный клик на странице.

    Пытается кликнуть внутри элемента 'messages_area', если селектор задан,
    иначе кликает по 'body'. Это предотвращает случайные клики по кнопкам/ссылкам.
    """
    print("[DEBUG_EMU] Attempting perform_random_click")
    click_target_selector = site_config.get('selectors', {}).get('messages_area')
    element_name = "область сообщений"

    if not click_target_selector or click_target_selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
        click_target_selector = 'body' # Кликаем по body, если нет специфичного селектора
        element_name = "тело страницы"

    print(f"[DEBUG_EMU] perform_random_click target: {element_name} ('{click_target_selector}')")
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
        # print(f"Безопасный случайный клик выполнен по элементу: {element_name} ('{click_target_selector}')") # Лог убран
        time.sleep(random.uniform(0.7, 1.5))
        return True
    except TimeoutException:
        print(f"[DEBUG_EMU] Элемент для безопасного клика не найден: {element_name} ('{click_target_selector}')")
        return False
    except ElementClickInterceptedException:
        print(f"[DEBUG_EMU] Клик по элементу {element_name} перехвачен. Пропускаем этот клик.")
        return False # Считаем неудачей, если клик перехвачен
    except Exception as e:
        print(f"[DEBUG_EMU] Ошибка при выполнении безопасного случайного клика по {element_name}: {e}")
        return False


def init_driver():
    """Инициализирует и возвращает веб-драйвер Chrome.
    Использует webdriver-manager для автоматической загрузки драйвера.
    """
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--log-level=3')

        # --- УБИРАЕМ: Указание пути к Chrome binary ---
        # chrome_binary_path = r"C:\student\chrome-win64\chrome.exe"
        # print(f"Указание пути к Chrome: {chrome_binary_path}")
        # options.binary_location = chrome_binary_path
        # --- КОНЕЦ УДАЛЕНИЯ ---

        # --- ВОЗВРАЩАЕМ: Использование webdriver-manager --- 
        print("Инициализация Chrome WebDriver (автоматический поиск/скачивание драйвера)...")
        # Используем Service с webdriver-manager
        service = ChromeService(executable_path=ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("Драйвер Chrome инициализирован.")
        return driver
    except WebDriverException as e_wd:
         # Оставляем общую обработку WebDriverException
         print(f"КРИТИЧЕСКАЯ ОШИБКА WebDriverException при инициализации драйвера: {e_wd.msg.splitlines()[0]}")
         if "session not created" in e_wd.msg:
             print("!!! Ошибка 'session not created'. Проверьте совместимость версий Chrome и ChromeDriver (webdriver-manager мог ошибиться).")
         elif "cannot find chrome binary" in e_wd.msg.lower():
             print("!!! Ошибка 'cannot find chrome binary'. Убедитесь, что Chrome установлен в стандартное местоположение.")
         return None
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА инициализации драйвера: {e}")
        # traceback.print_exc() # Можно раскомментировать для детальной отладки
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
    """
    Извлекает тексты ВСЕХ НОВЫХ сообщений и данные капчи (если применимо).
    Логика адаптируется: сложная для сайтов с 'text_content_selector', простая для остальных.
    Возвращает кортеж: (list_of_new_texts, captcha_base64, new_count)
    - list_of_new_texts: Список строк с текстами новых сообщений (может быть пустым).
    - captcha_base64: Строка base64 изображения капчи (или None).
    - new_count: Новое общее количество сообщений.
    Если новых сообщений нет, возвращает ([], None, last_known_messages_count).
    """
    list_of_new_texts = [] # Возвращаем список
    captcha_base64 = None
    new_count = last_known_messages_count

    try:
        selectors = site_config.get('selectors', {})
        messages_area_selector = selectors.get('messages_area')
        message_block_selector = selectors.get('individual_message')
        text_content_selector = selectors.get('text_content_selector') # Для Beeline
        use_specific_text_logic = bool(text_content_selector) # Флаг сложной логики

        if any(not s or s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [messages_area_selector, message_block_selector]):
            print("КРИТИЧЕСКАЯ ОШИБКА: Селекторы 'messages_area' или 'individual_message' не заполнены!")
            return [], None, last_known_messages_count # Пустой список

        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, messages_area_selector)))
        time.sleep(1.8) # Пауза

        all_message_elements = driver.find_elements(By.CSS_SELECTOR, message_block_selector)
        current_messages_count = len(all_message_elements)

        if current_messages_count <= last_known_messages_count:
            return [], None, last_known_messages_count # Нет новых сообщений, пустой список

        new_count = current_messages_count
        new_message_elements = all_message_elements[last_known_messages_count:]
        print(f"Найдено {len(new_message_elements)} новых сообщений. Обработка...")

        captcha_text_found = False # Для логики капчи
        captcha_image_found = False

        # --- Обработка КАЖДОГО нового сообщения --- 
        for i, msg_element in enumerate(new_message_elements):
            current_text = None

            # --- Адаптивное извлечение текста ---
            if use_specific_text_logic: # --- Сложная логика (Beeline) ---
                try: # Внешний try для Beeline
                    try: # Попытка 1: Основной селектор
                        text_element = msg_element.find_element(By.CSS_SELECTOR, text_content_selector)
                        current_text = text_element.text.strip()
                    except NoSuchElementException: # Если основной не найден
                        try: # Попытка 2: Запасной 1 (параграф)
                            fallback_text_element = msg_element.find_element(By.CSS_SELECTOR, FALLBACK_TEXT_SELECTOR_BEELINE)
                            current_text = fallback_text_element.text.strip()
                            if i == len(new_message_elements) -1: print(f"  Предупреждение: Не найден '{text_content_selector}'. Текст из '{FALLBACK_TEXT_SELECTOR_BEELINE}'.")
                        except NoSuchElementException: # Если и он не найден
                            try: # Попытка 3: Запасной 2 (обертка)
                               ultra_fallback_element = msg_element.find_element(By.CSS_SELECTOR, ULTRA_FALLBACK_SELECTOR_BEELINE)
                               current_text = ultra_fallback_element.text.strip()
                               if i == len(new_message_elements) - 1: print(f"  Предупреждение: Не найдены осн. и зап.1. Текст из '{ULTRA_FALLBACK_SELECTOR_BEELINE}'.")
                            except NoSuchElementException: # Если ВСЕ не найдены
                                 if i == len(new_message_elements) - 1: print(f"  КРИТИЧЕСКАЯ ОШИБКА: Не найден ни один селектор текста для Beeline.")
                                 current_text = None # Явно ставим None
                # Отлов общих ошибок для Beeline вне цепочки NoSuchElement
                except StaleElementReferenceException:
                    print(f"  [{i+1}] Ошибка StaleElementReferenceException при извлечении текста (Beeline). Пропуск сообщения.")
                    current_text = None
                except Exception as e_text:
                    print(f"  [{i+1}] Непредвиденная ошибка извлечения текста (Beeline): {e_text}")
                    current_text = None
            # --- Конец сложной логики Beeline --- 
            
            else: # --- Простая логика (Tele2 и др.) ---
                try: # Try для простой логики
                    current_text = msg_element.text.strip()
                # Отлов ошибок для простой логики
                except StaleElementReferenceException:
                    print(f"  [{i+1}] Ошибка StaleElementReferenceException при извлечении текста (Простая). Пропуск сообщения.")
                    current_text = None
                except Exception as e_text:
                    print(f"  [{i+1}] Непредвиденная ошибка извлечения текста (Простая): {e_text}")
                    current_text = None
            # --- Конец простой логики --- 

            # Добавляем извлеченный текст (даже если None) в список
            list_of_new_texts.append(current_text)
            if current_text is not None:
                 print(f"  [{i+1}/{len(new_message_elements)}] Текст: '{current_text[:60]}...'")
            else:
                 print(f"  [{i+1}/{len(new_message_elements)}] Текст: Не удалось извлечь.")

            # --- Проверка на капчу (только для сложной логики) ---
            if use_specific_text_logic:
                if current_text and CAPTCHA_TEXT_MARKER in current_text:
                    captcha_text_found = True
                try:
                    captcha_img = msg_element.find_element(By.CSS_SELECTOR, CAPTCHA_IMG_SELECTOR)
                    captcha_src = captcha_img.get_attribute('src')
                    if captcha_src and captcha_src.startswith('data:image'):
                        captcha_base64 = captcha_src # Сохраняем последнее найденное изображение
                        captcha_image_found = True
                except NoSuchElementException:
                    pass # Игнорируем, если картинки нет в этом блоке
                except Exception as e_captcha:
                    print(f"  [{i+1}] Ошибка поиска/извлечения img капчи: {e_captcha}")
            # --- Конец проверки на капчу --- 
        # --- Конец цикла по новым сообщениям --- 

        # --- Финальное решение по капче --- 
        final_captcha_base64 = captcha_base64 if (captcha_text_found and captcha_image_found) else None
        if use_specific_text_logic:
            if captcha_text_found != captcha_image_found:
                 print(f"Капча обработана: текст={captcha_text_found}, картинка={captcha_image_found}. Результат: НЕТ КАПЧИ")
            elif final_captcha_base64:
                 print(f"Капча обработана: текст={captcha_text_found}, картинка={captcha_image_found}. Результат: КАПЧА ЕСТЬ")

        print(f"Возврат: Сообщений={len(list_of_new_texts)}, Captcha={'ДА' if final_captcha_base64 else 'НЕТ'}, Count={new_count}")
        return list_of_new_texts, final_captcha_base64, new_count

    except TimeoutException:
        return [], None, last_known_messages_count
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА в get_last_message: {e}")
        import traceback
        traceback.print_exc()
        return [], None, last_known_messages_count

def close_driver(driver):
    """Закрывает веб-драйвер."""
    if driver:
        try:
            driver.quit()
            print("Драйвер Chrome закрыт.")
        except Exception as e:
            print(f"Ошибка при закрытии драйвера: {e}")