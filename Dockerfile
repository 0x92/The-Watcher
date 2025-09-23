FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System-Dependencies (inkl. Node & Buildtools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        nodejs \
        npm && \
    rm -rf /var/lib/apt/lists/*

# Python-Dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# JS-Dependencies
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# App-Code
COPY . .

# Frontend bauen (falls vorhanden)
RUN npm run build

EXPOSE 5000
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:5000", "--workers", "3", "--threads", "2", "--timeout", "60"]
