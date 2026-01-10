# Gunicorn configuration for production
# Usage: gunicorn -c gunicorn.conf.py web_search.api.main:app

import multiprocessing
import os

# Bind to all interfaces on port 8080
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")

# Worker configuration
# Rule of thumb: (2 * CPU cores) + 1
default_workers = multiprocessing.cpu_count() * 2 + 1
workers = int(
    os.getenv("GUNICORN_WORKERS", os.getenv("WEB_CONCURRENCY", default_workers))
)

# Use Uvicorn workers for async support
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout for graceful worker shutdown (seconds)
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))

# Graceful timeout (seconds)
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Keep-alive timeout (seconds)
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# Max requests per worker before restart (memory leak prevention)
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 50))

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")  # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Access log format (JSON-friendly)
access_log_format = '{"time": "%(t)s", "status": %(s)s, "method": "%(m)s", "path": "%(U)s", "query": "%(q)s", "duration_ms": %(D)s, "size": %(B)s, "remote_addr": "%(h)s", "user_agent": "%(a)s"}'

# Preload app for faster worker startup (but uses more memory)
preload_app = True

# Process naming
proc_name = "web_search"
