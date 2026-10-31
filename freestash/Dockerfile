# One service: FastAPI serves the API and the built React UI (same origin, so the UI needs no build-time URLs).
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Pin the OS codename: a floating slim tag once rolled to a new Debian and broke builds (railway-deploy-playbook).
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FREESTASH_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir ".[api,mcp]"
COPY --from=web /web/dist ./web/dist
ENV FREESTASH_WEB_DIST=/app/web/dist
EXPOSE 8787
# Railway injects PORT; bind it on 0.0.0.0. Client IPs come from the edge's headers (see api/auth.py:_ip).
CMD ["sh", "-c", "python -m uvicorn freestash.api.app:app --host 0.0.0.0 --port ${PORT:-8787}"]
