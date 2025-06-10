# Використовуємо Python 3.11 як базовий образ
FROM python:3.11-slim

# Встановлюємо необхідні пакети
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо файли проекту
COPY . /app

# Оновлюємо pip
RUN pip install --upgrade pip

# Встановлюємо залежності
RUN pip install -r requirements.txt

# Запускаємо бота
CMD ["python", "main.py"]
