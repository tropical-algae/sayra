FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

LABEL org.opencontainers.image.authors="tropical-algae tropicalalgae@gmail.com"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-default-groups --no-editable

EXPOSE 8000

CMD ["/app/.venv/bin/python", "-m", "sayra.app.main"]
