FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic alembic
COPY app app
# run as a normal user; the Whisper model is downloaded into ~/.cache on first use
RUN useradd --create-home app && mkdir -p /home/app/.cache && chown -R app /srv /home/app
USER app
EXPOSE 8000
# migrations first, then the server. Hosts such as Render set $PORT; locally it defaults to 8000.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
