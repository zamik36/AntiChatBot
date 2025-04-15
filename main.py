import tkinter as tk
import json
import gui # Импортируем наш модуль GUI

CONFIG_FILE = 'config.json'

def load_config(filename):
    """Загружает конфигурацию из JSON файла, применяя настройки по умолчанию."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            full_config = json.load(f)

        defaults = full_config.get('_defaults', {})
        sites_config = full_config.get('sites', {})
        processed_config = {}

        for site_name, site_specific_config in sites_config.items():
            # Начинаем с копии настроек по умолчанию
            current_site_config = defaults.copy()
            # Обновляем/добавляем специфичные настройки сайта
            # Это глубокое обновление для вложенных словарей типа 'selectors'
            for key, value in site_specific_config.items():
                if isinstance(value, dict) and isinstance(current_site_config.get(key), dict):
                    current_site_config[key].update(value)
                else:
                    current_site_config[key] = value
            processed_config[site_name] = current_site_config

        print(f"Конфигурация успешно загружена и обработана из {filename}")
        return processed_config # Возвращаем только обработанные конфиги сайтов

    except FileNotFoundError:
        print(f"Ошибка: Файл конфигурации {filename} не найден.")
        return None
    except json.JSONDecodeError:
        print(f"Ошибка: Неверный формат JSON в файле {filename}.")
        return None
    except Exception as e:
        print(f"Непредвиденная ошибка при загрузке конфигурации: {e}")
        return None

if __name__ == "__main__":
    config_data = load_config(CONFIG_FILE)

    if config_data:
        root = tk.Tk()
        app = gui.ChatBotApp(root, config_data)
        root.mainloop()
    else:
        print("Не удалось загрузить конфигурацию. Запуск приложения невозможен.")
        # Можно показать сообщение об ошибке и в простом окне Tkinter
        error_root = tk.Tk()
        error_root.title("Ошибка")
        tk.Label(error_root, text=f"Не удалось загрузить {CONFIG_FILE}.\nСмотрите ошибки в консоли.", padx=20, pady=20).pack()
        error_root.mainloop()