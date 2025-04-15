# gui.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox # Добавили messagebox
import json
import threading # Для запуска логики чата в отдельном потоке
import chat_logic # Импортируем нашу логику чата
from queue import Queue # Для безопасной передачи сообщений из потока в GUI
# Добавляем импорт Event
from threading import Event

class ChatBotApp:
    def __init__(self, root, config_sites, config_redis):
        self.root = root
        self.config_sites = config_sites # Конфигурация сайтов
        self.config_redis = config_redis # Конфигурация Redis
        self.sites = list(config_sites.keys()) if config_sites else []

        # Потокобезопасная очередь для статуса
        self.status_queue = Queue()
        # Событие для сигнала "пользователь готов" (создается при старте потока)
        self.user_ready_event = None
        self.chat_thread = None # Добавляем атрибут для потока

        self.root.title("АнтиЧатБот")
        self.root.geometry("600x500") # Немного увеличим окно
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Обработка закрытия окна

        # --- Фрейм для выбора сайта и кнопок ---
        control_frame = tk.Frame(root)
        control_frame.pack(pady=10, padx=10, fill=tk.X)

        tk.Label(control_frame, text="Выберите сайт:").pack(side=tk.LEFT, padx=(0, 5))
        self.site_combobox = ttk.Combobox(control_frame, values=self.sites, state="readonly", width=40)
        if self.sites:
            self.site_combobox.current(0)
        else:
             # Если нет сайтов, выводим сообщение и блокируем интерфейс
             self.site_combobox['values'] = ["Нет сайтов в config.json!"]
             self.site_combobox.current(0)
             self.site_combobox.config(state=tk.DISABLED)
        self.site_combobox.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # --- Фрейм для кнопок Старт/Продолжить ---
        button_frame = tk.Frame(root)
        button_frame.pack(pady=5, padx=10)

        self.start_button = tk.Button(button_frame, text="Начать диалог", command=self.start_chat_thread, width=25, height=2, state=tk.NORMAL if self.sites else tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.continue_button = tk.Button(button_frame, text="Продолжить (после формы)", command=self.on_continue_clicked, width=25, state=tk.DISABLED)
        self.continue_button.pack(side=tk.LEFT, padx=5)

        # --- Область статуса ---
        status_frame = tk.LabelFrame(root, text="Статус и Логи", padx=5, pady=5)
        status_frame.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)

        self.status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=15, state='disabled')
        self.status_text.pack(expand=True, fill=tk.BOTH)

        # Запускаем проверку очереди статуса
        self.check_status_queue()

    def update_status(self, message):
        """Безопасно добавляет сообщение в очередь для обновления GUI."""
        self.status_queue.put(message)

    def process_status_message(self, message):
        """Обрабатывает сообщение из очереди и обновляет GUI."""
        if message == "WAITING_FOR_FORM_INPUT":
            display_message = (
                "=============================================================\n"
                "ACTION REQUIRED / ТРЕБУЕТСЯ ДЕЙСТВИЕ:\n"
                "=============================================================\n"
                "Пожалуйста, перейдите в окно браузера.\n"
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
        elif message.startswith("КРИТИЧЕСКАЯ ОШИБКА:"):
             self.status_text.configure(state='normal')
             self.status_text.insert(tk.END, message + "\n\n")
             self.status_text.configure(state='disabled')
             messagebox.showerror("Критическая ошибка", message)
             self.reset_ui() # Сбрасываем интерфейс в исходное состояние
        else:
            self.status_text.configure(state='normal')
            self.status_text.insert(tk.END, message + "\n") # Убрал двойной перенос строки
            self.status_text.configure(state='disabled')

        self.status_text.see(tk.END)

    def check_status_queue(self):
        """Проверяет очередь статуса и вызывает обработчик."""
        try:
            while True:
                message = self.status_queue.get_nowait()
                self.process_status_message(message)
        except Exception: # Очередь пуста
            pass
        # Перезапускаем проверку
        self.root.after(100, self.check_status_queue)

    def start_chat_thread(self):
        """Запускает логику чата в отдельном потоке."""
        selected_site = self.site_combobox.get()
        if not selected_site or selected_site == "Нет сайтов в config.json!":
            messagebox.showerror("Ошибка", "Сайт не выбран или конфигурация пуста.")
            return

        # Блокируем кнопки и очищаем статус
        self.start_button.config(state=tk.DISABLED, text="В процессе...")
        self.continue_button.config(state=tk.DISABLED)
        self.site_combobox.config(state=tk.DISABLED)
        self.status_text.configure(state='normal')
        self.status_text.delete('1.0', tk.END)
        self.status_text.configure(state='disabled')
        self.update_status(f"--- Запуск сессии для сайта: {selected_site} ---")

        self.user_ready_event = Event()

        # Передаем ОБА конфига в поток
        self.chat_thread = threading.Thread(
            target=chat_logic.run_chat_session,
            args=(selected_site, self.config_sites, self.update_status, self.user_ready_event, self.config_redis),
            daemon=True
        )
        self.chat_thread.start()

        self.root.after(500, self.check_thread_completion)

    def on_continue_clicked(self):
        """Вызывается при нажатии кнопки 'Продолжить выполнение'."""
        self.continue_button.config(state=tk.DISABLED)
        if self.user_ready_event:
            self.update_status(">>> Пользователь подтвердил ввод формы. Продолжаем...")
            self.user_ready_event.set()

    def check_thread_completion(self):
        """Проверяет, завершился ли поток чата."""
        if self.chat_thread and self.chat_thread.is_alive():
            self.root.after(500, self.check_thread_completion)
        else:
             if self.start_button['text'] == "В процессе...": # Проверяем, был ли запущен процесс
                 self.update_status("--- Сессия завершена --- ")
                 self.reset_ui()

    def reset_ui(self):
        """Сбрасывает кнопки и комбобокс в исходное состояние."""
        self.start_button.config(state=tk.NORMAL if self.sites else tk.DISABLED, text="Начать диалог")
        self.continue_button.config(state=tk.DISABLED)
        if self.sites:
             self.site_combobox.config(state="readonly")

    def on_closing(self):
        """Обработчик закрытия окна."""
        # Здесь можно добавить логику для "мягкой" остановки потока, если нужно
        # Например, установить какой-то флаг и дождаться завершения
        # if self.chat_thread and self.chat_thread.is_alive():
        #     if messagebox.askyesno("Подтверждение", "Процесс еще активен. Прервать?"):
        #         # Логика остановки потока...
        #         self.root.destroy()
        #     else:
        #         return # Не закрывать окно
        # else:
        #     self.root.destroy()
        print("Окно закрывается.")
        self.root.destroy()