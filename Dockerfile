FROM python:3.11-slim-bookworm

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies (from wheels if available, otherwise from PyPI)
RUN if [ -d /wheels ]; then \
      pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

# Copy application source
COPY app/ ./app/
COPY tests/ ./tests/

# Create backups directory for local fallback writes
RUN mkdir -p /app/backups

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
