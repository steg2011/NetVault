FROM python:3.11-slim-bookworm

WORKDIR /app

# Copy pre-downloaded wheels for offline install
COPY wheels/ /wheels/

# Install dependencies from local wheels only (no internet required)
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY tests/ ./tests/

# Create backups directory for local fallback writes
RUN mkdir -p /app/backups

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
