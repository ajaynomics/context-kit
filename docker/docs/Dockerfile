FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

ARG MCP_VERSION=1.28.0
ARG MCP_PROXY_VERSION=0.12.0
ARG SENTENCE_TRANSFORMERS_VERSION=5.6.0
ARG TORCH_VERSION=2.12.1+cpu

COPY constraints.txt /tmp/context-kit-docs-constraints.txt

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first so sentence-transformers does not pull CUDA wheels.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      -c /tmp/context-kit-docs-constraints.txt \
      "torch==${TORCH_VERSION}"

RUN pip install --no-cache-dir -c /tmp/context-kit-docs-constraints.txt \
      "mcp==${MCP_VERSION}" \
      "mcp-proxy==${MCP_PROXY_VERSION}" \
      "sentence-transformers==${SENTENCE_TRANSFORMERS_VERSION}" \
      httpx numpy PyYAML \
 && rm /tmp/context-kit-docs-constraints.txt

COPY context_docs /opt/context-kit/context_docs
COPY tests /opt/context-kit/tests
COPY entrypoint.sh /usr/local/bin/docs-mcp-entrypoint
RUN chmod -R a+rX /opt/context-kit \
  && chmod 0555 /usr/local/bin/docs-mcp-entrypoint

RUN mkdir -p /data /models /etc/context-kit
ENV HF_HOME=/models \
    HOME=/tmp \
    USER=context-kit \
    LOGNAME=context-kit \
    SENTENCE_TRANSFORMERS_HOME=/models \
    PYTHONPATH=/opt/context-kit \
    DOCS_MCP_HTTP_HOST=0.0.0.0 \
    DOCS_MCP_HTTP_PORT=8000 \
    DOCS_MCP_STORE_PATH=/data/docs.sqlite3 \
    DOCS_MCP_SOURCES_FILE=/etc/context-kit/docs-sources.txt

VOLUME ["/data", "/models"]
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docs-mcp-entrypoint"]
