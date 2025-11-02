# --- Base image ---
FROM python:3.12-slim

# --- System dependencies ---
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# --- Workdir setup ---
WORKDIR /app

# --- Copy files ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --- Environment ---
ENV PYTHONUNBUFFERED=1

# --- Start bot ---
CMD ["python", "bot.py"]
