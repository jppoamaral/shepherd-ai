FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
ENV PATH="/app/.venv/bin:$PATH"

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home shepherd
USER shepherd

# Migrate, seed, serve on $PORT (Render). docker-compose sets its own commands.
CMD ["./start.sh"]
