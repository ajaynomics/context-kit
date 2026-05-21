FROM python:3.12-slim

ARG LLMS_TXT_MCP_VERSION=0.2.0

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first so llms-txt-mcp does not pull large CUDA wheels.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      torch

RUN if [ -n "${LLMS_TXT_MCP_VERSION}" ]; then \
      pip install --no-cache-dir "llms-txt-mcp==${LLMS_TXT_MCP_VERSION}"; \
    else \
      pip install --no-cache-dir llms-txt-mcp; \
    fi

RUN mkdir -p /data /models
ENV HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

VOLUME ["/data", "/models"]

ENTRYPOINT ["llms-txt-mcp"]
