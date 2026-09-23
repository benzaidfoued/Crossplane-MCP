FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv==0.12.17
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --compile-bytecode

FROM python:3.12-slim
LABEL org.opencontainers.image.title="Crossplane Compass"       org.opencontainers.image.description="Evidence-first Crossplane MCP server"       org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd -g 10001 compass && useradd -u 10001 -g compass -m compass
COPY --from=builder /build/.venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "crossplane_compass.server"]
