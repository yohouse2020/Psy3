import os
import logging
import subprocess
import tempfile
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import File
from openai import OpenAI

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLIENT = OpenAI(base_url=os.environ.get("OPENAI_API_BASE"))
LLM_MODEL = "gemini-2.5-flash"

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable not set.")

# --- LLM Integration Functions ---

def get_llm_response(prompt: str) -> str:
    """Получает ответ от LLM."""
    try:
        response = CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "Ты - дружелюбный и полезный ассистент, созданный на основе технологии Manus. Ты можешь свободно общаться с пользователем на русском языке."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error getting LLM response: {e}")
        return "Извините, произошла ошибка при обращении к модели."

# --- Speech Integration Functions (STT/TTS) ---

async def transcribe_voice_message(voice_file: File) -> str:
    """Скачивает голосовое сообщение, конвертирует и распознает его с помощью Manus STT."""
    try:
        # 1. Скачивание файла во временную папку
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
            ogg_path = ogg_file.name
        
        await voice_file.download_to_drive(ogg_path)
        logger.info(f"Downloaded voice file to {ogg_path}")

        # 2. Конвертация OGG (Telegram) в MP3 (для Manus STT) с помощью ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
            mp3_path = mp3_file.name
        
        logger.info(f"Converting audio from {ogg_path} to {mp3_path}")
        
        result = subprocess.run(
            ["ffmpeg", "-i", ogg_path, "-acodec", "libmp3lame", "-ab", "192k", mp3_path, "-y"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            os.unlink(ogg_path)
            return ""
        
        os.unlink(ogg_path)

        # 3. Распознавание речи (STT) с помощью Manus API
        with open(mp3_path, "rb") as mp3_file:
            transcript = CLIENT.audio.transcriptions.create(
                model="whisper-1",
                file=mp3_file,
                language="ru"
            )
        
        os.unlink(mp3_path)
        return transcript.text
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return ""

async def synthesize_speech(text: str) -> bytes:
    """Синтезирует речь (TTS) из текста с помощью Manus TTS."""
    try:
        response = CLIENT.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        return response.content
    except Exception as e:
        logger.error(f"Error during speech synthesis: {e}")
        return b""

# --- Telegram Handlers ---

async def start_command(update: Update, context) -> None:
    """Обрабатывает команду /start."""
    await update.message.reply_text('Привет! Я голосовой ассистент на базе Manus. Отправь мне текст или голосовое сообщение, и я отвечу.')

async def help_command(update: Update, context) -> None:
    """Обрабатывает команду /help."""
    await update.message.reply_text('Просто отправь мне сообщение. Я умею отвечать текстом и голосом.')

async def text_message_handler(update: Update, context) -> None:
    """Обрабатывает текстовые сообщения."""
    user_text = update.message.text
    logger.info(f"Received text from user {update.message.from_user.id}: {user_text}")
    
    # Отправляем "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Получаем ответ от LLM
    llm_response = get_llm_response(user_text)
    
    # Отправляем ответ
    await update.message.reply_text(llm_response)

async def voice_message_handler(update: Update, context) -> None:
    """Обрабатывает голосовые сообщения."""
    voice = update.message.voice
    if not voice:
        return

    logger.info(f"Received voice message from user {update.message.from_user.id}")

    # 1. Скачиваем и распознаем речь
    voice_file = await context.bot.get_file(voice.file_id)
    
    # Отправляем "запись..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_audio")
    
    transcribed_text = await transcribe_voice_message(voice_file)
    
    if not transcribed_text:
        await update.message.reply_text("Не удалось распознать голосовое сообщение. Попробуйте еще раз.")
        return

    logger.info(f"Transcribed text: {transcribed_text}")
    
    # 2. Получаем ответ от LLM
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    llm_response = get_llm_response(transcribed_text)
    
    # 3. Синтезируем речь
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_audio")
    audio_content = await synthesize_speech(llm_response)

    if not audio_content:
        await update.message.reply_text(f"Ответ: {llm_response}\n\nНе удалось синтезировать речь.")
        return

    # 4. Отправляем голосовое сообщение
    await update.message.reply_voice(
        voice=io.BytesIO(audio_content),
        caption=f"Ответ на: *{transcribed_text[:30]}...*",
        parse_mode="Markdown"
    )

# --- Main Application Setup ---

def main() -> None:
    """Запускает бота."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set.")
        return

    # Создаем Application и передаем ему токен бота.
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    # Регистрируем обработчик голосовых сообщений
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))

    # Запускаем бота
    logger.info("Starting bot...")
    application.run_polling(poll_interval=1.0)

if __name__ == '__main__':
    main()
