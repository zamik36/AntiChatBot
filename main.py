import tkinter as tk
import json
import gui # Импортируем наш модуль GUI

CONFIG_FILE = 'config.json'

def load_config(filename):
    """Загружает конфигурацию из JSON файла."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"Конфигурация успешно загружена из {filename}")
        return config
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