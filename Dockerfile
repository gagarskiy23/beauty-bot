FROM python:3.11-slim

WORKDIR /app

# Обновляем pip и ставим aiogram
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir aiogram

# Код бота
COPY main.py db.py config.py ./

# Токен через переменную окружения
CMD ["python", "main.py"]
