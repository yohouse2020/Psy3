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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable not set.")
    exit(1)

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not set.")
    exit(1)

# Инициализация клиента OpenAI
CLIENT = OpenAI(api_key=OPENAI_API_KEY)
LLM_MODEL = "gpt-3.5-turbo"

# --- LLM Integration Functions ---

def get_llm_response(prompt: str) -> str:
    """Получает ответ от LLM."""
    try:
        system_prompt = """
Ты - профессиональный психолог с 15-летним опытом работы. Твоя задача - оказывать психологическую поддержку.

Твой стиль общения:
- Поддерживающий и эмпатичный
- Профессиональный и этичный
- Конкретный и практичный
- Основанный на принципах доказательной психологии

Важные правила:
1. Не ставь медицинские диагнозы
2. Не заменяй очную консультацию
3. В кризисных ситуациях направляй к специалистам
4. Сосредоточься на активном слушании и поддержке
"""
        
        response = CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error getting LLM response: {e}")
        return "Благодарю вас за обращение. В настоящий момент я испытываю технические трудности. Пожалуйста, попробуйте написать ваш вопрос еще раз."

# --- Speech Integration Functions (STT/TTS) ---

async def transcribe_voice_message(voice_file: File) -> str:
    """Скачивает голосовое сообщение, конвертирует и распознает его с помощью Whisper."""
    ogg_path = None
    mp3_path = None
    
    try:
        # 1. Скачивание файла во временную папку
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
            ogg_path = ogg_file.name
        
        await voice_file.download_to_drive(ogg_path)
        logger.info(f"Downloaded voice file to {ogg_path}")

        # 2. Конвертация OGG в MP3 для Whisper
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
            mp3_path = mp3_file.name
        
        logger.info(f"Converting audio from {ogg_path} to {mp3_path}")
        
        result = subprocess.run([
            "ffmpeg", "-i", ogg_path, 
            "-acodec", "libmp3lame", 
            "-ab", "128k",
            "-ac", "1",
            mp3_path, "-y"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return ""

        # 3. Распознавание речи с помощью Whisper
        with open(mp3_path, "rb") as audio_file:
            transcript = CLIENT.audio.transcriptions.create(
                model="whisper-1",
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
        # Гарантированная очистка временных файлов
        for path in [ogg_path, mp3_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    logger.error(f"Error deleting temp file {path}: {e}")

async def synthesize_speech(text: str) -> bytes:
    """Синтезирует речь (TTS) из текста с помощью OpenAI TTS."""
    try:
        # Ограничиваем длину текста для TTS
        if len(text) > 1000:
            text = text[:1000] + "..."
            
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    welcome_text = """
👋 Добро пожаловать в кабинет психологической помощи!

Я - ваш виртуальный психолог. Вы можете:
• Писать текстовые сообщения
• Отправлять голосовые сообщения 🎤
• Получать профессиональную поддержку

Расскажите, что вас беспокоит...
    """
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help."""
    help_text = """
💫 Как пользоваться ботом:

📝 *Текстовые сообщения* - просто напишите ваш вопрос
🎤 *Голосовые сообщения* - отправьте голосовое сообщение
⚡ *Быстрые ответы* - я постараюсь ответить быстро и по делу

Кризисная помощь: если вы переживаете острый кризис, пожалуйста, обратитесь к специалистам:
• Телефон доверия: 8-800-2000-122
• Экстренная помощь: 112
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения."""
    user_text = update.message.text
    logger.info(f"Received text from user {update.message.from_user.id}: {user_text}")
    
    # Проверяем кризисные ситуации
    crisis_keywords = ['суицид', 'самоубийство', 'умру', 'покончить', 'кризис', 'хочу умереть']
    if any(keyword in user_text.lower() for keyword in crisis_keywords):
        crisis_response = """
🚨 Я понимаю, что вы переживаете тяжелые чувства.

Пожалуйста, обратитесь за немедленной помощью:
• Телефон доверия: 8-800-2000-122 (круглосуточно)
• Экстренная психологическая помощь: 112
• Не оставайтесь один на один с проблемой
"""
        await update.message.reply_text(crisis_response)
        return
    
    # Отправляем "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Получаем ответ от LLM
    llm_response = get_llm_response(user_text)
    
    # Отправляем ответ
    await update.message.reply_text(llm_response)

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await update.message.reply_text("❌ Не удалось распознать голосовое сообщение. Пожалуйста, попробуйте еще раз или напишите текстом.")
        return

    logger.info(f"Transcribed text: {transcribed_text}")
    
    # 2. Получаем ответ от LLM
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    llm_response = get_llm_response(transcribed_text)
    
    # 3. Синтезируем речь
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_audio")
    audio_content = await synthesize_speech(llm_response)

    if not audio_content:
        # Если TTS не работает, отправляем текстовый ответ
        await update.message.reply_text(
            f"🎤 *Вы сказали:* {transcribed_text}\n\n"
            f"💬 *Мой ответ:* {llm_response}",
            parse_mode="Markdown"
        )
        return

    # 4. Отправляем голосовое сообщение
    await update.message.reply_voice(
        voice=io.BytesIO(audio_content),
        caption=f"💬 Ответ на ваше сообщение",
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
    application.run_polling()

if __name__ == '__main__':
    main()
