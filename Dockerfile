FROM python:3.11 as build

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip 
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["/bin/sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WORKERS:-3} --worker-class gthread --threads ${THREADS:-2} --timeout ${TIMEOUT:-120} --keep-alive ${KEEP_ALIVE:-65} --max-requests ${MAX_REQUESTS:-1000} --max-requests-jitter ${MAX_REQUESTS_JITTER:-50} --access-logfile ${ACCESS_LOGFILE:--} --error-logfile ${ERROR_LOGFILE:--} --log-level ${LOG_LEVEL:-info}"]

