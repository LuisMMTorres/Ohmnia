# Development/demo image: built front-end served by the Python back-end, with ngspice.
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends ngspice libngspice0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV CIRCUITOS_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "python", "-m", "circuitos", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
