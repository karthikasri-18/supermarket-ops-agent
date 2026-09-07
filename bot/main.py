"""
bot/main.py

The Telegram long-polling loop. On every incoming text message:
  1. Check processed_updates -- skip if Telegram already redelivered
     this exact update_id (idempotency).
  2. Load preferences fresh from Postgres (not cached anywhere) --
     this is what makes them survive a Telegram-side "new chat".
  3. Hand the message + preferences to the agent, stream back the reply.

Run with:  python -m bot.main
(NOT "python bot/main.py" -- that breaks the tools./db. imports,
see the README note on this.)
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
from google.genai.errors import ClientError

from bot.agent import new_chat_session, pop_last_generated_file, set_current_update_id, pop_last_mutation
from db.connection import get_connection

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# One live chat SESSION per Telegram chat, kept in memory for as long as
# this process runs. This is ONLY conversation history -- it holds no shop
# data and no preferences, so it's fine that it resets if the bot restarts.
# Preferences are reloaded from Postgres every message regardless of
# whether this cache is warm or cold.
_chat_sessions: dict = {}


def is_already_processed(update_id: int) -> bool:
    """
    Idempotency guard. Tries to INSERT this update_id; if it's already
    there, the INSERT is skipped (ON CONFLICT DO NOTHING) and RETURNING
    gives back no row -- that's how we detect "seen this before".
    """
    with get_connection() as cur:
        cur.execute(
            """
            INSERT INTO processed_updates (telegram_update_id)
            VALUES (%s)
            ON CONFLICT (telegram_update_id) DO NOTHING
            RETURNING telegram_update_id
            """,
            (update_id,),
        )
        return cur.fetchone() is None


def load_preferences() -> dict:
    with get_connection() as cur:
        cur.execute("SELECT key, value FROM preferences")
        return {row["key"]: row["value"] for row in cur.fetchall()}


def get_session_for_chat(chat_id: int):
    if chat_id not in _chat_sessions:
        _chat_sessions[chat_id] = new_chat_session()
    return _chat_sessions[chat_id]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_already_processed(update.update_id):
        return  # Telegram redelivered something we've already handled

    chat_id = update.effective_chat.id
    user_text = update.message.text

    prefs = load_preferences()
    prefs_line = "; ".join(f"{k}={v}" for k, v in prefs.items()) or "(none set)"
    message_with_context = f"[Shop preferences: {prefs_line}]\n\n{user_text}"

    # Feeds tools/khata.py's idempotency_key for this turn -- if a
    # mutating tool runs, this is the key it's stored under, so a
    # genuine Telegram-level redelivery of this same update_id can't
    # double-apply it.
    set_current_update_id(update.update_id)

    session = get_session_for_chat(chat_id)
    # session.send_message is a blocking call (network + our own blocking
    # DB calls inside tool execution) -- run it in a thread so it doesn't
    # freeze the bot's whole event loop while it's working.
    try:
        response = await asyncio.to_thread(session.send_message, message_with_context)
    except ClientError as e:
        # A mutating tool (khata charge/payment, finalize_bill) can commit
        # to Postgres and THEN the turn can still fail on the later
        # round-trip to Gemini for final reply text -- automatic function
        # calling executes tools before that final text comes back. If
        # that happened, say so plainly instead of a blind "try again",
        # which is what caused the double-payment: the owner retried an
        # action that had actually already gone through.
        mutation = pop_last_mutation()
        if mutation:
            await update.message.reply_text(
                f"{mutation}\n\n(Then hit a connection hiccup after that, so this may look "
                f"like an error, but the action above did go through -- no need to repeat it.)"
            )
            return
        if getattr(e, "code", None) == 429:
            await update.message.reply_text(
                "Hit the free API rate limit for a moment -- please wait a bit and try again."
            )
            return
        # Any other API error (503 etc.) with nothing committed -- safe to
        # tell the owner to just retry.
        await update.message.reply_text(
            "Hit a temporary connection issue -- please try that again."
        )
        return

    reply_text = (response.text or "").strip()
    if not reply_text:
        # response.text comes back empty when the model's turn ended with
        # an unresolved function_call instead of final text (e.g. hit the
        # automatic-function-calling cap). Silence here looks like a hang
        # from the owner's side -- say something instead of nothing.
        mutation = pop_last_mutation()
        reply_text = mutation or "Sorry, I got stuck partway through that -- could you try again or rephrase?"
    await update.message.reply_text(reply_text)

    # If a document tool ran this turn, send the actual file too.
    file_path = pop_last_generated_file()
    if file_path:
        with open(file_path, "rb") as f:
            await update.message.reply_document(document=f)


async def handle_network_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Registered error handler. Without this, PTB just logs a full traceback
    for every transient network hiccup during long-polling's get_updates
    (e.g. a brief WiFi drop) -- alarming, but PTB's own retry loop already
    recovers from these on its own. This handler exists so that:
      1. Real errors get one clean log line instead of a wall of traceback
      2. Errors we can't recover from tell the owner via Telegram, rather
         than silently vanishing
    """
    from telegram.error import NetworkError
    if isinstance(context.error, NetworkError):
        print(f"[transient network error, retrying automatically] {context.error}")
        return
    print(f"[unhandled error] {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Something went wrong on my end -- please try that again."
        )


async def handle_new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /new -- discards this chat's conversation history so we can prove
    preferences (stored in Postgres, loaded fresh every message) still
    apply even with zero conversation memory carried over.
    """
    chat_id = update.effective_chat.id
    _chat_sessions.pop(chat_id, None)
    await update.message.reply_text("Started a fresh chat. Shop data and preferences are unaffected.")


def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .pool_timeout(30)
        .get_updates_read_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("new", handle_new_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_network_error)
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()