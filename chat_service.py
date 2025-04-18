# chat_service.py
import sys
import os
# Добавляем директорию src в путь поиска модулей
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'src'))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError
import json
import threading
import time
import traceback
from dotenv import load_dotenv
from antichatbot import chat_logic # Наша основная логика чата

# --- Загрузка переменных окружения ---
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", 'localhost')
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CONFIG_FILE = 'config.json'

# --- Каналы Redis --- (Согласованные)
SESSION_START_REQUEST_CHANNEL = "antichatbot:session_start_request"
# Остальные каналы определены в chat_logic

# --- Глобальные переменные ---
redis_client = None
config = {}
active_sessions = {} # Словарь для отслеживания активных сессий {session_id: thread}

# --- Функции ---

def load_config():
    """Загружает конфигурацию из JSON файла."""
    global config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"Конфигурация успешно загружена из {CONFIG_FILE}")
        return True
    except FileNotFoundError:
        print(f"Ошибка: Файл конфигурации {CONFIG_FILE} не найден.")
        return False
    except json.JSONDecodeError as e:
        print(f"Ошибка: Неверный формат JSON в файле {CONFIG_FILE}: {e}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при загрузке конфигурации: {e}")
        return False

def connect_redis():
    """Устанавливает соединение с Redis."""
    global redis_client
    while True:
        try:
            print(f"Попытка подключения к Redis ({REDIS_HOST}:{REDIS_PORT})...")
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            print(f"Успешное подключение к Redis ({REDIS_HOST}:{REDIS_PORT}).")
            redis_client = r
            return True
        except (ConnectionError, TimeoutError, RedisError) as e:
            print(f"Ошибка подключения к Redis: {e}. Повтор через 10 секунд...")
            time.sleep(10)
        except Exception as e:
            print(f"Непредвиденная ошибка при подключении к Redis: {e}. Повтор через 10 секунд...")
            traceback.print_exc()
            time.sleep(10)

def session_runner(site_name, session_id, redis_config_dict):
    """Запускает сессию чата в отдельном потоке."""
    # --- ЛОГ: Начало выполнения потока --- #
    # print(f"[S_RUNNER:{session_id}] Thread started for site '{site_name}'.")
    # --- КОНЕЦ ЛОГА ---
    global config, active_sessions
    print(f"[S:{session_id}] Запуск сессии чата для сайта '{site_name}'...")
    try:
        # Передаем весь конфиг, session_id и параметры Redis
        chat_logic.run_chat_session(site_name, config, session_id, redis_config_dict)
    except Exception as e:
        print(f"[S:{session_id}] КРИТИЧЕСКАЯ ОШИБКА в потоке сессии: {e}")
        traceback.print_exc()
        # Попытка опубликовать ошибку в статус, если возможно
        # Используем шаблон из chat_logic для формирования имени канала
        status_channel = chat_logic.SESSION_STATUS_CHANNEL_TEMPLATE.format(session_id=session_id)
        if redis_client:
            try:
                redis_client.publish(status_channel, f"КРИТИЧЕСКАЯ ОШИБКА ПОТОКА: {e}")
            except Exception as pub_e:
                print(f"[S:{session_id}] Не удалось опубликовать ошибку потока: {pub_e}")
    finally:
        print(f"[S:{session_id}] Сессия чата завершена (поток завершает работу).")
        # Удаляем сессию из активных
        if session_id in active_sessions:
            del active_sessions[session_id]
            print(f"[S:{session_id}] Сессия удалена из списка активных.")

def redis_listener():
    """Слушает канал Redis для запросов на запуск сессий."""
    global redis_client, config, active_sessions
    pubsub = None
    redis_config_dict = {'host': REDIS_HOST, 'port': REDIS_PORT}

    while True:
        if not redis_client or not redis_client.ping():
            print("Переподключение к Redis для слушателя...")
            connect_redis()

        if not config:
             print("Конфигурация не загружена, повторная попытка загрузки...")
             if not load_config():
                  print("Не удалось загрузить конфигурацию. Повтор через 10 секунд...")
                  time.sleep(10)
                  continue

        try:
            pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(SESSION_START_REQUEST_CHANNEL)
            print(f"Слушатель Redis: Подписка на канал '{SESSION_START_REQUEST_CHANNEL}' установлена.")

            for message in pubsub.listen():
                channel = message['channel']
                session_id = None # Инициализируем
                site_name = None
                try:
                    request_data_str = message['data']
                    # --- ЛОГ: Получение сообщения слушателем --- #
                    # print(f"[LISTENER] Raw message received on {channel}: {request_data_str}")
                    # --- КОНЕЦ ЛОГА ---
                    request_data = json.loads(request_data_str)
                    site_name = request_data.get("site_name")
                    session_id = request_data.get("session_id")

                    if not site_name or not session_id:
                         print(f"[LISTENER_WARN] Incomplete data: {request_data_str}. Skipping.")
                         continue

                    print(f"[LISTENER] Parsed request: Site='{site_name}', SessionID={session_id}")

                except json.JSONDecodeError:
                    print(f"[LISTENER_ERR] JSON Decode Error: {message.get('data')}. Skipping.")
                    continue
                except Exception as e:
                    print(f"[LISTENER_ERR] Error processing message: {e}")
                    traceback.print_exc()
                    continue

                # Проверяем, есть ли такой сайт в разделе "sites" конфига
                sites_config = config.get("sites", {}) 
                
                if site_name not in sites_config:
                    print(f"[LISTENER_WARN] Config for '{site_name}' not found. Ignoring.")
                    continue

                if session_id in active_sessions:
                    print(f"[LISTENER_WARN] Session '{session_id}' already active. Ignoring.")
                    continue
                
                # --- ЛОГ: Перед запуском потока --- #
                print(f"[SERVICE] Запуск потока для SessionID={session_id}, Site='{site_name}'")
                # --- КОНЕЦ ЛОГА ---
                session_thread = threading.Thread(
                    target=session_runner,
                    args=(site_name, session_id, redis_config_dict),
                    daemon=True
                )
                active_sessions[session_id] = session_thread
                session_thread.start()

        except (ConnectionError, TimeoutError, RedisError) as e:
            print(f"Слушатель Redis: Потеряно соединение ({e}). Попытка переподключения...")
            if pubsub:
                try: pubsub.close()
                except Exception: pass
            pubsub = None
            redis_client = None
            time.sleep(5)
        except Exception as e:
            print(f"Слушатель Redis: Критическая ошибка ({e}). Перезапуск слушателя через 10 секунд...")
            traceback.print_exc()
            if pubsub:
                try: pubsub.close()
                except Exception: pass
            pubsub = None
            redis_client = None
            time.sleep(10)

def main():
    print("--- Запуск Chat Service ---")
    if not load_config():
        print("Не удалось загрузить конфигурацию при старте. Сервис не может работать.")
        return
    if not connect_redis():
         print("Не удалось подключиться к Redis при старте. Сервис не может работать.")
         return

    redis_listener()

    print("--- Chat Service остановлен ---")

if __name__ == "__main__":
    main()