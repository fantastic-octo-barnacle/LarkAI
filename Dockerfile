FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM rust:1.98-bookworm AS backend
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY backend/ backend/
RUN cargo build --release --locked -p larkai

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 larkai && useradd --uid 10001 --gid larkai --no-create-home larkai
WORKDIR /app
COPY --from=backend /build/target/release/larkai /usr/local/bin/larkai
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN mkdir -p /app/data && chown larkai:larkai /app/data
USER larkai
ENV HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/app/data/larkai.sqlite3 FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=6 CMD curl --fail --silent http://127.0.0.1:8000/healthz || exit 1
CMD ["larkai"]
