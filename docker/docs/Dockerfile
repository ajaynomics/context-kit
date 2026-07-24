FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

ARG LLMS_TXT_MCP_VERSION=0.2.0
ARG MCP_PROXY_VERSION=0.12.0
ARG TORCH_VERSION=2.12.1+cpu

COPY constraints.txt /tmp/context-kit-docs-constraints.txt

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first so llms-txt-mcp does not pull large CUDA wheels.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      -c /tmp/context-kit-docs-constraints.txt \
      "torch==${TORCH_VERSION}"

# llms-txt-mcp does the indexing/search; mcp-proxy fronts its stdio transport
# as Streamable HTTP so multiple MCP clients can share one long-lived process
# (and therefore one Chroma DB writer).
RUN if [ -n "${LLMS_TXT_MCP_VERSION}" ]; then \
      pip install --no-cache-dir -c /tmp/context-kit-docs-constraints.txt "llms-txt-mcp==${LLMS_TXT_MCP_VERSION}"; \
    else \
      pip install --no-cache-dir -c /tmp/context-kit-docs-constraints.txt llms-txt-mcp; \
    fi \
 && pip install --no-cache-dir -c /tmp/context-kit-docs-constraints.txt "mcp-proxy==${MCP_PROXY_VERSION}" \
 && rm /tmp/context-kit-docs-constraints.txt

COPY entrypoint.sh /usr/local/bin/docs-mcp-entrypoint
RUN chmod 0555 /usr/local/bin/docs-mcp-entrypoint

RUN mkdir -p /data /models /etc/context-kit
ENV HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    DOCS_MCP_HTTP_HOST=0.0.0.0 \
    DOCS_MCP_HTTP_PORT=8000 \
    DOCS_MCP_SOURCES_FILE=/etc/context-kit/docs-sources.txt

VOLUME ["/data", "/models"]
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docs-mcp-entrypoint"]
