#!/bin/bash
# =============================================================================
# pull_models.sh — Ollama model initialisation entrypoint
# =============================================================================
# This script is used as the Docker entrypoint for the ollama service in
# docker-compose.yml. It:
#   1. Starts the Ollama server in the background
#   2. Waits for the server to become responsive
#   3. Pulls required models (idempotent — skips if already downloaded)
#   4. Keeps the server running in the foreground
#
# On first run, llama3.2:3b (~2.0 GB) and nomic-embed-text (~270 MB)
# are downloaded from the Ollama registry. Subsequent starts are fast
# because model weights are stored in the ollama_data Docker volume.
# =============================================================================

set -euo pipefail

LLM_MODEL="${LLM_MODEL:-llama3.2:3b}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

echo "==> Starting Ollama server..."
ollama serve &
SERVER_PID=$!

# Wait for the Ollama API to become responsive.
# Retry every 2 seconds — model weight loading can take 10-30 seconds.
echo "==> Waiting for Ollama API..."
MAX_WAIT=60
WAITED=0
until curl -sf "${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "ERROR: Ollama API did not become ready within ${MAX_WAIT}s" >&2
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "==> Ollama API is ready."

# Pull models. ollama pull is idempotent:
#   - If the model is already present and up to date, this is a no-op.
#   - If a newer version is available, it will be downloaded.
echo "==> Pulling LLM model: ${LLM_MODEL}"
ollama pull "${LLM_MODEL}"

echo "==> Pulling embedding model: ${EMBEDDING_MODEL}"
ollama pull "${EMBEDDING_MODEL}"

echo "==> All models ready."
echo "    LLM:       ${LLM_MODEL}"
echo "    Embedding: ${EMBEDDING_MODEL}"

# Keep the server process running.
# 'wait' blocks until the background ollama serve process exits.
wait "${SERVER_PID}"
