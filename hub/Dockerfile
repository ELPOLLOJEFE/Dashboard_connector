FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

# La base de datos vive en /data (volumen persistente).
ENV DC_DB_PATH=/data/hub.db
EXPOSE 8700

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8700/healthz').read()"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8700", "--proxy-headers"]
