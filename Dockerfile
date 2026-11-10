FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY vendor ./vendor
RUN pip install --upgrade pip && pip install ./vendor/*.whl

COPY pyproject.toml README.md .env.example ./
COPY src ./src
COPY fixtures ./fixtures
COPY tests ./tests

RUN pip install -e ".[dev]"

CMD ["python", "-m", "mediateca", "worker"]
