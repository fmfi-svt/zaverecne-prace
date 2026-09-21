FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxmlsec1-openssl git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV FLASK_APP=app.py \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:8000", "--timeout", "120", "app:app"]
