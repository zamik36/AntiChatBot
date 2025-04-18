import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import threading
import redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError
import os
from dotenv import load_dotenv
import time
import traceback
import uuid

# --- Загрузка переменных окружения (для Redis) ---
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", 'localhost')
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CONFIG_FILE = 'config.json'

# --- Каналы Redis --- (согласованные с chat_logic и chat_service)
SESSION_START_REQUEST_CHANNEL = "antichatbot:session_start_request"
SESSION_STATUS_CHANNEL_TEMPLATE = "antichatbot:session_status:{session_id}"
USER_READY_CHANNEL_TEMPLATE = "antichatbot:user_ready:{session_id}"
SESSION_CLOSE_REQUEST_TEMPLATE = "antichatbot:session_close_request:{session_id}"


class ChatBotApp:
    # Убираем config_redis из конструктора, т.к. используем .env
    def __init__(self, root, config_sites):
        self.root = root
        self.config_sites = config_sites # Конфигурация сайтов
        self.sites = list(config_sites.keys()) if config_sites else []

        # Атрибуты для управления сессией и Redis
        self.current_session_id = None
        self.redis_client = None
        self.redis_pubsub = None
        self.redis_listener_thread = None
        self.is_listening_redis = False
        self.stop_redis_listener_flag = threading.Event() # Флаг для остановки слушателя
        self.last_displayed_status = None # <-- Добавляем атрибут для отслеживания последнего статуса

        # --- Инициализация GUI --- (остается похожей)
        self.root.title("АнтиЧатБот - Клиент")
        self.root.geometry("600x500")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        control_frame = tk.Frame(root)
        control_frame.pack(pady=10, padx=10, fill=tk.X)

        tk.Label(control_frame, text="Выберите сайт:").pack(side=tk.LEFT, padx=(0, 5))
        self.site_combobox = ttk.Combobox(control_frame, values=self.sites, state="readonly", width=40)
        if self.sites:
            self.site_combobox.current(0)
        else:
            self.site_combobox['values'] = ["Нет сайтов в config.json!"]
            self.site_combobox.current(0)
            self.site_combobox.config(state=tk.DISABLED)
        self.site_combobox.pack(side=tk.LEFT, expand=True, fill=tk.X)

        button_frame = tk.Frame(root)
        button_frame.pack(pady=5, padx=10)

        # Меняем команду кнопки "Начать диалог"
        self.start_button = tk.Button(button_frame, text="Начать диалог", command=self.request_session_start, width=25, height=2, state=tk.DISABLED) # Начнем с DISABLED
        self.start_button.pack(side=tk.LEFT, padx=5)

        # Меняем команду кнопки "Продолжить"
        self.continue_button = tk.Button(button_frame, text="Продолжить (после формы)", command=self.signal_user_ready, width=25, state=tk.DISABLED)
        self.continue_button.pack(side=tk.LEFT, padx=5)

        status_frame = tk.LabelFrame(root, text="Статус и Логи Сессии", padx=5, pady=5)
        status_frame.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)

        self.status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=15, state='disabled')
        self.status_text.pack(expand=True, fill=tk.BOTH)

        # --- Подключение к Redis и запуск слушателя --- #
        self.connect_redis_and_start_listener()

    def update_status_display(self, message):
        """Обновляет текстовое поле статуса в главном потоке GUI."""
        # --- ДОБАВЛЕНО: Проверка на дублирование --- #
        if message == self.last_displayed_status:
            return # Не отображаем то же самое сообщение снова
        self.last_displayed_status = message # Запоминаем последнее отображенное сообщение
        # --- КОНЕЦ ПРОВЕРКИ --- #

        # Эта функция должна вызываться из основного потока, например, через root.after
        # Теперь напрямую обновляем виджет, т.к. обработка идет в главном потоке
        if message == "WAITING_FOR_FORM_INPUT":
            display_message = (
                "=============================================================\n"
                "ACTION REQUIRED / ТРЕБУЕТСЯ ДЕЙСТВИЕ:\n"
                "=============================================================\n"
                "Пожалуйста, перейдите в окно браузера (открытое ChatService).\n"
                "Заполните все необходимые поля в форме чата "
                "(имя, email, телефон, согласие и т.п.).\n"
                "Нажмите кнопку начала чата НА САЙТЕ (например, 'Начать чат', 'Отправить').\n\n"
                ">>> После появления интерфейса чата в браузере, нажмите кнопку \n"
                "    'Продолжить (после формы)' ЗДЕСЬ, в этой программе. <<<\n"
                "============================================================="
            )
            self.status_text.configure(state='normal')
            self.status_text.insert(tk.END, display_message + "\n\n")
            self.status_text.configure(state='disabled')
            # Активируем кнопку "Продолжить"
            self.continue_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.DISABLED) # Блокируем старт на время ожидания
        elif message.startswith("КРИТИЧЕСКАЯ") or message.startswith("🏁 Завершено") or message.startswith("✅ УСПЕХ"):
             # Сообщения об ошибках, завершении или успехе
             self.status_text.configure(state='normal')
             self.status_text.insert(tk.END, f"\n--- {message} ---\n\n")
             self.status_text.configure(state='disabled')
             if message.startswith("КРИТИЧЕСКАЯ"):
                  messagebox.showerror("Критическая ошибка сессии", message)
             elif message.startswith("🏁 Завершено"):
                  messagebox.showinfo("Сессия завершена", message)
             self.reset_ui_after_session() # Сбрасываем интерфейс
        else:
            # Обычное сообщение о статусе
            self.status_text.configure(state='normal')
            self.status_text.insert(tk.END, message + "\n")
            self.status_text.configure(state='disabled')

        self.status_text.see(tk.END)

    def connect_redis_and_start_listener(self):
        """Пытается подключиться к Redis и запустить слушатель статуса."""
        try:
            self.status_text.configure(state='normal')
            self.status_text.insert(tk.END, f"Подключение к Redis ({REDIS_HOST}:{REDIS_PORT})...\n")
            self.status_text.configure(state='disabled')
            self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            self.redis_client.ping()
            self.status_text.configure(state='normal')
            self.status_text.insert(tk.END, "Успешное подключение к Redis!\n")
            self.status_text.configure(state='disabled')
            # Активируем кнопку старта, если Redis подключен и есть сайты
            if self.sites:
                self.start_button.config(state=tk.NORMAL)
            # Запускаем слушатель в отдельном потоке (если еще не запущен)
            if not self.is_listening_redis:
                 self.stop_redis_listener_flag.clear()
                 self.redis_listener_thread = threading.Thread(target=self.redis_status_listener, daemon=True)
                 self.redis_listener_thread.start()
                 self.is_listening_redis = True
        except (ConnectionError, TimeoutError, RedisError) as e:
             error_msg = f"Ошибка подключения к Redis: {e}\nСервис чата и бот не будут работать.\nПроверьте, запущен ли Redis сервер.\n"
             self.status_text.configure(state='normal')
             self.status_text.insert(tk.END, error_msg)
             self.status_text.configure(state='disabled')
             messagebox.showerror("Ошибка Redis", error_msg)
             self.start_button.config(state=tk.DISABLED)
        except Exception as e:
             error_msg = f"Непредвиденная ошибка при подключении к Redis: {e}\n"
             self.status_text.configure(state='normal')
             self.status_text.insert(tk.END, error_msg)
             self.status_text.configure(state='disabled')
             messagebox.showerror("Ошибка", error_msg)
             self.start_button.config(state=tk.DISABLED)

    def redis_status_listener(self):
        """Слушает сообщения статуса для ТЕКУЩЕЙ сессии в Redis."""
        listener_instance_id = str(uuid.uuid4())[:4] # Unique ID for this listener instance/thread for logging
        print(f"[GUI] Поток слушателя Redis ({listener_instance_id}) запущен.")

        while not self.stop_redis_listener_flag.is_set():
            # --- ЛОГ: Начало итерации цикла ---
            time.sleep(0.1) # Небольшая пауза для предотвращения 100% CPU

            if self.current_session_id and self.redis_client:
                status_channel = SESSION_STATUS_CHANNEL_TEMPLATE.format(session_id=self.current_session_id)
                # --- ЛОГ: Проверка pubsub и подписка ---
                if not self.redis_pubsub:
                    try:
                        self.redis_pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
                        # --- ЛОГ: Перед подпиской ---
                        self.redis_pubsub.subscribe(status_channel)
                        # --- ЛОГ: После подписки ---
                        print(f"[GUI] Успешная подписка на статус сессии: {status_channel}")
                        # Добавим сообщение в GUI о подписке
                        self.root.after(0, self.update_status_display, f"[INFO] Ожидание статуса сессии {self.current_session_id}...")
                    except (ConnectionError, TimeoutError, RedisError, AttributeError) as e:
                        print(f"[GUI_LISTENER_THREAD {listener_instance_id}] ERROR during subscribe: {e}")
                        self.redis_pubsub = None # Сбрасываем для повторной попытки
                        time.sleep(2)
                        continue # Попробуем подписаться снова
                    except Exception as e:
                         print(f"[GUI_LISTENER_THREAD {listener_instance_id}] UNEXPECTED ERROR during subscribe: {e}")
                         traceback.print_exc()
                         self.redis_pubsub = None
                         time.sleep(5)
                         continue

                # Если есть pubsub, слушаем сообщения
                if self.redis_pubsub:
                    try:
                        message = self.redis_pubsub.get_message(timeout=1.0)

                        if message and message['type'] == 'message':
                            status_update = message['data']
                            # --- СУЩЕСТВУЮЩИЙ ЛОГ ---
                            self.root.after(0, self.update_status_display, status_update)
                        # else: # Если сообщение None или не 'message'
                        #     if message: print(f"[GUI_LISTENER_THREAD {listener_instance_id}] Ignored message (type: {message.get('type')})")
                        #     # Просто продолжаем цикл

                    except TimeoutError:
                        continue # Это нормально, просто нет сообщений
                    except (ConnectionError, RedisError, AttributeError) as e:
                        # --- ЛОГ: Ошибка соединения ---
                        print(f"[GUI] Ошибка соединения Redis при получении статуса: {e}. Переподключение...")
                        if self.redis_pubsub:
                            try: self.redis_pubsub.unsubscribe()
                            except Exception: pass
                            try: self.redis_pubsub.close()
                            except Exception: pass
                        self.redis_pubsub = None
                        time.sleep(2)
                    except Exception as e:
                         # --- ЛОГ: Неожиданная ошибка ---
                         print(f"[GUI] Неожиданная ошибка при получении статуса: {e}")
                         traceback.print_exc()
                         if self.redis_pubsub:
                             try: self.redis_pubsub.unsubscribe()
                             except Exception: pass
                             try: self.redis_pubsub.close()
                             except Exception: pass
                         self.redis_pubsub = None
                         time.sleep(5)
            else:
                # Если нет активной сессии или клиента Redis, просто ждем
                time.sleep(1)

        print(f"[GUI] Поток слушателя Redis ({listener_instance_id}) остановлен.")
        self.is_listening_redis = False

    def request_session_start(self):
        """Отправляет запрос на запуск новой сессии в Redis."""
        if not self.redis_client:
            messagebox.showerror("Ошибка Redis", "Нет соединения с Redis. Не могу запустить сессию.")
            self.connect_redis_and_start_listener() # Попытка переподключения
            return

        selected_site = self.site_combobox.get()
        if not selected_site or selected_site == "Нет сайтов в config.json!":
            messagebox.showerror("Ошибка", "Сайт не выбран или конфигурация пуста.")
            return

        # Блокируем UI перед отправкой запроса
        self.start_button.config(state=tk.DISABLED, text="Запрос отправлен...")
        self.continue_button.config(state=tk.DISABLED)
        self.site_combobox.config(state=tk.DISABLED)
        self.status_text.configure(state='normal')
        self.status_text.delete('1.0', tk.END)
        self.status_text.insert(tk.END, f"--- Запрос на запуск сессии для сайта: {selected_site} ---\n")
        self.status_text.configure(state='disabled')

        try:
            self.current_session_id = str(uuid.uuid4())
            request_data = json.dumps({"site_name": selected_site, "session_id": self.current_session_id})

            # --- ЛОГ: Перед отправкой запроса из GUI --- #
            published_count = self.redis_client.publish(SESSION_START_REQUEST_CHANNEL, request_data)

            if published_count > 0:
                self.status_text.configure(state='normal')
                self.status_text.insert(tk.END, f"Запрос на сессию {self.current_session_id} отправлен. Ожидание статуса...\n")
                self.status_text.configure(state='disabled')
                # Теперь слушатель redis_status_listener будет использовать self.current_session_id
                # Нужно переподписаться, если уже слушали что-то другое
                if self.redis_pubsub:
                     try: self.redis_pubsub.unsubscribe()
                     except Exception: pass
                     try: self.redis_pubsub.close()
                     except Exception: pass
                     self.redis_pubsub = None # Сброс для переподписки в цикле слушателя
            else:
                 # Если 0, значит нет подписчиков (ChatService не запущен?)
                 error_msg = "Ошибка: Запрос на старт сессии не был получен ни одним сервисом. Запущен ли ChatService?"
                 messagebox.showerror("Ошибка отправки", error_msg)
                 self.status_text.configure(state='normal')
                 self.status_text.insert(tk.END, error_msg + "\n")
                 self.status_text.configure(state='disabled')
                 self.reset_ui_after_session() # Сбрасываем UI

        except (ConnectionError, TimeoutError, RedisError) as e:
            messagebox.showerror("Ошибка Redis", f"Не удалось отправить запрос на старт сессии: {e}")
            self.reset_ui_after_session()
        except Exception as e:
             messagebox.showerror("Ошибка", f"Непредвиденная ошибка при запросе старта сессии: {e}")
             traceback.print_exc()
             self.reset_ui_after_session()

    def signal_user_ready(self):
        """Отправляет сигнал готовности пользователя в Redis для текущей сессии."""
        if not self.redis_client:
            messagebox.showerror("Ошибка Redis", "Нет соединения с Redis. Не могу отправить сигнал.")
            return
        if not self.current_session_id:
            messagebox.showerror("Ошибка", "Нет активной сессии для отправки сигнала.")
            return

        self.continue_button.config(state=tk.DISABLED)
        user_ready_channel = USER_READY_CHANNEL_TEMPLATE.format(session_id=self.current_session_id)
        try:
            print(f"[GUI] Отправка сигнала готовности для сессии {self.current_session_id}")
            # Отправляем просто '1' как сигнал
            published_count = self.redis_client.publish(user_ready_channel, "1")
            if published_count > 0:
                 self.update_status_display(f">>> Сигнал готовности для сессии {self.current_session_id} отправлен.")
        except (ConnectionError, TimeoutError, RedisError) as e:
             messagebox.showerror("Ошибка Redis", f"Не удалось отправить сигнал готовности: {e}")
             # Возможно, стоит снова активировать кнопку?
             self.continue_button.config(state=tk.NORMAL) # Даем шанс попробовать еще раз
        except Exception as e:
             messagebox.showerror("Ошибка", f"Непредвиденная ошибка при отправке сигнала готовности: {e}")
             traceback.print_exc()
             self.continue_button.config(state=tk.NORMAL)

    def reset_ui_after_session(self):
        """Сбрасывает кнопки и комбобокс после завершения/ошибки сессии."""
        print("[GUI] Сброс UI после сессии.")
        self.start_button.config(state=tk.NORMAL if self.redis_client and self.sites else tk.DISABLED, text="Начать диалог")
        self.continue_button.config(state=tk.DISABLED)
        if self.sites:
             self.site_combobox.config(state="readonly")
        # Отписываемся от старого канала статуса
        if self.redis_pubsub:
            try: self.redis_pubsub.unsubscribe()
            except Exception: pass
            try: self.redis_pubsub.close()
            except Exception: pass
        self.redis_pubsub = None
        self.current_session_id = None # Сбрасываем ID текущей сессии

    def on_closing(self):
        """Обработчик закрытия окна."""
        print("Окно закрывается...")
        
        # --- ДОБАВЛЕНО: Отправка сигнала закрытия сессии --- 
        if self.current_session_id and self.redis_client:
            close_channel = SESSION_CLOSE_REQUEST_TEMPLATE.format(session_id=self.current_session_id)
            try:
                print(f"[GUI] Отправка сигнала закрытия для сессии {self.current_session_id}")
                # Отправляем просто 'close' как сигнал
                self.redis_client.publish(close_channel, "close")
                # Даем немного времени на отправку и обработку сигнала перед закрытием соединения
                time.sleep(0.5) 
            except (ConnectionError, TimeoutError, RedisError) as e:
                print(f"[GUI] Ошибка Redis при отправке сигнала закрытия: {e}")
            except Exception as e:
                print(f"[GUI] Непредвиденная ошибка при отправке сигнала закрытия: {e}")
        # --- КОНЕЦ ДОБАВЛЕНИЯ --- 

        # Останавливаем слушатель Redis
        self.stop_redis_listener_flag.set()
        if self.redis_listener_thread and self.redis_listener_thread.is_alive():
             print("Ожидание завершения потока слушателя Redis...")
             self.redis_listener_thread.join(timeout=1.0) # Уменьшим таймаут ожидания

        # Закрываем соединение Redis, если оно есть
        if self.redis_pubsub:
            try: self.redis_pubsub.unsubscribe()
            except Exception as e: print(f"Ошибка отписки Redis при закрытии: {e}")
            try: self.redis_pubsub.close()
            except Exception as e: print(f"Ошибка закрытия pubsub Redis при закрытии: {e}")
        if self.redis_client:
            try: self.redis_client.close()
            except Exception as e: print(f"Ошибка закрытия клиента Redis при закрытии: {e}")
            print("Соединение с Redis закрыто.")

        self.root.destroy()

# --- Загрузка и ОБРАБОТКА конфигурации сайтов --- #
def load_site_config(filename=CONFIG_FILE):
    """Загружает конфигурацию из JSON, применяет _defaults к сайтам и возвращает словарь сайтов."""
    full_config = None
    processed_sites_config = {}

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            full_config = json.load(f)
    except FileNotFoundError:
        messagebox.showerror("Ошибка конфигурации", f"Файл {filename} не найден.")
        return None
    except json.JSONDecodeError as e:
        messagebox.showerror("Ошибка конфигурации", f"Неверный формат JSON в {filename}: {e}")
        return None
    except Exception as e:
         messagebox.showerror("Ошибка", f"Непредвиденная ошибка загрузки {filename}: {e}")
         return None

    # --- Логика обработки _defaults (из main.py) --- #
    defaults = full_config.get('_defaults', {})
    sites_config_raw = full_config.get('sites', {})

    if not sites_config_raw: # Проверка, есть ли вообще секция sites
        print("В файле конфигурации не найден раздел 'sites' или он пуст.")
        messagebox.showwarning("Ошибка конфигурации", "В файле конфигурации не найден раздел 'sites' или он пуст.")
        # Возвращаем пустой словарь, чтобы GUI мог запуститься, но без сайтов
        return {}

    for site_name, site_specific_config in sites_config_raw.items():
        # Начинаем с копии настроек по умолчанию
        current_site_config = {}
        for key, value in defaults.items():
            if isinstance(value, dict): # Глубокое копирование для словарей (emulation_options, selectors)
                current_site_config[key] = value.copy()
            else:
                current_site_config[key] = value

        # Обновляем/перезаписываем настройками конкретного сайта
        for key, value in site_specific_config.items():
            if isinstance(value, dict) and isinstance(current_site_config.get(key), dict):
                # Обновляем существующий вложенный словарь
                current_site_config[key].update(value)
            else:
                # Перезаписываем или добавляем новые ключи
                current_site_config[key] = value
        processed_sites_config[site_name] = current_site_config
    # --- Конец логики обработки _defaults --- #

    print(f"Конфигурация сайтов успешно загружена и обработана из {filename}")
    return processed_sites_config # Возвращаем ТОЛЬКО обработанный словарь сайтов

# --- Главная часть --- #
if __name__ == "__main__":
    # Загружаем уже обработанный конфиг сайтов
    config_sites_data = load_site_config()
    # Проверяем, вернулся ли словарь (даже пустой - это успех загрузки)
    if config_sites_data is not None:
        # Просто передаем полученный словарь в приложение
        root = tk.Tk()
        app = ChatBotApp(root, config_sites_data) # <-- Передаем config_sites_data
        root.mainloop()
    else:
        # Ошибка загрузки файла уже показана в load_site_config
        print("Не удалось загрузить конфигурацию сайтов (критическая ошибка). Запуск GUI отменен.")
        # Можно добавить messagebox и здесь, но он уже был в load_site_config