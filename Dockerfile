# ── Stage 1: build deps ───────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies into a local prefix so we can copy them cleanly
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

# Create a non-root user — never run production containers as root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source (tests and dev files excluded via .dockerignore)
COPY server/ ./server/

# Set PYTHONPATH so "from server.xxx import yyy" resolves correctly
ENV PYTHONPATH=/app

# Render / Fly / Railway inject PORT at runtime; default to 8000 locally
ENV PORT=8000

# Drop to non-root user
USER appuser

EXPOSE 8000

# Healthcheck so deployment platforms know when the container is ready
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

CMD ["python", "-m", "server.main"]
