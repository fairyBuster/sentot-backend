import multiprocessing
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def env_int(name, default):
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


cpu_cores = multiprocessing.cpu_count()
# Optimasi untuk 4 core CPU & 8GB RAM
# Rumus umum workers: (2 x num_cores) + 1
# Dengan 4 core, kita bisa set ke 9 workers.
# Karena RAM 8GB sangat lega untuk 9 worker, dan user banyak (1000 aktif),
# kita bisa naikkan threads agar handle "Waiting for Server" lebih baik saat I/O bound.

default_workers = 9   # Tetap 9 workers (standar CPU 4 core)
default_threads = 15  # Naikkan dari 4 ke 15 threads per worker (Total concurrency: 9x15 = 135)
worker_class = "gthread"  # Gthread sangat efisien untuk I/O blocking

# Jika environment variable tidak di-set, gunakan nilai optimal ini
workers = env_int("GUNICORN_WORKERS", default_workers)
threads = env_int("GUNICORN_THREADS", default_threads)
worker_class = os.getenv("GUNICORN_WORKER_CLASS", worker_class)
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
timeout = env_int("GUNICORN_TIMEOUT", 120)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 120)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 200)
accesslog = os.getenv("GUNICORN_ACCESSLOG", str(LOG_DIR / "gunicorn.access"))
errorlog = os.getenv("GUNICORN_ERRORLOG", str(LOG_DIR / "gunicorn.err"))
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
pidfile_env = os.getenv("GUNICORN_PIDFILE")
pidfile = pidfile_env if pidfile_env else None
preload_app = os.getenv("GUNICORN_PRELOAD", "true").lower() in ("1", "true", "yes", "on")
reload = os.getenv("GUNICORN_RELOAD", "false").lower() in ("1", "true", "yes", "on")
