# Base Layer MCP server (stdio). Used by Glama to build, start and introspect the
# server. The image holds no specification and no database: it starts with an
# empty data root, needs no API key, and answers initialize, tools/list and
# resources/list. Tools report that no database exists until one is built.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CPU-only torch first. Without this, sentence-transformers pulls CUDA torch and
# the nvidia wheels, several GB the server never uses.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# A regular install, not editable: an editable install would make config.py
# resolve the data root to the source tree.
RUN pip install . && rm -rf /app/build /app/src

# Empty data root. MEMORY_SYSTEM_ROOT must point at an existing directory.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /opt/baselayer \
    && chown app:app /opt/baselayer
ENV MEMORY_SYSTEM_ROOT=/opt/baselayer
USER app

CMD ["baselayer-mcp"]
