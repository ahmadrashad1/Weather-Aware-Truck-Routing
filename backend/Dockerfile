FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
RUN useradd --system --create-home app
USER app

ENV PATH="/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
# Threads and a long timeout because a request can wait out a provider's per-minute rate limit.
# One worker, because the in-process cache and its rate limit counts aren't shared between them.
# No access log, because Django logs each request without its search text.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-1} --worker-class gthread --threads ${GUNICORN_THREADS:-8} --timeout 150"]
