FROM python:3.11-slim-bookworm

WORKDIR /app

COPY wheels/ /wheels/

COPY requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY . .

RUN chmod +x /app && mkdir -p /app/backups

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
