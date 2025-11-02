import os
import logging
import subprocess
import tempfile
import io
import asyncio
from telegram import Update, File
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки окружения ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable not set.")
    exit(1)

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not set.")
    exit(1)

# --- Инициализация клиента OpenAI ---
CLIENT = OpenAI(api_key=OPENAI_API_KEY)

# --- Настройки моделей ---
LLM_MODEL = "gpt-5-nano"       # Новая основная текстовая модель
AUDIO_MODEL = "gpt-audio-mini" # Универсальная аудиомодель (STT + TTS)


# --- LLM Integration Functions ---
def get_llm_response(prompt: str) -> str:
    """Получает ответ от модели GPT-5 nano."""
    try:
        system_prompt = """
Ты - профессиональный психолог с 20-летним опытом работы. 
Твоя задача - оказывать качественную психологическую поддержку.

Твой стиль общения:
🎯 Поддерживающий и эмпатичный
🎯 Профессиональный и этичный
🎯 Конкретный и практичный
🎯 Основанный на научных данных

Ключевые принципы:
1. Активное слушание и валидация чувств
2. Безоценочное принятие
3. Конфиденциальность и уважение
4. Ориентация на решение

Важные правила:
❌ Не ставь медицинские диагнозы
❌ Не заменяй очную консультацию
🚨 В кризисных ситуациях направляй к специалистам
💡 Сосредоточься на ресурсах и сильных сторонах клиента

Отвечай на русском языке естественно и тепло.
"""
        response = CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.8,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error getting LLM response from {LLM_MODEL}: {e}")
        return "Благодарю вас за обращение. Сейчас возникла техническая ошибка. Пожалуйста, попробуйте позже."


# --- Speech Integration Functions (STT/TTS) ---
async def transcribe_voice_message(voice_file: File) -> str:
    """Распознаёт речь с помощью gpt-audio-mini."""
    ogg_path = mp3_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
            ogg_path = ogg_file.name
        await voice_file.download_to_drive(ogg_path)
        logger.info(f"Downloaded voice file to {ogg_path}")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
            mp3_path = mp3_file.name

        logger.info(f"Converting audio from {ogg_path} to {mp3_path}")
        subprocess.run([
            "ffmpeg", "-i", ogg_path, "-acodec", "libmp3lame",
            "-ac", "1", mp3_path, "-y"
        ], check=True)

        with open(mp3_path, "rb") as audio_file:
            transcript = CLIENT.audio.transcriptions.create(
                model=AUDIO_MODEL,
                file=audio_file,
                language="ru",
                response_format="text"
            )

        logger.info(f"Transcription successful: {transcript[:100]}...")
        return transcript

    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return ""
    finally:
        for path in [ogg_path, mp3_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    logger.error(f"Error deleting temp file {path}: {e}")


async def synthesize_speech(text: str) -> bytes:
    """Синтезирует речь (TTS) с помощью gpt-audio-mini."""
    try:
        if len(text) > 1000:
            text = text[:1000] + "..."

        response = CLIENT.audio.speech.create(
            model=AUDIO_MODEL,
            voice="alloy",
            input=text,
            speed=1.0
        )
        return response.content
    except Exception as e:
        logger.error(f"Error during speech synthesis: {e}")
        return b""


# --- Telegram Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    welcome_text = """
🧠 *Добро пожаловать в кабинет современной психологической помощи!*

Я - ваш виртуальный психолог, работающий на основе современных технологий OpenAI.

*Что я могу:*
💬 **Текстовые консультации**
🎤 **Голосовая поддержка**
⚡ **Мгновенные ответы**
🔒 **Полная конфиденциальность**

Расскажите, что вас беспокоит, и я постараюсь помочь.
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help."""
    help_text = """
🌟 *Как получить максимальную пользу от консультации:*

📝 Опишите вашу ситуацию подробно.  
🎤 Говорите естественно, как с живым психологом.  
💫 Чем конкретнее вопрос, тем точнее ответ.

🚨 В кризисной ситуации:
• Телефон доверия: `8-800-2000-122`
• Экстренная помощь: `112`

Вы не одиноки — помощь доступна.
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def model_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о используемых моделях."""
    info_text = f"""
🤖 *Информация о системе:*

*Текстовая модель:* `{LLM_MODEL}`
*Аудио-модель:* `{AUDIO_MODEL}`
*Назначение:* Психологический ассистент с поддержкой голоса
"""
    await update.message.reply_text(info_text, parse_mode="Markdown")


def check_crisis_situation(text: str) -> bool:
    """Проверяет наличие кризисных слов."""
    crisis_keywords = [
        'суицид', 'самоубийство', 'умру', 'покончить',
        'кризис', 'хочу умереть', 'наложу на себя руки',
        'самоповреждение', 'режу себя', 'больше не могу',
        'кончу жизнь', 'сведу счеты', 'лучше умереть'
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in crisis_keywords)


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения."""
    user_text = update.message.text
    logger.info(f"Received text from user {update.message.from_user.id}: {user_text}")

    if check_crisis_situation(user_text):
        crisis_response = """
🚨 *ЭКСТРЕННАЯ ПОМОЩЬ*

Похоже, вы переживаете очень тяжёлые чувства.  
Ваша жизнь бесценна, и помощь доступна прямо сейчас.

📞 **Телефон доверия:** `8-800-2000-122`
🚑 **Экстренная помощь:** `112`
"""
        await update.message.reply_text(crisis_response, parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        llm_response = get_llm_response(user_text)
        await update.message.reply_text(llm_response)
    except Exception as e:
        logger.error(f"Error in text handler: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке вашего сообщения. Попробуйте позже.")


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает голосовые сообщения."""
    voice = update.message.voice
    if not voice:
        return

    logger.info(f"Received voice message from user {update.message.from_user.id}")
    voice_file = await context.bot.get_file(voice.file_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_audio")

    transcribed_text = await transcribe_voice_message(voice_file)
    if not transcribed_text:
        await update.message.reply_text("❌ Не удалось распознать голосовое сообщение.")
        return

    logger.info(f"Transcribed text: {transcribed_text}")

    if check_crisis_situation(transcribed_text):
        await update.message.reply_text(
            "🚨 Пожалуйста, немедленно обратитесь за помощью: 📞 8-800-2000-122",
            parse_mode="Markdown"
        )
        return

    llm_response = get_llm_response(transcribed_text)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_audio")
    audio_content = await synthesize_speech(llm_response)

    if not audio_content:
        await update.message.reply_text(
            f"🎤 *Вы сказали:* {transcribed_text}\n\n💬 *Ответ:* {llm_response}",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_voice(
        voice=io.BytesIO(audio_content),
        caption=f"💬 Ответ от модели {LLM_MODEL}",
        parse_mode="Markdown"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки."""
    logger.error(f"Exception: {context.error}")


# --- Webhook Setup ---
async def set_webhook(application: Application):
    """Устанавливает webhook после запуска."""
    webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
    if webhook_url:
        webhook_url = f"{webhook_url}/{TELEGRAM_TOKEN}"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        logger.info(f"Webhook set to: {webhook_url}")
        logger.info(f"Using models: {LLM_MODEL} / {AUDIO_MODEL}")
    else:
        logger.warning("RENDER_EXTERNAL_URL not set, webhook not configured")


# --- Main Application Setup ---
def main() -> None:
    """Запускает Telegram-бота."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("model", model_info_command))

    # Сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))

    # Ошибки
    application.add_error_handler(error_handler)

    webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
    port = int(os.environ.get('PORT', 8443))

    if webhook_url:
        logger.info(f"Starting bot with webhook on port {port}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{webhook_url}/{TELEGRAM_TOKEN}",
            post_init=set_webhook
        )
    else:
        logger.info("Starting bot in polling mode (development)")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message"]
        )


if __name__ == '__main__':
    main()
