FROM python:3.12-slim

# -----------------------------
# System dependencies
# -----------------------------
RUN apt-get update && apt-get install -y \
    curl \
    tree \
    ca-certificates \
    pandoc \          # Added pandoc (available in Debian repos)
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Create user early (clean layering)
# -----------------------------
RUN useradd -m appuser

WORKDIR /app

# -----------------------------
# Copy ONLY dependency files first (critical for caching)
# -----------------------------
COPY pyproject.toml uv.lock ./

# -----------------------------
# Install uv
# -----------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/home/appuser/.local/bin:$PATH"

# Improve network resilience (important for your region)
ENV UV_HTTP_TIMEOUT=300
ENV UV_LINK_MODE=copy

# -----------------------------
# Install dependencies (cached layer)
# -----------------------------
RUN uv sync --frozen

# -----------------------------
# Now copy the actual project
# (this change will NOT reinstall deps anymore)
# -----------------------------
COPY . .

RUN chown -R appuser:appuser /app
USER appuser

# -----------------------------
# Build-time generation step
# -----------------------------
RUN uv run python docs_converter/godot_docs_converter.py

RUN tree docs/. > docs/docs_tree.txt

# -----------------------------
# Runtime command
# -----------------------------
CMD ["uv", "run", "fastmcp", "run", "main.py"]