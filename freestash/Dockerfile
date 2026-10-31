# One service: FastAPI serves the API and the built React UI.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY web/ ./
ARG VITE_AUTH_MODE=none
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_PUBLISHABLE_KEY=
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE VITE_SUPABASE_URL=$VITE_SUPABASE_URL VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FREESTASH_DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir ".[api,mcp]"
COPY --from=web /web/dist ./web/dist
ENV FREESTASH_WEB_DIST=/app/web/dist
EXPOSE 8787
CMD ["sh", "-c", "python -m uvicorn freestash.api.app:app --host 0.0.0.0 --port ${PORT:-8787} --proxy-headers"]
