# ==============================================================================
# Dockerfile — OpsSense AI (Single-Container Full-Stack Build for Google Cloud Run)
# Stage 1: Node 20 builds React/Vite/Tailwind UI into /frontend/dist
# Stage 2: Python 3.11-slim serves FastAPI + /frontend/dist on port 8080
# ==============================================================================

FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy Authentic Google Agent Skills (.agents/skills/), Backend, Edge Client & Built Frontend
COPY .agents/ /app/.agents/
COPY backend/ /app/backend/
COPY edge_client/ /app/edge_client/
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
