import asyncio
import re
import os
import sys
import random
import json
from datetime import datetime, timezone
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest, ImportChatInviteRequest
from telethon.tl.types import KeyboardButtonCallback, KeyboardButtonUrl, ReplyInlineMarkup
from colorama import Fore, init

init(autoreset=True)

# === CONFIG ===
MAX_SESSIONS = 10
BOT_USERNAME = "gram_piarbot"
SCAN_MESSAGES = 8
REPORT_IN_SAVED = True
SESSIONS_LOG = "sessions.log"
SESSIONS_DIR = "sessions"
STATUS_FILE = "status.json"
JOINED_CHANNELS_FILE = "joined_channels.json"

# === WEB SESSION CONFIG ===
# Параметры для маскировки под Telegram Web
WEB_DEVICE = {
    "model": "Telegram Web",
    "sys": "Windows 11",
    "app": "WebK 2.1.0"
}

#===== JSON =======
def update_status(session_name, status_text, field="status"):
    data = {}

    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    current = data.get(session_name, {})
    if not isinstance(current, dict):
        current = {"status": current, "guard": "—"}

    current[field] = status_text
    data[session_name] = current

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
def load_joined_channels():
    if not os.path.exists(JOINED_CHANNELS_FILE):
        return {}
    try:
        with open(JOINED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_joined_channels(data):
    with open(JOINED_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def track_joined_channel(session_name, channel_entity):
    if channel_entity is None:
        return
    channel_id = getattr(channel_entity, "id", None) or getattr(channel_entity, "channel_id", None)
    if not channel_id:
        return

    data = load_joined_channels()
    session_channels = data.setdefault(session_name, {})

    # Фиксируем только первую дату вступления, чтобы срок 7 дней считался корректно.
    session_channels.setdefault(str(channel_id), datetime.now(timezone.utc).isoformat())

    save_joined_channels(data)
# === ANTI-FLOOD ===
MIN_ACTION_DELAY = 5.0
MAX_ACTION_DELAY = 7.0
MIN_REST_AFTER_BATCH = 10
MAX_REST_AFTER_BATCH = 20
BATCH_MIN = 5
BATCH_MAX = 7


def log(text, color=Fore.WHITE):
    print(color + text + Fore.RESET)


async def ensure_connected(client, name):
    if client.is_connected():
        return True
    try:
        await client.connect()
        if await client.is_user_authorized():
            log(f"[{name}] 🔌 Переподключился к Telegram.", Fore.CYAN)
            return True
    except Exception as e:
        log(f"[{name}] ❌ Ошибка переподключения: {e}", Fore.RED)
    return False


def human_sleep():
    return random.uniform(MIN_ACTION_DELAY, MAX_ACTION_DELAY)


def button_text_matches(text):
    if not text:
        return False
    t = text.lower()
    patterns = ["подпис", "subscribe", "join", "канал", "channel"]
    for p in patterns:
        if p in t:
            return True
    if re.search(r"\+\d+", t):
        return True
    return False


def get_check_button_from_markup(markup):
    if not markup or not isinstance(markup, ReplyInlineMarkup):
        return None
    for row in markup.rows:
        for btn in row.buttons:
            if isinstance(btn, KeyboardButtonCallback):
                t = (btn.text or "").lower()
                if "провер" in t or "check" in t:
                    return btn
    return None


async def press_callback(client, bot_entity, message_id, data):
    try:
        await client(GetBotCallbackAnswerRequest(bot_entity, message_id, data=data))
        await asyncio.sleep(1.2)
        return True
    except Exception as e:
        log(f"[!] Ошибка при нажатии callback: {e}", Fore.RED)
        return False


async def find_subscribe_button(client, bot_entity, scan_messages=SCAN_MESSAGES):
    msgs = await client.get_messages(bot_entity, limit=scan_messages)
    for msg in msgs:
        markup = getattr(msg, "reply_markup", None)
        if not isinstance(markup, ReplyInlineMarkup):
            continue
        for row in markup.rows:
            for btn in row.buttons:
                if isinstance(btn, KeyboardButtonUrl) and btn.url and "t.me" in (btn.url or ""):
                    return True, msg, btn
                if isinstance(btn, KeyboardButtonCallback) and button_text_matches(btn.text):
                    return True, msg, btn
    return False, None, None

def format_report(stats, start_time):
    elapsed = datetime.now(timezone.utc) - start_time
    hh, rem = divmod(int(elapsed.total_seconds()), 3600)
    mm, ss = divmod(rem, 60)
    return (
        f"AutoFarm Report\n"
        f"Start UTC: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Uptime: {hh:02d}:{mm:02d}:{ss:02d}\n"
        f"Tasks completed: {stats.get('tasks', 0)}\n"
        f"GRAM earned: {int(stats.get('grams', 0))}\n"
        f"Channels joined (this session): {len(stats.get('joined_set', set()))}\n"
    )


# === SMART JOIN HANDLER (финал) ===
async def join_and_archive(client, url, joined_set, stats=None, start_time=None):
    try:
        # приватные ссылки (invite)
        m_inv = re.search(r"(?:t\.me/\+|joinchat/)([\w\d_-]+)", url)
        if m_inv:
            h = m_inv.group(1)
            try:
                res = await client(ImportChatInviteRequest(h))
                if hasattr(res, "chats") and res.chats:
                    entity = res.chats[0]
                    uid = getattr(entity, "id", None) or getattr(entity, "channel_id", None)
                    if uid and uid not in joined_set:
                        joined_set.add(uid)
                    return "joined", entity
                else:
                    log("[ℹ️] Обнаружен канал с заявкой — обрабатываю без ожидания.", Fore.CYAN)
                    return "request_sent", None

            except errors.UserAlreadyParticipantError:
                return "already", None

            except errors.FloodWaitError as e:
                wait_time = int(getattr(e, "seconds", 0) or 0)
                if stats is not None and start_time is not None and REPORT_IN_SAVED:
                    report = format_report(stats, start_time)
                    report += f"\nFloodWait seconds: {wait_time}\nTime (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    try:
                        await client.send_message("me", report)
                    except Exception:
                        pass
                return "flood", wait_time

            except Exception as e:
                err_text = str(e)
                # Главная доработка — Telegram сообщает, что заявка подана
                if (
                    "INVITE_REQUEST_SENT" in err_text
                    or "request_sent" in err_text.lower()
                    or "You have successfully requested to join this chat or channel" in err_text
                ):
                    log("[ℹ️📨] Обнаружен канал с заявкой — заявка успешно отправлена.", Fore.CYAN)
                    return "request_sent", None
                log(f"[⚠️] Ошибка при вступлении: {e}", Fore.YELLOW)
                return "failed", None

        # публичные каналы
        else:
            m = re.search(r"(?:t\.me/|telegram\.me/)([\w\d_]+)", url)
            if not m:
                return "failed", None
            username = m.group(1)
            entity = await client.get_entity(username)
            try:
                await client(JoinChannelRequest(entity))
                uid = getattr(entity, "id", None) or getattr(entity, "channel_id", None)
                if uid and uid not in joined_set:
                    joined_set.add(uid)
                return "joined", entity
            except errors.UserAlreadyParticipantError:
                return "already", None

    except Exception as e:
        log(f"[⚠️] join_and_archive ошибка: {e}", Fore.YELLOW)
        return "failed", None


async def attempt_press_check(client, bot_entity, original_msg=None, search_limit=8):
    if original_msg:
        mk = getattr(original_msg, "reply_markup", None)
        cb = get_check_button_from_markup(mk)
        if cb:
            return await press_callback(client, bot_entity, original_msg.id, cb.data)
    recent = await client.get_messages(bot_entity, limit=search_limit)
    for r in recent:
        mk = getattr(r, "reply_markup", None)
        cb = get_check_button_from_markup(mk)
        if cb:
            return await press_callback(client, bot_entity, r.id, cb.data)
    return False


def ensure_sessions_dir():
    if not os.path.isdir(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR, exist_ok=True)


def sessions_log_read():
    entries = {}
    if not os.path.exists(SESSIONS_LOG):
        return entries
    with open(SESSIONS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) >= 3:
                try:
                    entries[parts[0]] = (int(parts[1]), parts[2])
                except Exception:
                    pass
    return entries


def sessions_log_append(name, api_id, api_hash):
    entries = sessions_log_read()
    if name not in entries:
        with open(SESSIONS_LOG, "a", encoding="utf-8") as f:
            f.write(f"{name};{api_id};{api_hash}\n")


# === SESSION WORKER ===
async def session_worker(s: dict):
    client = s["client"]
    name = s["name"]
    stats = s["stats"]
    start_time = datetime.now(timezone.utc)
    consecutive_success = 0
    no_task_counter = 0
    last_no_tasks_msg_id = None
    log(f"[{name}] Воркер запущен.", Fore.CYAN)
    update_status(name, "WORKING 🟢")

    while True:
        try:
            if not await ensure_connected(client, name):
                update_status(name, "DISCONNECTED 🔴")
                await asyncio.sleep(10)
                continue

           # Получаем bot_entity СНАЧАЛА
            bot = await client.get_entity(BOT_USERNAME)
            
            await client.send_read_acknowledge(bot) # Помечаем как прочитанное
            await asyncio.sleep(random.uniform(2, 4)) # Типа "читаем" пару секунд
            # === CAPTCHA SLEEP ===
            if await detect_captcha(client, bot):

                log(f"[{name}] 🛑 Обнаружена капча. Ожидаю прохождения...", Fore.RED)
                update_status(name, "CAPTCHA 🔴")

                while True:
                    await asyncio.sleep(300)

                    if not await detect_captcha(client, bot):
                        break

                log(f"[{name}] ✅ Капча пройдена. Продолжаю работу.", Fore.GREEN)
                update_status(name, "WORKING 🟢")

                continue
                
            await client.send_message(bot, "👨‍💻 Заработать")
            await asyncio.sleep(human_sleep())
            found, msg_with_btn, btn = await find_subscribe_button(client, bot)

            # ===== НЕТ ЗАДАНИЙ =====
            if not found:
                # бот показал экран без заданий
                if await detect_no_tasks(client, bot):

                    log(f"[{name}] ❌ Нет заданий. Сон 15 минут.", Fore.MAGENTA)
                    update_status(name, "NO TASKS 🟣")

                    await asyncio.sleep(900)
                    continue

            # иначе просто ждём новую кнопку
                log(f"[{name}] Кнопка не найдена. Ждём...", Fore.YELLOW)
                await asyncio.sleep(human_sleep())
                continue
                
            #=========== URL ============
            url = None
            if isinstance(btn, KeyboardButtonCallback):
                await press_callback(client, bot, msg_with_btn.id, btn.data)
                await asyncio.sleep(human_sleep())
                recent = await client.get_messages(bot, limit=6)
                for r in recent:
                    mk = getattr(r, "reply_markup", None)
                    if isinstance(mk, ReplyInlineMarkup):
                        for row in mk.rows:
                            for b in row.buttons:
                                if isinstance(b, KeyboardButtonUrl) and "t.me" in b.url:
                                    url = b.url
                                    break
                            if url:
                                break
                    if url:
                        break
            elif isinstance(btn, KeyboardButtonUrl):
                url = btn.url

            if url:
                status, info = await join_and_archive(client, url, stats["joined_set"], stats, start_time)

                if status in ("joined", "already", "request_sent"):
                    if status == "joined":
                        track_joined_channel(name, info)

                    no_task_counter = 0
                    pressed_check = await attempt_press_check(client, bot, original_msg=msg_with_btn)
                    if pressed_check:
                        stats["tasks"] += 1
                        consecutive_success += 1
                        label = {
                            "joined": "✅ Подписка успешна и проверена",
                            "already": "🔁 Уже подписан, проверено",
                            "request_sent": "📨 Отправлена заявка — 'Проверить' нажат"
                        }[status]
                        log(f"[{name}] {label}.", Fore.GREEN if status != "request_sent" else Fore.CYAN)
                    else:
                        log(f"[{name}] 'Проверить' не найден ({status}).", Fore.YELLOW)
                    await asyncio.sleep(human_sleep())

                elif status == "flood":
                    update_status(name, "FLOOD 🟡")
                    wait_time = int(info or 0)
                    log(f"[{name}] ⚠️ Реальный FloodWait: {wait_time} сек. Пауза...", Fore.RED)
                    await asyncio.sleep(wait_time + 3)
                    consecutive_success = 0
                else:
                    log(f"[{name}] Не удалось подписаться ({status}).", Fore.YELLOW)
                    await asyncio.sleep(human_sleep())
            else:
                log(f"[{name}] Ссылка не найдена.", Fore.YELLOW)
                await asyncio.sleep(human_sleep())

            if consecutive_success >= random.randint(BATCH_MIN, BATCH_MAX):
                rest = random.uniform(MIN_REST_AFTER_BATCH, MAX_REST_AFTER_BATCH)
                log(f"[{name}] Отдых {int(rest)} сек после {consecutive_success} задач.", Fore.MAGENTA)
                await asyncio.sleep(rest)
                consecutive_success = 0

        except errors.FloodWaitError as e:
            wait_time = int(e.seconds)
            log(f"[{name}] FloodWaitError: {wait_time} сек.", Fore.RED)
            await asyncio.sleep(wait_time + 3)
        except Exception as e:
            err_text = str(e)
            if "Cannot send requests while disconnected" in err_text:
                update_status(name, "DISCONNECTED 🔴")
                log(f"[{name}] ⚠️ Клиент отключен. Пробую переподключение...", Fore.YELLOW)
                if await ensure_connected(client, name):
                    update_status(name, "WORKING 🟢")
                    await asyncio.sleep(2)
                    continue
                await asyncio.sleep(10)
            else:
                log(f"[{name}] Ошибка: {e}", Fore.YELLOW)
                await asyncio.sleep(3)
            
# === CAPTCHA DETECT ======
async def detect_captcha(client, bot_entity, limit=6):
    msgs = await client.get_messages(bot_entity, limit=limit)

    for msg in msgs:
        if not msg.text:
            continue

        text = msg.text.lower()

        captcha_keywords = [
            "на какой фотографии",
            "изображён",
            "изображена",
            "выберите изображение",
            "капча"
        ]

        if any(k in text for k in captcha_keywords):
            return True

    return False
    
# === MAIN ===
async def main():
    sessions = []

    print(Fore.CYAN + "PR GRAM AutoFarm v2.0 – Full Edition (by lNexio)\n" + Fore.RESET)
    ensure_sessions_dir()

    stored = sessions_log_read()

    # === AUTLOAD SESSIONS ===
    if stored:
        for name, (api_id, api_hash) in stored.items():

            if len(sessions) >= MAX_SESSIONS:
                break

            session_basename = f"{name}_session"
            session_path = session_basename

            if not os.path.exists(f"{session_basename}.session") and \
               os.path.exists(os.path.join(SESSIONS_DIR, f"{session_basename}.session")):
                session_path = os.path.join(SESSIONS_DIR, session_basename)

            try:
                client = TelegramClient(
                    session_path,
                    api_id,
                    api_hash,
                    device_model="Telegram Web",
                    system_version="Windows 11",
                    app_version="WebK 2.1.0",
                    lang_code="ru",
                    system_lang_code="ru-RU"
                )

                await client.connect()

                if await client.is_user_authorized():
                    log(f"[✅] Автозагружена сессия: {name}", Fore.GREEN)

                    sessions.append({
                        "name": name,
                        "client": client,
                        "stats": {
                            "tasks": 0,
                            "grams": 0,
                            "joined_set": set()
                        }
                    })
                else:
                    log(f"[!] Сессия {name} не авторизована.", Fore.YELLOW)
                    await client.disconnect()

            except Exception as e:
                log(f"[❌] Ошибка автозагрузки {name}: {e}", Fore.RED)

    if not sessions:
        log("Нет подключённых сессий.", Fore.RED)
        return []

    log(f"Всего загружено сессий: {len(sessions)}", Fore.CYAN)
    log("[🚀] Запускаю воркеры...\n", Fore.CYAN)

    # ✅ ВАЖНО: запускаем воркеры В ФОНЕ
    for s in sessions:
        asyncio.create_task(session_worker(s))

    # ✅ ВАЖНО: сразу отдаём список аккаунтов
    return sessions


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("\n[✖] Остановлено пользователем.", Fore.RED)
        sys.exit(0)

