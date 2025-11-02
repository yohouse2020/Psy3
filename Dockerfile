# Используем стабильную версию Python 3.12 (а не 3.13!)
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Обновляем pip и ставим зависимости
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]
