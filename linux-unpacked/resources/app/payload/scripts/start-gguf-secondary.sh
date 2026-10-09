#!/usr/bin/env bash
# ─── GGUF Secondary LLM Server ─────────────────────────────────────────────
# Serves the Qwen2.5 7B Instruct Uncensored model via llama-cpp-python
# with dual-GPU tensor splitting (50/50 across 2x RTX 3060 12GB)
# Context: 8192 — increased from 4096 to fully utilize 2x 12GB VRAM
#
# Usage:
#   chmod +x scripts/start-gguf-secondary.sh
#   ./scripts/start-gguf-secondary.sh
#
# The server will be available at http://127.0.0.1:8000/v1
# ────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODEL_PATH="$PROJECT_ROOT/models/qwen2.5-7b-instruct-uncensored-q4_k_m.gguf"
PORT=8000
HOST="127.0.0.1"

# ─── Verify model exists ───────────────────────────────────────────────────
if [ ! -f "$MODEL_PATH" ]; then
    echo "ERROR: Model not found at $MODEL_PATH"
    echo ""
    echo "Download it first from HuggingFace:"
    echo "  wget -O \"$MODEL_PATH\" https://huggingface.co/QuantFactory/Qwen2.5-7B-Instruct-Uncensored-GGUF/resolve/main/qwen2.5-7b-instruct-uncensored.q4_k_m.gguf"
    exit 1
fi

MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          GGUF Secondary LLM Server                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Model:      $(basename $MODEL_PATH)"
echo "  Size:       $MODEL_SIZE"
echo "  GPUs:       2x RTX 3060 (12GB each)"
echo "  Tensor Split: 50/50"
echo "  Port:       $PORT"
echo "  API:        http://$HOST:$PORT/v1"
echo "  Compatible: OpenAI API format"
echo ""

# ─── Install dependencies if missing ──────────────────────────────────────
python3 -c "import llama_cpp" 2>/dev/null || {
    echo "[Setup] Installing llama-cpp-python for CUDA..."
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124 2>/dev/null || \
    CMAKE_ARGS="-DGGML_CUDA=ON" pip install llama-cpp-python
}

# ─── Launch the server ─────────────────────────────────────────────────────
python3 "$SCRIPT_DIR/gguf_server.py" \
    --model "$MODEL_PATH" \
    --port "$PORT" \
    --host "$HOST" \
    --n-gpu-layers -1 \
    --n-ctx 8192 \
    --tensor-split "0.5,0.5" \
    --split-mode "layer"
