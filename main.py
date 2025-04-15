import tkinter as tk
import json
import gui # Импортируем наш модуль GUI
import os
from dotenv import load_dotenv
import time

# Загружаем переменные из .env файла (если он есть)
load_dotenv()

CONFIG_FILE = 'config.json'

def load_config(filename):
    """Загружает конфигурацию из JSON файла, применяя настройки по умолчанию."""
    full_config = None
    processed_sites_config = {}

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            full_config = json.load(f)
    except FileNotFoundError:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Файл конфигурации {filename} не найден.")
        return None, None # Возвращаем None для обеих частей
    except json.JSONDecodeError as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Неверный формат JSON в файле {filename}. Ошибка: {e}")
        return None, None
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА при чтении конфигурации: {e}")
        return None, None

    # Обработка сайтов с настройками по умолчанию
    defaults = full_config.get('_defaults', {})
    sites_config = full_config.get('sites', {})

    for site_name, site_specific_config in sites_config.items():
        current_site_config = defaults.copy()
        # Глубокое обновление словарей (особенно важно для selectors)
        for key, value in site_specific_config.items():
            if isinstance(value, dict) and isinstance(current_site_config.get(key), dict):
                # Обновляем существующий вложенный словарь, не перезаписывая его полностью
                current_site_config[key].update(value)
            else:
                current_site_config[key] = value
        processed_sites_config[site_name] = current_site_config

    # Получаем конфигурацию Redis
    redis_config = full_config.get('redis', {})
    # Проверяем наличие хоста и порта, используем значения по умолчанию, если их нет
    if 'host' not in redis_config:
        redis_config['host'] = 'localhost'
        print(f"Предупреждение: Хост Redis не найден в {filename}, используется значение по умолчанию: 'localhost'")
    if 'port' not in redis_config:
        redis_config['port'] = 6379
        print(f"Предупреждение: Порт Redis не найден в {filename}, используется значение по умолчанию: 6379")
    # Преобразуем порт в число, если он загрузился как строка
    try:
         redis_config['port'] = int(redis_config['port'])
    except (ValueError, TypeError):
        print(f"Предупреждение: Неверный формат порта Redis ('{redis_config['port']}') в {filename}, используется значение по умолчанию: 6379")
        redis_config['port'] = 6379

    print(f"Конфигурация успешно загружена и обработана из {filename}")
    return processed_sites_config, redis_config # Возвращаем конфиг сайтов и конфиг Redis

if __name__ == "__main__":
    # Проверяем наличие .env и выводим предупреждение, если его нет
    if not os.path.exists('.env'):
         print("ПРЕДУПРЕЖДЕНИЕ: Файл .env не найден.")
         print("Для работы с Telegram (уведомления, капча) создайте файл .env и добавьте:")
         print("TELEGRAM_BOT_TOKEN=ВАШ_ТОКЕН")
         print("TELEGRAM_USER_ID=ВАШ_ЧИСЛОВОЙ_ID")
         print("(Можно получить ID, написав боту @userinfobot)")
         print("Продолжение работы без интеграции с Telegram...")
         time.sleep(3) # Даем время прочитать

    # Загружаем конфигурацию
    sites_data, redis_data = load_config(CONFIG_FILE)

    if sites_data:
        root = tk.Tk()
        # Передаем оба словаря конфигурации в GUI
        app = gui.ChatBotApp(root, sites_data, redis_data)
        root.mainloop()
    else:
        print("Не удалось загрузить конфигурацию сайтов. Запуск приложения невозможен.")
        # Показываем простое окно с ошибкой
        error_root = tk.Tk()
        error_root.withdraw() # Скрываем основное пустое окно
        tk.messagebox.showerror("Ошибка конфигурации",
                               f"Не удалось загрузить конфигурацию сайтов из {CONFIG_FILE}.\n" +
                               "Проверьте файл и смотрите ошибки в консоли.")
        error_root.destroy()