# telegram_bot.py
import redis
# Импортируем специфичные ошибки Redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError
import telegram
# Используем Application и ApplicationBuilder вместо Updater
from telegram.ext import Application, MessageHandler, filters, CommandHandler
# Импортируем нужные классы ошибок
from telegram.error import Forbidden, BadRequest
import base64
import io
import os
import threading
import time
from dotenv import load_dotenv
import traceback

# --- Загрузка переменных окружения из .env файла ---
load_dotenv()

# --- Настройки --- (Берем из переменных окружения)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YOUR_USER_ID_STR = os.getenv("TELEGRAM_USER_ID")
REDIS_HOST = os.getenv("REDIS_HOST", 'localhost') # По умолчанию localhost
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))   # По умолчанию 6379

# --- Проверка наличия обязательных переменных ---
if not TELEGRAM_TOKEN:
    print("Ошибка: Переменная окружения TELEGRAM_BOT_TOKEN не установлена.")
    print("Пожалуйста, создайте файл .env и добавьте в него TELEGRAM_BOT_TOKEN=ВАШ_ТОКЕН")
    exit()
if not YOUR_USER_ID_STR:
    print("Ошибка: Переменная окружения TELEGRAM_USER_ID не установлена.")
    print("Пожалуйста, создайте файл .env и добавьте в него TELEGRAM_USER_ID=ВАШ_ID")
    exit()
try:
    YOUR_USER_ID = int(YOUR_USER_ID_STR)
except ValueError:
    print(f"Ошибка: Неверный формат TELEGRAM_USER_ID ('{YOUR_USER_ID_STR}'). Должно быть число.")
    exit()

# --- Каналы Redis --- (Используем префикс для ясности)
CAPTCHA_REQUEST_CHANNEL = "antichatbot:captcha_request"
CAPTCHA_SOLUTION_CHANNEL = "antichatbot:captcha_solution"
OPERATOR_NOTIFY_CHANNEL = "antichatbot:operator_notify"
HEARTBEAT_CHANNEL = "antichatbot:heartbeat" # Канал для проверки активности

# --- Инициализация Redis --- (Используем try-except для Redis)
r = None
try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping() # Проверяем соединение
    print(f"Успешное подключение к Redis по адресу {REDIS_HOST}:{REDIS_PORT}")
# Используем более специфичные исключения
except (ConnectionError, TimeoutError, RedisError) as e:
    print(f"Ошибка подключения к Redis ({REDIS_HOST}:{REDIS_PORT}): {e}")
    print("Убедитесь, что Redis сервер запущен и доступен.")
    exit()
except Exception as e:
    print(f"Непредвиденная ошибка при подключении к Redis: {e}")
    exit()

# --- Инициализация Telegram Application (новый способ v20+) ---
# Создаем объект Application
application = Application.builder().token(TELEGRAM_TOKEN).build()
# Получаем объекты bot и job_queue из application
# bot = application.bot # Можно получить bot, но обычно используют context.bot в обработчиках
# job_queue = application.job_queue # JobQueue доступна так

# Глобальный флаг для ожидания решения капчи
waiting_for_captcha = False

# --- Функции бота (асинхронные для v20+) --- 
# Добавляем async/await
async def start(update, context):
    """Обработчик команды /start"""
    user_id = update.effective_chat.id
    print(f"Получена команда /start от пользователя {user_id}")
    if user_id == YOUR_USER_ID:
        # Используем await для асинхронных вызовов
        await context.bot.send_message(chat_id=user_id, text="🤖 Привет! Я АнтиЧатБот Telegram Помощник. Я буду присылать уведомления и запросы на ввод капчи.")
    else:
        await context.bot.send_message(chat_id=user_id, text="⛔ Извините, я работаю только с авторизованным пользователем.")

# Добавляем async/await
async def handle_text(update, context):
    """Обрабатывает текстовые сообщения (предположительно, ответы на капчу)"""
    global waiting_for_captcha
    user_id = update.effective_chat.id

    if user_id != YOUR_USER_ID:
        print(f"Получено сообщение от неавторизованного пользователя {user_id}")
        return # Игнорируем сообщения от других пользователей

    user_text = update.message.text
    print(f"Получен текст от авторизованного пользователя: {user_text}")

    if waiting_for_captcha:
        print(f"Отправка решения капчи '{user_text}' в Redis...")
        try:
            r.publish(CAPTCHA_SOLUTION_CHANNEL, user_text)
            await context.bot.send_message(chat_id=user_id, text=f"✅ Ответ '{user_text}' отправлен приложению.")
            waiting_for_captcha = False # Сбрасываем флаг
        # Улучшенная обработка ошибок Redis при публикации
        except (ConnectionError, TimeoutError, RedisError) as e:
            print(f"Ошибка публикации решения в Redis: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"❌ Ошибка Redis при отправке решения: {e}. Повторите попытку позже.")
            # Не сбрасываем флаг waiting_for_captcha, чтобы пользователь мог попробовать еще раз
        except Exception as e:
            print(f"Непредвиденная ошибка при публикации решения: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"❌ Непредвиденная ошибка при отправке решения: {e}")
            waiting_for_captcha = False # Сбрасываем флаг в случае неизвестной ошибки
    else:
        print("Сообщение получено не во время ожидания капчи, игнорируется.")
        # await context.bot.send_message(chat_id=user_id, text="Сейчас я не ожидаю ввода капчи.")

# --- Асинхронные функции для вызова из job_queue ---
# Эти функции будут вызываться через job_queue, им нужен context
async def send_operator_notification(context):
    job_data = context.job.data # Получаем данные, переданные в job_queue
    chat_id = job_data['chat_id']
    site_name = job_data['site_name']
    try:
        await context.bot.send_message(chat_id=chat_id, text=f"🔔 Оператор подключился на сайте: {site_name}")
    except Forbidden:
         print(f"Ошибка Telegram (Forbidden): Бот заблокирован пользователем {chat_id} или не может инициировать чат.")
    except BadRequest as e:
         print(f"Ошибка Telegram (BadRequest): Не удалось отправить уведомление оператора - {e}")
    except Exception as e:
        print(f"Ошибка отправки уведомления об операторе в Telegram: {e}")

async def send_captcha_request(context):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    img_stream = job_data['image']
    caption = job_data['caption']
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=img_stream, caption=caption)
    except Forbidden:
         print(f"Ошибка Telegram (Forbidden): Бот заблокирован пользователем {chat_id} или не может инициировать чат.")
    except BadRequest as e:
         print(f"Ошибка Telegram (BadRequest): Не удалось отправить фото капчи - {e}")
    except Exception as e:
        print(f"Ошибка отправки фото капчи в Telegram: {e}")

async def send_generic_message(context):
    job_data = context.job.data
    chat_id = job_data['chat_id']
    text = job_data['text']
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Forbidden:
        print(f"Ошибка Telegram (Forbidden): Бот заблокирован пользователем {chat_id} или не может инициировать чат.")
    except BadRequest as e:
        print(f"Ошибка Telegram (BadRequest): Не удалось отправить сообщение - {e}")
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")

def redis_listener():
    """Слушает каналы Redis в отдельном потоке"""
    global waiting_for_captcha

    while True: # Переподключаемся в случае обрыва
        pubsub = None
        try:
            pubsub = r.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(OPERATOR_NOTIFY_CHANNEL, CAPTCHA_REQUEST_CHANNEL, HEARTBEAT_CHANNEL)
            print("Redis Listener: Подписка на каналы установлена.")

            for message in pubsub.listen():
                channel = message['channel']
                data = message['data']
                print(f"Redis Listener: Получено сообщение (канал: {channel})") # Лог

                try:
                    if channel == OPERATOR_NOTIFY_CHANNEL:
                        print(f"Отправка уведомления об операторе пользователю {YOUR_USER_ID}")
                        # Передаем данные в context через data={...}
                        application.job_queue.run_once(send_operator_notification, 0,
                                                   data={'chat_id': YOUR_USER_ID, 'site_name': data},
                                                   name=f"op_notify_{time.time()}") # Уникальное имя для job
                        waiting_for_captcha = False

                    elif channel == CAPTCHA_REQUEST_CHANNEL:
                        print(f"Получен запрос на капчу. Отправка пользователю {YOUR_USER_ID}")
                        waiting_for_captcha = True
                        try:
                            # Убираем префикс 'data:image/png;base64,' если он есть
                            if data.startswith('data:image'):
                                img_data_b64 = data.split(',', 1)[1]
                            else:
                                img_data_b64 = data # Предполагаем, что это уже чистый base64

                            img_bytes = base64.b64decode(img_data_b64)
                            img_file = io.BytesIO(img_bytes)
                            img_file.name = 'captcha.png' # Имя файла важно для Telegram
                            img_file.seek(0)

                            # Запускаем асинхронную отправку фото
                            application.job_queue.run_once(send_captcha_request, 0,
                                                       data={'chat_id': YOUR_USER_ID,
                                                             'image': img_file,
                                                             'caption': "❗ Пожалуйста, введите текст с картинки:"},
                                                       name=f"captcha_{time.time()}")

                        except (base64.binascii.Error, ValueError) as decode_error:
                            print(f"Ошибка декодирования Base64 капчи: {decode_error}")
                            application.job_queue.run_once(send_generic_message, 0,
                                                       data={'chat_id': YOUR_USER_ID,
                                                             'text': f"❌ Получены некорректные данные для капчи."}, 
                                                       name=f"error_{time.time()}")
                        except Exception as e:
                            print(f"Ошибка обработки/отправки изображения капчи: {e}")
                            application.job_queue.run_once(send_generic_message, 0,
                                                        data={'chat_id': YOUR_USER_ID,
                                                              'text': f"❌ Ошибка при обработке запроса на капчу: {e}"},
                                                        name=f"error_{time.time()}")

                    elif channel == HEARTBEAT_CHANNEL:
                        # Можно добавить логику ответа на heartbeat, если нужно
                        pass # Пока просто игнорируем

                except Exception as e:
                    print(f"Ошибка обработки сообщения из Redis (канал: {channel}): {e}")

        # Уточняем перехватываемые исключения для переподключения
        except (ConnectionError, TimeoutError, RedisError) as e:
            print(f"Redis Listener: Потеряно соединение с Redis ({e}). Попытка переподключения через 10 секунд...")
            if pubsub: 
                try: pubsub.close() # Закрываем старый объект перед паузой
                except Exception as close_e: print(f"Ошибка при закрытии pubsub: {close_e}")
            pubsub = None
            time.sleep(10)
        except Exception as e:
            print(f"Redis Listener: Критическая ошибка ({e}). Остановка слушателя.")
            traceback.print_exc()
            break # Выход из цикла while True
        finally:
             if pubsub:
                 try:
                     pubsub.unsubscribe()
                     pubsub.close()
                     print("Redis Listener: Подписка корректно закрыта.")
                 except Exception as close_e:
                     print(f"Redis Listener: Ошибка при закрытии подписки: {close_e}")

# --- Регистрация обработчиков Telegram (через application) ---
# Фильтр для авторизованного пользователя
authorized_user_filter = filters.Chat(chat_id=YOUR_USER_ID)

application.add_handler(CommandHandler('start', start, filters=authorized_user_filter))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & authorized_user_filter, handle_text))
# Добавим обработчик для неавторизованных пользователей на команду start
application.add_handler(CommandHandler('start', start, filters=~authorized_user_filter))

# --- Основная функция --- 
def main():
    # Запускаем слушателя Redis в отдельном потоке
    print("Запуск Redis Listener в отдельном потоке...")
    redis_thread = threading.Thread(target=redis_listener, daemon=True)
    redis_thread.start()

    # Запускаем бота Telegram через Application
    print("Запуск Telegram Bot Polling...")
    # run_polling будет работать пока процесс не будет прерван (например, Ctrl+C)
    application.run_polling()
    print("Бот остановлен.")

if __name__ == '__main__':
    main() 