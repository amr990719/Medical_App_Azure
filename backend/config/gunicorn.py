"""Gunicorn settings for the production image (`gunicorn --config python:config.gunicorn`).

The app is NOT preloaded: each worker imports `config.wsgi` after the fork, so the
OpenTelemetry exporters (background threads) start in every worker. Gunicorn's access log is
off: its lines contain query strings (an admin search by national ID would be written in
clear); `config.middleware.RequestIdMiddleware` writes the masked, structured access log.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
worker_tmp_dir = "/dev/shm"  # noqa: S108 — tmpfs heartbeat files, never application data
preload_app = False
accesslog = None
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
# Gunicorn 26's runtime-management socket (`gunicornc`) is not used in containers; disabled
# rather than given a writable home directory.
control_socket_disable = True
