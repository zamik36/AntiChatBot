import time
from selenium import webdriver
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains


def scroll_page(driver, scroll_amount=300, direction='down'):
    """Плавно прокручивает страницу вверх или вниз."""
    try:
        scroll_value = scroll_amount if direction == 'down' else -scroll_amount
        driver.execute_script(f"window.scrollBy(0, {scroll_value});")
        time.sleep(random.uniform(0.5, 1.5)) # Небольшая пауза после прокрутки
        print(f"Страница прокручена {'вниз' if direction == 'down' else 'вверх'}.")
        return True
    except Exception as e:
        print(f"Ошибка при прокрутке страницы: {e}")
        return False


def move_mouse_to_element_safe(driver, selector, element_name="элемент"):
    """Плавно перемещает курсор мыши к указанному элементу."""
    try:
        wait = WebDriverWait(driver, 5) # Короткое ожидание, элемент должен быть видим
        element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.pause(random.uniform(0.5, 1.2)) # Задержка курсора на элементе
        actions.perform()
        print(f"Курсор перемещен к элементу: {element_name} ('{selector}')")
        return True
    except TimeoutException:
        # Не страшно, если элемент для эмуляции не найден
        print(f"Элемент для перемещения мыши не найден: {element_name} ('{selector}')")
        return False
    except Exception as e:
        print(f"Ошибка при перемещении мыши к элементу {element_name}: {e}")
        return False


def init_driver():
    """Инициализирует и возвращает веб-драйвер Chrome."""
    try:
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless') # Для отладки лучше запускать с видимым окном
        options.add_argument("--start-maximized") # Открывать в максимальном окне
        options.add_experimental_option("excludeSwitches", ["enable-logging"]) # Убрать лишние логи в консоль

        # Автоматически скачивает/обновляет и использует chromedriver
        service = ChromeService(executable_path=ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("Драйвер Chrome инициализирован.")
        return driver
    except Exception as e:
        print(f"Ошибка инициализации драйвера: {e}")
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

def wait_for_login_and_open_chat(driver, site_config, status_callback):
    """
    Ожидает, пока пользователь войдет в систему и кнопка чата станет доступной,
    затем кликает на кнопку чата.
    """
    try:
        chat_button_selector = site_config['chat_button_selector']
        if not chat_button_selector or chat_button_selector == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР":
             status_callback("Ошибка: Селектор кнопки чата не заполнен в config.json!")
             return False

        # Длительное ожидание - пользователь должен успеть войти
        # Установи таймаут в секундах (например, 5 минут = 300 секунд)
        wait_time = 300
        wait = WebDriverWait(driver, wait_time)

        status_callback(f"Ожидание появления кнопки чата ({chat_button_selector})...\n"
                        f"ПОЖАЛУЙСТА, ВОЙДИТЕ В СВОЙ АККАУНТ В БРАУЗЕРЕ.\n"
                        f"У вас есть {wait_time // 60} минут.")

        chat_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, chat_button_selector)),
            message=f"Кнопка чата '{chat_button_selector}' не найдена или не кликабельна за {wait_time} сек. Возможно, вы не вошли или селектор неверный."
        )

        status_callback("Кнопка чата найдена. Попытка открыть чат...")
        print("Кнопка чата найдена. Попытка клика...")

        # Попытка клика с обходом возможных перекрытий
        try:
            chat_button.click()
        except ElementClickInterceptedException:
            print("Обычный клик перехвачен, пробую клик через JavaScript...")
            driver.execute_script("arguments[0].click();", chat_button)

        print("Кнопка чата нажата.")
        status_callback("Чат открыт/открывается. Ожидание загрузки...")
        time.sleep(5) # Дать чату время загрузиться
        return True

    except TimeoutException as e:
        print(f"Ошибка ожидания/клика по кнопке чата: {e}")
        status_callback(f"Ошибка: Кнопка чата не найдена за {wait_time} сек. Убедитесь, что вы вошли и селектор верный.")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при ожидании/открытии чата: {e}")
        status_callback(f"Ошибка при открытии чата: {e}")
        return False

def send_message(driver, site_config, message):
    """
    Находит поле ввода, кликает на него, вводит сообщение ПО СИМВОЛАМ
    и нажимает кнопку отправки.
    ПРЕДУПРЕЖДЕНИЕ: Посимвольный ввод может быть нестабилен на некоторых сайтах.
    """
    try:
        input_selector = site_config['selectors']['input_field']
        send_button_selector = site_config['selectors']['send_button']

        if any(s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" or not s for s in [input_selector, send_button_selector]):
            print("Ошибка: Селекторы поля ввода или кнопки отправки не заполнены!")
            return False

        wait = WebDriverWait(driver, 15)

        # --- НАХОДИМ ПОЛЕ ВВОДА ---
        try:
            input_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, input_selector)))
            print(f"Поле ввода '{input_selector}' найдено.")
        except TimeoutException:
             print(f"Ошибка: Поле ввода '{input_selector}' не найдено или не видимо за 15 сек.")
             return False

        # --- КЛИК ДЛЯ ФОКУСА, ОЧИСТКА И ПОСИМВОЛЬНЫЙ ВВОД ---
        try:
            # Кликаем на поле для фокуса перед вводом
            input_field.click()
            print("Клик по полю ввода для фокуса.")
            time.sleep(0.4) # Пауза после клика

            input_field.clear()
            print("Поле ввода очищено.")
            time.sleep(0.3) # Пауза после очистки

            # *** ИЗМЕНЕНИЕ ЗДЕСЬ: Посимвольный ввод ***
            print(f"Начинаем посимвольный ввод: '{message[:30]}...'")
            for char in message:
                input_field.send_keys(char)
                # Пауза между символами для эмуляции
                time.sleep(random.uniform(0.08, 0.25)) # Немного увеличенный и вариативный интервал

            print(f"Текст '{message[:30]}...' введен посимвольно.")
            time.sleep(0.5) # Пауза после ввода перед поиском кнопки

        except StaleElementReferenceException:
             print("### Ошибка: Поле ввода устарело (StaleElementReferenceException) во время ввода. Попробуем найти заново на след. итерации.")
             return False # Выходим, чтобы внешний цикл попробовал снова
        except Exception as e:
            print(f"Ошибка при клике/очистке или посимвольном вводе в поле '{input_selector}': {e}")
            return False

        # --- НАХОДИМ И НАЖИМАЕМ КНОПКУ ОТПРАВКИ ---
        try:
            # Используем presence_of_element_located, т.к. кнопка может быть скрыта, но существовать
            # Затем проверяем кликабельность отдельно
            send_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, send_button_selector)))
            # Дополнительное ожидание кликабельности
            send_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, send_button_selector)))

            print(f"Кнопка отправки '{send_button_selector}' найдена и кликабельна.")
            # Попытка клика с обходом возможных перекрытий
            try:
                send_button.click()
            except ElementClickInterceptedException:
                print("Обычный клик по кнопке отправки перехвачен, пробую JS клик...")
                driver.execute_script("arguments[0].click();", send_button)

            print(f"Сообщение отправлено (после посимвольного ввода): {message}")
            return True
        except TimeoutException:
            print(f"Ошибка: Кнопка отправки '{send_button_selector}' не найдена или не кликабельна за 15 сек.")
            return False
        except StaleElementReferenceException:
             print("### Ошибка: Кнопка отправки устарела (StaleElementReferenceException). Попробуем на след. итерации.")
             return False
        except Exception as e:
            print(f"Ошибка при клике на кнопку отправки '{send_button_selector}': {e}")
            return False

    except Exception as e:
        # Общая ошибка
        print(f"Непредвиденная ошибка в функции send_message: {e}")
        return False


def get_last_message(driver, site_config, last_known_messages_count):
    """
    Извлекает текст последнего сообщения из области чата.
    Возвращает (new_text, new_count) или (None, last_known_messages_count)
    """
    try:
        messages_area_selector = site_config['selectors']['messages_area']
        message_selector = site_config['selectors']['individual_message']

        if any(s == "ЗАПОЛНИ_ЭТОТ_СЕЛЕКТОР" for s in [messages_area_selector, message_selector]):
            print("Ошибка: Селекторы области сообщений или отдельного сообщения не заполнены!")
            return None, last_known_messages_count

        wait = WebDriverWait(driver, 10) # Ждем недолго, основное ожидание в цикле логики

        # Дождаться наличия хотя бы одного сообщения (или области)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, messages_area_selector)))

        # Находим все сообщения
        # Добавим небольшую паузу, чтобы дать JS время отрисовать новое сообщение
        time.sleep(1.5)
        messages_elements = driver.find_elements(By.CSS_SELECTOR, f"{message_selector}")
        current_messages_count = len(messages_elements)

        if current_messages_count > last_known_messages_count and messages_elements:
            # Есть новые сообщения, берем самое последнее
            last_message_text = messages_elements[-1].text.strip()
            print(f"Получено новое сообщение ({current_messages_count}): {last_message_text}")
            return last_message_text, current_messages_count # Возвращаем текст и новое количество
        elif messages_elements:
            # Новых сообщений нет, но старые есть. Вернем последнее на всякий случай, но без изменения счетчика
            # Может быть полезно для повторной проверки, если что-то пошло не так
             # print(f"Новых сообщений нет (всего {current_messages_count}). Последнее известное: {messages_elements[-1].text.strip()}")
             return None, last_known_messages_count # Сигнал, что нового нет
        else:
            # Сообщений вообще нет
            print("Сообщений в чате не найдено.")
            return None, 0 # Нового нет, и всего 0

    except TimeoutException:
        # print(f"Таймаут при ожидании сообщений ('{messages_area_selector}' или '{message_selector}').")
        # Не страшно, если просто нет новых сообщений
        return None, last_known_messages_count
    except Exception as e:
        print(f"Ошибка при получении сообщения: {e}")
        return None, last_known_messages_count # Ошибка

def close_driver(driver):
    """Закрывает веб-драйвер."""
    if driver:
        try:
            driver.quit()
            print("Браузер закрыт.")
        except Exception as e:
            print(f"Ошибка при закрытии браузера: {e}")