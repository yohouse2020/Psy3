import os
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ... весь ваш существующий код обработчиков ...

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))

    # Webhook конфигурация
    webhook_url = os.environ.get('RENDER_EXTERNAL_URL')
    if not webhook_url:
        logger.error("RENDER_EXTERNAL_URL not set")
        return
        
    port = int(os.environ.get('PORT', 8443))
    
    # Устанавливаем webhook
    async def post_init(application):
        await application.bot.set_webhook(
            url=f"{webhook_url}/{TELEGRAM_TOKEN}",
            allowed_updates=["message"]
        )
        logger.info(f"Webhook set to: {webhook_url}/{TELEGRAM_TOKEN}")

    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{webhook_url}/{TELEGRAM_TOKEN}",
        post_init=post_init
    )

if __name__ == '__main__':
    main()
