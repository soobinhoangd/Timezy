FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIMEZY_DB=/var/data/timezy.sqlite3 \
    PORT=10000

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend
COPY database/__init__.py database/connection.py database/schema.sql /app/database/
RUN mkdir -p /var/data

EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','10000')+'/health',timeout=3)"

CMD ["python","-m","backend.deploy"]
