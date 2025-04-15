# gui.py
import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import threading # Для запуска логики чата в отдельном потоке
import chat_logic # Импортируем нашу логику чата
from queue import Queue # Для безопасной передачи сообщений из потока в GUI
# Добавляем импорт Event
from threading import Event

class ChatBotApp:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.sites = list(config.keys()) # Получаем список сайтов из конфига

        # Потокобезопасная очередь для статуса
        self.status_queue = Queue()
        # Событие для сигнала "пользователь готов" (создается при старте потока)
        self.user_ready_event = None

        self.root.title("АнтиЧатБот")
        self.root.geometry("550x450") # Немного увеличим окно

        # --- Элементы интерфейса ---
        # Выбор сайта
        tk.Label(root, text="Выберите сайт:").pack(pady=(10, 0))
        self.site_combobox = ttk.Combobox(root, values=self.sites, state="readonly", width=50)
        if self.sites:
            self.site_combobox.current(0) # Выбрать первый сайт по умолчанию
        self.site_combobox.pack(pady=5)

        # Кнопка Старт
        self.start_button = tk.Button(root, text="Начать диалог", command=self.start_chat_thread, width=25, height=2)
        self.start_button.pack(pady=10)

        # НОВАЯ Кнопка Продолжить
        self.continue_button = tk.Button(root, text="Продолжить выполнение", command=self.on_continue_clicked, width=25, state=tk.DISABLED)
        self.continue_button.pack(pady=5)

        # Область для вывода статуса
        tk.Label(root, text="Статус:").pack(pady=(10, 0))
        self.status_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=70, height=12, state='disabled')
        self.status_text.pack(pady=5, padx=10, expand=True, fill=tk.BOTH)

        # Запускаем проверку очереди статуса
        self.check_status_queue()

    def update_status(self, message):
        """Безопасно обновляет текстовое поле статуса из любого потока."""
        # Добавляем специальный маркер для ожидания формы
        if message == "WAITING_FOR_FORM_INPUT":
            # Отображаем инструкцию и активируем кнопку "Продолжить"
            display_message = ("---> ДЕЙСТВИЕ ПОЛЬЗОВАТЕЛЯ:\n"
                               "Пожалуйста, заполните форму в браузере "
                               "(имя, телефон, согласие и т.д.) и нажмите кнопку 'Начать чат' (или аналогичную) НА САЙТЕ.\n"
                               "После того как увидите интерфейс чата, нажмите кнопку 'Продолжить выполнение' ЗДЕСЬ в программе.")
            self.status_queue.put(display_message)
            # Активируем кнопку (безопасно через главный поток)
            self.root.after(0, lambda: self.continue_button.config(state=tk.NORMAL))
        else:
            # Обычное сообщение статуса
            self.status_queue.put(message)

    def check_status_queue(self):
        """Проверяет очередь и обновляет GUI, если есть сообщения."""
        try:
            while True: # Обрабатываем все сообщения в очереди за раз
                message = self.status_queue.get_nowait() # Не блокировать, если пусто
                self.status_text.configure(state='normal') # Включить редактирование
                self.status_text.insert(tk.END, message + "\n\n") # Добавим отступ между сообщениями
                self.status_text.configure(state='disabled') # Выключить редактирование
                self.status_text.see(tk.END) # Прокрутить вниз
        except Exception: # Ловим Queue.empty (имя может отличаться в разных версиях)
            pass # Очередь пуста, ничего не делаем

        # Перезапускаем проверку через 100 мс
        self.root.after(100, self.check_status_queue)

    def start_chat_thread(self):
        """Запускает логику чата в отдельном потоке."""
        selected_site = self.site_combobox.get()
        if not selected_site:
            self.update_status("Ошибка: Сайт не выбран.")
            return

        # Блокируем обе кнопки
        self.start_button.config(state=tk.DISABLED, text="В процессе...")
        self.continue_button.config(state=tk.DISABLED) # Убедимся, что она выключена
        self.status_text.configure(state='normal')
        self.status_text.delete('1.0', tk.END) # Очищаем поле статуса
        self.status_text.configure(state='disabled')

        # Создаем НОВОЕ событие для ЭТОЙ сессии чата
        self.user_ready_event = Event()

        # Создаем и запускаем поток
        # Передаем self.update_status И self.user_ready_event в chat_logic
        self.chat_thread = threading.Thread(
            target=chat_logic.run_chat_session,
            args=(selected_site, self.config, self.update_status, self.user_ready_event), # Добавлен user_ready_event
            daemon=True # Поток завершится, если закроется основное окно
        )
        self.chat_thread.start()

        # Запускаем проверку завершения потока, чтобы разблокировать кнопку Старт
        self.root.after(500, self.check_thread_completion)

    # НОВЫЙ метод для кнопки "Продолжить"
    def on_continue_clicked(self):
        """Вызывается при нажатии кнопки 'Продолжить выполнение'."""
        self.continue_button.config(state=tk.DISABLED) # Снова деактивируем кнопку
        if self.user_ready_event:
            self.update_status(">>> Пользователь подтвердил готовность. Продолжаем...")
            self.user_ready_event.set() # Устанавливаем событие, сигнализируя рабочему потоку

    def check_thread_completion(self):
        """Проверяет, завершился ли поток чата, и управляет кнопками."""
        if self.chat_thread and self.chat_thread.is_alive():
            # Поток еще работает, проверим позже
            self.root.after(500, self.check_thread_completion)
        else:
            # Поток завершился, разблокируем кнопку Старт
            self.start_button.config(state=tk.NORMAL, text="Начать диалог")
            # Убедимся, что кнопка Продолжить тоже выключена
            self.continue_button.config(state=tk.DISABLED)
            # Сообщение о завершении теперь выводится в chat_logic