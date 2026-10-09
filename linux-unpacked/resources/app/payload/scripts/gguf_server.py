#!/usr/bin/env python3
"""
GGUF Model Server — serves a GGUF model via OpenAI-compatible API.

Uses llama_cpp directly with a minimal FastAPI/uvicorn server.
Exposes /v1/chat/completions endpoint (OpenAI-compatible).

Usage:
    python scripts/gguf_server.py --model /path/to/model.gguf --port 8000
"""

import argparse
import sys
import os
import signal
import json
import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    stream: Optional[bool] = False


class CompletionRequest(BaseModel):
    model: str = "default"
    prompt: str
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    stream: Optional[bool] = False


def create_app(model_path: str, n_gpu_layers: int, n_ctx: int, n_threads: Optional[int],
               tensor_split: Optional[list] = None, split_mode: str = 'layer'):
    from llama_cpp import Llama

    split_mode_map = {'none': 0, 'layer': 1, 'row': 2}

    print(f"[GGUF Server] Loading model: {model_path}", flush=True)
    print(f"[GGUF Server] GPU layers: {n_gpu_layers}, Context: {n_ctx}", flush=True)
    if tensor_split:
        print(f"[GGUF Server] Tensor split: {tensor_split}", flush=True)

    # Build optional kwargs for multi-GPU
    gpu_kwargs = {}
    if tensor_split:
        gpu_kwargs["tensor_split"] = tensor_split
    if split_mode != 'layer':
        gpu_kwargs["split_mode"] = split_mode_map.get(split_mode, 1)

    try:
        llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
            **gpu_kwargs,
        )
    except TypeError as e:
        if gpu_kwargs:
            print(f"[GGUF Server] Multi-GPU kwargs not supported by this llama-cpp version, falling back to single GPU: {e}", flush=True)
            llm = Llama(
                model_path=model_path,
                n_gpu_layers=n_gpu_layers,
                n_ctx=n_ctx,
                n_threads=n_threads,
                verbose=False,
            )
        else:
            raise

    app = FastAPI(title="GGUF Server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    @app.get("/v1/health")
    async def health():
        return {"status": "ok", "model": os.path.basename(model_path)}

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                {
                    "id": os.path.basename(model_path),
                    "object": "model",
                    "created": int(os.path.getmtime(model_path)),
                    "owned_by": "gguf-server",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        start_time = time.time()
        # Use create_chat_completion which auto-applies the model's chat template
        output = llm.create_chat_completion(
            messages=[m.model_dump() for m in req.messages],
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
        elapsed = time.time() - start_time

        content = output["choices"][0]["message"]["content"] if output["choices"] else ""
        prompt_tokens = output["usage"]["prompt_tokens"] if "usage" in output else 0
        completion_tokens = output["usage"]["completion_tokens"] if "usage" in output else 0

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": os.path.basename(model_path),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    @app.post("/v1/completions")
    async def completions(req: CompletionRequest):
        start_time = time.time()
        output = llm(
            req.prompt,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            top_k=req.top_k or 40,
            stop=["</s>"],
            echo=False,
        )
        elapsed = time.time() - start_time

        content = output["choices"][0]["text"] if output["choices"] else ""
        prompt_tokens = output["usage"]["prompt_tokens"] if "usage" in output else 0
        completion_tokens = output["usage"]["completion_tokens"] if "usage" in output else 0

        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": os.path.basename(model_path),
            "choices": [
                {
                    "index": 0,
                    "text": content,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return app


def main():
    parser = argparse.ArgumentParser(description="GGUF Model Server")
    parser.add_argument("--model", required=True, help="Path to the GGUF model file")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--n-gpu-layers", type=int, default=-1,
                        help="Number of layers to offload to GPU (-1 = all, 0 = CPU only)")
    parser.add_argument("--n-ctx", type=int, default=4096, help="Context size (default: 4096)")
    parser.add_argument("--n-threads", type=int, default=0,
                        help="Number of CPU threads (0 = auto)")
    parser.add_argument("--tensor-split", type=str, default=None,
                        help="GPU memory split ratio for multi-GPU, e.g. '0.5,0.5' for 2 GPUs")
    parser.add_argument("--split-mode", type=str, default='layer', choices=['none', 'layer', 'row'],
                        help="Model splitting strategy across GPUs (default: layer)")

    args = parser.parse_args()

    model_path = os.path.abspath(args.model)
    if not os.path.isfile(model_path):
        print(f"ERROR: Model file not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    n_threads = args.n_threads if args.n_threads > 0 else None

    # Parse tensor split for multi-GPU
    tensor_split_list = None
    if args.tensor_split:
        try:
            tensor_split_list = [float(x.strip()) for x in args.tensor_split.split(',')]
        except ValueError:
            print(f"WARNING: Invalid tensor-split value '{args.tensor_split}', using default", file=sys.stderr)

    app = create_app(
        model_path=model_path,
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
        n_threads=n_threads,
        tensor_split=tensor_split_list,
        split_mode=args.split_mode,
    )

    print(f"\n[GGUF Server] Starting on {args.host}:{args.port}", flush=True)
    print(f"[GGUF Server] Model: {model_path}", flush=True)
    print(f"[GGUF Server] GPU layers: {args.n_gpu_layers}, Context: {args.n_ctx}", flush=True)
    if tensor_split_list:
        print(f"[GGUF Server] Tensor split across GPUs: {tensor_split_list}", flush=True)
    print(f"[GGUF Server] Split mode: {args.split_mode}", flush=True)
    print(f"[GGUF Server] OpenAI API: http://{args.host}:{args.port}/v1\n", flush=True)

    def shutdown(sig, frame):
        print(f"\n[GGUF Server] Shutting down...", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
