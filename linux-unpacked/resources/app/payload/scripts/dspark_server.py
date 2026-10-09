#!/usr/bin/env python3
"""
DSpark Server — OpenAI-compatible GGUF server (llama.cpp).

Two modes:

1. Plain mode (default) — loads a local GGUF with llama-cpp-python and serves
   it on :8000. The legacy llama-cpp-python draft path (LlamaModelDraft) is
   experimental and NOT an accelerator on the 0.3.x build (it re-evaluates the
   full context per step, ~parity-to-slower), so draft mode defaults to 'none'.

2. Spec mode (--spec-draft <DSpark GGUF>) — serves the target WITH the trained
   DSpark draft head. llama-cpp-python can't run a dflash/dspark head, so this
   delegates to a llama-server binary that supports `--spec-type draft-dspark`
   (default: the LM Studio CUDA12 backend) and proxies the OpenAI-compatible
   API, adding /v1/health for the VACA backend probes. Enable from the launcher
   with DSPARK_SPEC_DRAFT=/path/to/Qwen3.8-27B-DSpark-Q8_0.gguf.

GPU handling:
  --n-gpu-layers defaults to 'auto' — the layer count is fitted to the visible
  VRAM (weights + KV + compute headroom) so the server boots on a 6 GB card OR
  the remote 3×12 GB box. Load/context-allocation failures retry with halved
  layers down to CPU-only. '-1'/N pass through as requested. Tensor splits that
  reference GPUs that don't exist are dropped.

Target resolution: a GGUF path, or an Ollama model name resolved from its
manifest (e.g. qwen2.5-7b-instruct-uncensored:latest).

Exposes OpenAI-compatible endpoints:
  GET  /v1/models
  POST /v1/chat/completions
  POST /v1/completions
  GET  /v1/health

Usage:
    python scripts/dspark_server.py --port 8000 --n-ctx 16384
    python scripts/dspark_server.py --spec-draft Qwen3.8-27B-DSpark-Q8_0.gguf
"""

import argparse
import os
import sys
import json
import time
import signal
import asyncio
import socket
import shutil
import struct
import subprocess
import threading
from collections import deque
from typing import Optional, List, Any, Dict

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel


# ── Model resolution helpers ────────────────────────────────────────────────

OLLAMA_MODEL_DIRS = [
    os.path.expanduser('~/.ollama/models'),
    '/usr/share/ollama/.ollama/models',
    '/var/lib/ollama/models',
]


def resolve_gguf(model_name: str) -> Optional[str]:
    """Resolve a model name like 'qwen2.5-7b-instruct-uncensored:latest' or
    'qwen2.5-coder:0.5b' to its GGUF blob path via Ollama manifests."""
    # Normalize: 'library/qwen2.5-coder:0.5b' -> namespace 'library', name, tag
    ns = 'library'
    rest = model_name
    if '/' in rest:
        ns, rest = rest.split('/', 1)
    if ':' in rest:
        name, tag = rest.split(':', 1)
    else:
        name, tag = rest, 'latest'

    for base in OLLAMA_MODEL_DIRS:
        manifest = os.path.join(base, 'manifests', 'registry.ollama.ai', ns, name, tag)
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest) as f:
                data = json.load(f)
            for layer in data.get('layers', []):
                if 'model' in layer.get('mediaType', ''):
                    digest = layer['digest'].replace('sha256:', '')
                    blob = os.path.join(base, 'blobs', f'sha256-{digest}')
                    if os.path.isfile(blob):
                        return blob
        except Exception as e:
            print(f"[DSpark] Failed to parse manifest {manifest}: {e}", file=sys.stderr)
    return None


# ── Hardware-aware GPU helpers ───────────────────────────────────────────────
# The old launcher default was `--n-gpu-layers -1` + a 3-way tensor split,
# tuned for the remote 3×RTX 3060 box. On machines with a single small GPU
# (e.g. this 6 GB GTX 1660 Ti) that combination made llama.cpp fail to load
# the model entirely ("Failed to load model from file"). These helpers pick a
# layer count that actually fits the visible VRAM, and drop tensor splits that
# reference GPUs that don't exist.

def _gguf_kv(path: str) -> Dict[str, Any]:
    """Read a GGUF file's top-level metadata KV pairs (format-version tolerant).
    Returns {} on any parse error — callers treat missing keys as 'unknown'."""
    try:
        with open(path, 'rb') as f:
            if f.read(4) != b'GGUF':
                return {}
            f.read(4)  # version
            _n_tensors, n_kv = struct.unpack('<QQ', f.read(16))
            kv: Dict[str, Any] = {}

            def read_val(ftype: int):
                if ftype == 0: return struct.unpack('<B', f.read(1))[0]
                if ftype == 1: return struct.unpack('<b', f.read(1))[0]
                if ftype == 2: return struct.unpack('<H', f.read(2))[0]
                if ftype == 3: return struct.unpack('<h', f.read(2))[0]
                if ftype == 4: return struct.unpack('<I', f.read(4))[0]
                if ftype == 5: return struct.unpack('<i', f.read(4))[0]
                if ftype == 6: return struct.unpack('<f', f.read(4))[0]
                if ftype == 7: return struct.unpack('<?', f.read(1))[0]
                if ftype == 8:
                    ln = struct.unpack('<Q', f.read(8))[0]
                    return f.read(ln).decode('utf-8', 'replace')
                if ftype == 9:
                    etype = struct.unpack('<I', f.read(4))[0]
                    n = struct.unpack('<Q', f.read(8))[0]
                    return [read_val(etype) for _ in range(n)]
                if ftype == 10: return struct.unpack('<Q', f.read(8))[0]
                if ftype == 11: return struct.unpack('<q', f.read(8))[0]
                if ftype == 12: return struct.unpack('<d', f.read(8))[0]
                raise ValueError(f'unknown gguf type {ftype}')

            for _ in range(n_kv):
                # GGUF v3 layout: key_len (uint64) -> key -> value type (uint32)
                # -> value (older readers assume type-first; the files in the
                # wild here are v3, and the bytes don't lie).
                klen = struct.unpack('<Q', f.read(8))[0]
                key = f.read(klen).decode('utf-8', 'replace')
                vtype = struct.unpack('<I', f.read(4))[0]
                kv[key] = read_val(vtype)
            return kv
    except Exception:
        return {}


def gguf_block_count(path: str) -> Optional[int]:
    """Decoder-layer count of a GGUF (e.g. 48 for a 14B), or None when unknown."""
    try:
        kv = _gguf_kv(path)
        arch = kv.get('general.architecture')
        if isinstance(arch, str) and arch:
            bc = kv.get(f'{arch}.block_count')
            if isinstance(bc, int) and bc > 0:
                return bc
        for k, v in kv.items():
            if k.endswith('.block_count') and isinstance(v, int) and v > 0:
                return v
    except Exception:
        pass
    return None


def gpu_vram_mb() -> tuple:
    """(total_mb, free_mb) summed across CUDA GPUs; (0, 0) when no nvidia-smi."""
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total,memory.free', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10,
        ).stdout
        total = free = 0
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) == 2:
                total += int(parts[0])
                free += int(parts[1])
        return total, free
    except Exception:
        return 0, 0


def gpu_count() -> int:
    """Number of CUDA GPUs visible to nvidia-smi (0 when none)."""
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=index', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10,
        ).stdout
        return len([l for l in out.strip().splitlines() if l.strip()])
    except Exception:
        return 0


def resolve_n_gpu_layers(value: str, model_path: str, reserve_mb: int = 1024) -> int:
    """Resolve a --n-gpu-layers value: 'auto' fits the model to visible VRAM
    (full offload when it fits, partial otherwise, 0 = CPU when no GPU),
    anything else (e.g. '-1') is passed through as the user asked."""
    if value != 'auto':
        return int(value)
    total_mb, free_mb = gpu_vram_mb()
    if total_mb <= 0:
        print('[DSpark] No CUDA GPU detected — running CPU-only (n_gpu_layers=0)', flush=True)
        return 0
    ngpus = max(gpu_count(), 1)
    free_per_gpu = free_mb / ngpus
    try:
        size_mb = os.path.getsize(model_path) / 1048576.0
    except OSError:
        size_mb = 0.0
    # Full offload only when BOTH total free and PER-GPU free fit the model
    # share + a real reserve (KV/compute buffers live per GPU). Summing free
    # VRAM across GPUs used to falsely claim 'fits' on a shared box and OOM the
    # first context (observed: 3x3060 with two 14Bs already resident).
    if free_mb >= size_mb + reserve_mb and free_per_gpu >= size_mb / ngpus + reserve_mb:
        print(f'[DSpark] Model fits in {free_mb:.0f}MB free VRAM ({free_per_gpu:.0f}MB/GPU) — full offload (-1)', flush=True)
        return -1
    block_count = gguf_block_count(model_path)
    if not block_count:
        print(f'[DSpark] Could not read layer count; {free_mb:.0f}MB free < {size_mb:.0f}MB model — CPU-only', flush=True)
        return 0
    per_layer_mb = size_mb / block_count
    # Budget against the SMALLEST comfortable per-GPU share — conservative, so
    # a 3rd model on a shared box lands safely (spill to RAM instead of OOM).
    layers = int((free_per_gpu - reserve_mb) * ngpus / per_layer_mb)
    layers = max(0, min(block_count, layers))
    print(f'[DSpark] {free_mb:.0f}MB free VRAM ({free_per_gpu:.0f}MB/GPU) < {size_mb:.0f}MB model — offloading {layers}/{block_count} layers',
          flush=True)
    return layers


# ── Request models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = 'default'
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    stream: Optional[bool] = False


class CompletionRequest(BaseModel):
    model: str = 'default'
    prompt: str
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    stream: Optional[bool] = False


# ── App factory ─────────────────────────────────────────────────────────────

class LlamaModelDraft:
    """A real-model drafter for llama-cpp-python 0.3.x.

    The library calls draft(input_ids) and expects a numpy array of draft token
    ids back. We run the small draft Llama greedily on the same token ids and
    return its raw predicted tokens. The target model verifies every proposed
    token, so output quality is unchanged (lossless) — but on this 0.3.x build
    the drafter re-evaluates the full context each step and does NOT speed up
    generation, so this mode is experimental only.
    """

    def __init__(self, draft_llm, num_pred_tokens: int = 16):
        self.draft_llm = draft_llm
        self.num_pred_tokens = num_pred_tokens

    def __call__(self, input_ids, **kwargs):
        import numpy as np
        try:
            ids = np.asarray(input_ids)
            prompt_list = ids.astype(np.int32).tolist()
            if len(prompt_list) == 0:
                return np.array([], dtype=np.int32)
            output = self.draft_llm.create_completion(
                prompt=prompt_list,
                max_tokens=self.num_pred_tokens,
                temperature=0.0,
                stream=False,
            )
            text = output.get('choices', [{}])[0].get('text', '') or ''
            tokens = self.draft_llm.tokenize(text.encode('utf-8'), add_bos=False)
            return np.asarray(tokens, dtype=np.int32)
        except Exception as e:
            # Never let the drafter kill generation — empty draft = no proposals.
            print(f'[DSpark] Draft pass failed (falling back to no draft): {e}', flush=True)
            return np.array([], dtype=np.int32)


def create_app(target_path: str, draft_path: Optional[str], n_gpu_layers: int, n_ctx: int,
               n_threads: Optional[int], tensor_split: Optional[list] = None,
               split_mode: str = 'layer', n_batch: int = 512, model_id: Optional[str] = None,
               draft_gpu_layers: int = -1, draft_num_pred_tokens: int = 16,
               draft_mode: str = 'none', flash_attn: bool = False,
               spec_draft_path: Optional[str] = None, spec_n_max: int = 4,
               spec_bin: Optional[str] = None, spec_port: int = 0,
               llama_server: bool = False):
    from llama_cpp import Llama
    from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

    split_mode_map = {'none': 0, 'layer': 1, 'row': 2}

    print(f"[DSpark] Target model: {target_path}", flush=True)
    print(f"[DSpark] Draft mode:   {draft_mode}", flush=True)
    if draft_mode == 'model':
        print(f"[DSpark] Draft model:  {draft_path}", flush=True)
    print(f"[DSpark] GPU layers: {n_gpu_layers} (target) / {draft_gpu_layers} (draft), "
          f"Context: {n_ctx}, Batch: {n_batch}", flush=True)
    if tensor_split:
        print(f"[DSpark] Tensor split: {tensor_split}", flush=True)

    # ── Spec mode: serve the target WITH the trained DSpark draft head ──
    # llama-cpp-python 0.3.x cannot run a dflash/dspark spec head (the draft
    # re-evaluates the whole context and has no hidden-state access), so spec
    # mode delegates to a llama-server binary that supports `--spec-type
    # draft-dspark` (default: the LM Studio CUDA12 backend that ships it) and
    # exposes the SAME OpenAI-compatible API on this port, plus /v1/health.
    if spec_draft_path:
        return _create_spec_app(
            target_path=target_path,
            spec_draft_path=spec_draft_path,
            spec_n_max=spec_n_max,
            spec_bin=spec_bin,
            n_gpu_layers=n_gpu_layers,
            draft_gpu_layers=draft_gpu_layers,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            port=spec_port,
            model_id=model_id,
        )
    if llama_server:
        # Plain llama-server mode (no draft head): serve the target via a
        # llama.cpp llama-server binary. Qwen3-family GGUFs default to the
        # thinking chat template, which llama-cpp-python 0.3.x leaks as plain
        # content; llama-server handles it and `--reasoning off` returns clean
        # final answers. Enable with DSPARK_LLAMA_SERVER=1 (or --llama-server).
        print(f'[DSpark] llama-server mode (no draft head) — reasoning off', flush=True)
        return _create_spec_app(
            target_path=target_path,
            spec_draft_path=None,
            spec_n_max=spec_n_max,
            spec_bin=spec_bin,
            n_gpu_layers=n_gpu_layers,
            draft_gpu_layers=draft_gpu_layers,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            port=spec_port,
            model_id=model_id,
        )

    # Draft must be a LlamaDraftModel-style callable that returns raw token ids.
    if draft_mode == 'lookup':
        # Built-in n-gram lookup drafter — zero extra model, minimal overhead.
        draft_wrapper = LlamaPromptLookupDecoding(num_pred_tokens=draft_num_pred_tokens)
        print(f"[DSpark] Using built-in prompt-lookup drafter", flush=True)
    elif draft_mode == 'none':
        draft_wrapper = None
        print(f"[DSpark] Draft mode 'none' — no drafter attached", flush=True)
    else:
        draft_llm = Llama(
            model_path=draft_path,
            n_gpu_layers=draft_gpu_layers,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            verbose=False,
        )
        print(f"[DSpark] Draft model loaded ({os.path.basename(draft_path)})", flush=True)
        draft_wrapper = LlamaModelDraft(draft_llm, num_pred_tokens=draft_num_pred_tokens)

    gpu_kwargs = {}
    if tensor_split:
        gpu_kwargs['tensor_split'] = tensor_split
    if split_mode != 'layer':
        gpu_kwargs['split_mode'] = split_mode_map.get(split_mode, 1)

    # The initial n_gpu_layers estimate covers weights + KV cache, but the
    # prefill compute buffer (1.4 GB at n_batch=512 on a 14B) can still push a
    # small GPU over the edge. Retry with halved layers on any load/context
    # failure — the model file stays mmap'd, so each retry is fast — until it
    # boots (possibly CPU-only). Multi-GPU kwargs that the build rejects are
    # retried without them.
    def _make_llm(layers: int, kw: dict):
        try:
            llm = Llama(
                model_path=target_path,
                draft_model=draft_wrapper,
                n_gpu_layers=layers,
                n_ctx=n_ctx,
                n_batch=n_batch,
                n_threads=n_threads,
                flash_attn=flash_attn,
                verbose=False,
                **kw,
            )
            return llm, None
        except TypeError as e:
            if kw:
                print(f'[DSpark] Multi-GPU kwargs not supported, retrying single-GPU: {e}', flush=True)
                return _make_llm(layers, {})
            return None, e
        except (ValueError, RuntimeError) as e:
            return None, e

    # Positive values halve down to 0 (CPU) so a small GPU always boots. Full
    # offload (-1) is attempted first but ALSO falls back through the halving
    # chain — a shared-box OOM at full offload must not be fatal.
    block_count = gguf_block_count(target_path) or 64
    attempts = []
    a = n_gpu_layers
    if a < 0:
        attempts.append(-1)
        a = block_count
    while a >= 0:
        attempts.append(a)
        if a == 0:
            break
        a = a // 2

    llm, err = None, None
    for attempt in attempts:
        kw = dict(gpu_kwargs)
        if attempt <= 0:
            kw.pop('tensor_split', None)
            kw.pop('split_mode', None)
        llm, err = _make_llm(attempt, kw)
        if llm is not None:
            break
        if attempt == attempts[-1]:
            raise err
        print(f'[DSpark] Load failed at {attempt} GPU layers ({type(err).__name__}: {err}) — retrying with {attempts[attempts.index(attempt) + 1]}',
              flush=True)

    target_id = model_id or os.path.basename(target_path)
    app = FastAPI(title='DSpark GGUF Server (OpenAI-compatible)')

    # ── Offload blocking generation ─────────────────────────────────────────
    # llama.cpp generation is synchronous AND long (minutes at 16k ctx). Calling
    # llm.* inside `async def` blocks uvicorn's event loop, so /v1/health and
    # /v1/models time out while the model is actually fine (the backend then
    # reports `llm: up:false` mid-build). Run generation in a worker thread so
    # the event loop stays free to serve health/models. The lock serializes
    # generation because llama.cpp's Llama is not safe for concurrent calls.
    _gen_lock = threading.Lock()

    async def _run_blocking(func, *args, **kwargs):
        def _worker():
            with _gen_lock:
                return func(*args, **kwargs)

        return await asyncio.to_thread(_worker)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    # ── Throughput stats (rolling window, exposed via /health) ──
    # Each completion records (completion_tokens, elapsed_seconds). Tokens/sec is
    # computed over the recent window so the status UI shows real-world throughput
    # for the current draft mode.
    _stats_lock = threading.Lock()
    _stat_window: 'deque[tuple[int, float]]' = deque(maxlen=20)
    _total_completion_tokens = 0
    _total_requests = 0

    def _record_stats(completion_tokens: int, elapsed: float):
        nonlocal _total_completion_tokens, _total_requests
        with _stats_lock:
            _stat_window.append((completion_tokens, elapsed))
            _total_completion_tokens += completion_tokens
            _total_requests += 1

    def _stats_snapshot() -> Dict[str, Any]:
        with _stats_lock:
            if not _stat_window:
                return {
                    'tokens_per_sec': None,
                    'avg_latency_ms': None,
                    'total_completion_tokens': _total_completion_tokens,
                    'requests': _total_requests,
                }
            total_tokens = sum(t for t, _ in _stat_window)
            total_elapsed = sum(e for _, e in _stat_window)
            tps = total_tokens / total_elapsed if total_elapsed > 0 else 0.0
            avg_ms = (total_elapsed / len(_stat_window)) * 1000
            return {
                'tokens_per_sec': round(tps, 2),
                'avg_latency_ms': round(avg_ms, 1),
                'total_completion_tokens': _total_completion_tokens,
                'requests': _total_requests,
            }

    @app.get('/health')
    @app.get('/v1/health')
    async def health():
        body = {
            'status': 'ok',
            'model': target_id,
            'draft_mode': draft_mode,
            'speculative_decoding': draft_mode != 'none',
            'stats': _stats_snapshot(),
        }
        if draft_mode == 'model':
            body['draft'] = os.path.basename(draft_path)
        return body

    @app.get('/v1/models')
    async def list_models():
        return {
            'object': 'list',
            'data': [
                {
                    'id': target_id,
                    'object': 'model',
                    'created': int(os.path.getmtime(target_path)),
                    'owned_by': 'dspark-server',
                }
            ],
        }

    @app.post('/v1/chat/completions')
    async def chat_completions(req: ChatCompletionRequest):
        start_time = time.time()
        output = await _run_blocking(
            llm.create_chat_completion,
            messages=[m.model_dump() for m in req.messages],
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            top_k=req.top_k,
        )
        elapsed = time.time() - start_time

        content = output['choices'][0]['message']['content'] if output.get('choices') else ''
        prompt_tokens = output.get('usage', {}).get('prompt_tokens', 0)
        completion_tokens = output.get('usage', {}).get('completion_tokens', 0)
        tps = completion_tokens / elapsed if elapsed > 0 else 0
        _record_stats(completion_tokens, elapsed)
        draft_note = ", drafter attached" if draft_mode != 'none' else ""
        print(f"[DSpark] chat: {completion_tokens} tokens in {elapsed:.2f}s ({tps:.1f} tok/s{draft_note})",
              flush=True)

        return {
            'id': f'chatcmpl-{int(time.time())}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': target_id,
            'choices': [
                {
                    'index': 0,
                    'message': {'role': 'assistant', 'content': content},
                    'finish_reason': 'stop',
                }
            ],
            'usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
            },
        }

    @app.post('/v1/completions')
    async def completions(req: CompletionRequest):
        start_time = time.time()
        output = await _run_blocking(
            llm,
            req.prompt,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            top_k=req.top_k or 40,
            stop=['</s>'],
            echo=False,
        )
        elapsed = time.time() - start_time

        content = output['choices'][0]['text'] if output.get('choices') else ''
        prompt_tokens = output.get('usage', {}).get('prompt_tokens', 0)
        completion_tokens = output.get('usage', {}).get('completion_tokens', 0)
        tps = completion_tokens / elapsed if elapsed > 0 else 0
        _record_stats(completion_tokens, elapsed)
        print(f"[DSpark] completion: {completion_tokens} tokens in {elapsed:.2f}s ({tps:.1f} tok/s)",
              flush=True)

        return {
            'id': f'cmpl-{int(time.time())}',
            'object': 'text_completion',
            'created': int(time.time()),
            'model': target_id,
            'choices': [
                {
                    'index': 0,
                    'text': content,
                    'finish_reason': 'stop',
                }
            ],
            'usage': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
            },
        }

    return app


def _find_spec_bin() -> Optional[str]:
    """Locate a llama-server binary (used by both spec mode and plain
    llama-server mode). Priority: $DSPARK_SPEC_BIN, the newest LM Studio CUDA12
    backend (bundles its own CUDA runtime), then any llama-server on PATH."""
    candidates = [os.environ.get('DSPARK_SPEC_BIN')]
    backends_root = os.path.expanduser('~/.lmstudio/extensions/backends')
    try:
        versions = sorted(
            (d for d in os.listdir(backends_root)
             if d.startswith('llama.cpp-linux-x86_64-nvidia-cuda12-')),
            reverse=True,
        )
        if versions:
            candidates.append(os.path.join(backends_root, versions[0], 'llama-server'))
    except OSError:
        pass
    candidates.append(shutil.which('llama-server'))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _create_spec_app(target_path: str, spec_draft_path: str, spec_n_max: int,
                     spec_bin: Optional[str], n_gpu_layers: int, draft_gpu_layers: int,
                     n_ctx: int, n_batch: int, n_threads: Optional[int], port: int,
                     model_id: Optional[str]) -> FastAPI:
    """Spec mode: run llama-server (draft-dspark) on an internal port and proxy
    the OpenAI-compatible API on the public port, adding /v1/health so the VACA
    backend's probes (ensureDSparkServer, /api/llm/dspark-status) keep working."""
    import httpx

    bin_path = spec_bin or _find_spec_bin()
    if not bin_path:
        raise RuntimeError('Spec / llama-server mode needs a llama-server binary '
                           '(set DSPARK_SPEC_BIN or install one).')
    is_spec = spec_draft_path is not None
    print(f'[DSpark] {"Spec" if is_spec else "llama-server"} mode: {os.path.basename(bin_path)}' +
          (f' with draft {os.path.basename(spec_draft_path)}' if is_spec else ' (reasoning off)'),
          flush=True)

    # Internal port for the real server (public port stays for the proxy).
    internal_port = port + 1
    if internal_port > 65535:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            internal_port = s.getsockname()[1]

    cmd = [
        bin_path,
        '-m', target_path,
        '-c', str(n_ctx),
        '-b', str(n_batch),
        '-ngl', str(n_gpu_layers),
        '--host', '127.0.0.1',
        '--port', str(internal_port),
        '--no-warmup',
    ]
    if is_spec:
        cmd += [
            '--model-draft', spec_draft_path,
            '--spec-type', 'draft-dspark',
            '--spec-draft-n-max', str(spec_n_max),
            '-ngld', str(draft_gpu_layers),
        ]
    else:
        # Qwen3-family templates default to thinking mode; without this the
        # reasoning tokens would be emitted as plain content.
        cmd += ['--reasoning', 'off']
    if n_threads:
        cmd += ['-t', str(n_threads)]
    if model_id:
        cmd += ['-a', model_id]
    print(f'[DSpark] Spawning: {" ".join(cmd)}', flush=True)

    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1, start_new_session=True)

    def _pump():
        try:
            for line in child.stdout:
                print(f'[spec] {line}', end='', flush=True)
        except Exception:
            pass

    threading.Thread(target=_pump, daemon=True).start()

    # Wait for the real server (target + draft can take minutes to load).
    base = f'http://127.0.0.1:{internal_port}'
    deadline = time.time() + 600
    while time.time() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f'llama-server exited early (rc={child.returncode}) — see log above')
        try:
            if httpx.get(f'{base}/health', timeout=2).status_code == 200:
                print(f'[DSpark] Spec server ready on internal port {internal_port}', flush=True)
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        child.terminate()
        raise RuntimeError('Spec server did not become healthy within 600s')

    global _SPEC_CHILD
    _SPEC_CHILD = child

    client = httpx.AsyncClient(timeout=None)
    target_id = model_id or os.path.basename(target_path)
    app = FastAPI(title='DSpark Spec Server (OpenAI-compatible, draft-dspark)')
    app.add_middleware(
        CORSMiddleware, allow_origins=['*'], allow_credentials=True,
        allow_methods=['*'], allow_headers=['*'],
    )

    async def _relay(method: str, path: str, req_body=None, stream: bool = False):
        url = f'{base}{path}'
        if stream:
            upstream = client.stream(method, url, json=req_body)
            up = await upstream.__aenter__()
            return StreamingResponse(
                up.aiter_raw(), status_code=up.status_code,
                media_type=up.headers.get('content-type', 'application/json'),
                background=upstream.aclose,
            )
        resp = await client.request(method, url, json=req_body)
        return Response(content=resp.content, status_code=resp.status_code,
                        media_type=resp.headers.get('content-type', 'application/json'))

    @app.post('/v1/chat/completions')
    async def chat_completions(req: Request):
        body = await req.json()
        return await _relay('POST', '/v1/chat/completions', body, stream=bool(body.get('stream')))

    @app.post('/v1/completions')
    async def completions(req: Request):
        body = await req.json()
        return await _relay('POST', '/v1/completions', body, stream=bool(body.get('stream')))

    @app.get('/v1/models')
    async def list_models():
        # Normalize to the OpenAI 'data' shape the VACA backend/frontend expect
        # (llama-server returns {'models': [...]} with the raw path as the id).
        return {
            'object': 'list',
            'data': [{
                'id': target_id,
                'object': 'model',
                'created': int(os.path.getmtime(target_path)),
                'owned_by': 'dspark-server',
            }],
        }

    @app.get('/v1/health')
    @app.get('/health')
    async def health():
        body = {
            'status': 'ok',
            'model': target_id,
            'draft_mode': 'model' if is_spec else 'none',
            'speculative_decoding': is_spec,
            'stats': {},
        }
        if is_spec:
            body['draft'] = os.path.basename(spec_draft_path)
            body['spec_draft_n_max'] = spec_n_max
        return body

    return app


# The spec-mode llama-server child (killed on SIGTERM/SIGINT).
_SPEC_CHILD: Optional[subprocess.Popen] = None


def main():
    parser = argparse.ArgumentParser(description='DSpark GGUF server (OpenAI-compatible)')
    parser.add_argument('--target', default='qwen2.5-7b-instruct-uncensored:latest',
                        help='Target model name (Ollama) or GGUF path')
    parser.add_argument('--draft', default='qwen2.5-coder:0.5b',
                        help='Draft model name (Ollama) or GGUF path')
    parser.add_argument('--port', type=int, default=8000, help='Server port (default: 8000)')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: 127.0.0.1)')
    parser.add_argument('--n-gpu-layers', type=str, default='auto',
                        help='GPU layers for target: auto (fit to VRAM, default), -1 (all), N, or 0 (CPU)')
    parser.add_argument('--draft-gpu-layers', type=int, default=-1,
                        help='GPU layers for draft model (-1 = all, 0 = CPU; default: -1)')
    parser.add_argument('--draft-num-pred-tokens', type=int, default=16,
                        help='Tokens drafted per proposal pass (default: 16)')
    parser.add_argument('--draft-mode', type=str, default='none',
                        choices=['model', 'lookup', 'none'],
                        help='Drafter: model (qwen2.5-coder:0.5b), lookup (built-in n-gram), none (off, default)')
    parser.add_argument('--n-ctx', type=int, default=16384, help='Context size (default: 16384)')
    parser.add_argument('--n-batch', type=int, default=512, help='Batch size (default: 512)')
    parser.add_argument('--n-threads', type=int, default=0, help='CPU threads (0 = auto)')
    parser.add_argument('--model-id', type=str, default='qwen2.5-coder-14b-uncensored-dspark',
                        help='Model id reported by the API (default: qwen2.5-coder-14b-uncensored-dspark)')
    parser.add_argument('--tensor-split', type=str, default=None,
                        help="GPU memory split, e.g. '0.5,0.5' for 2 GPUs")
    parser.add_argument('--split-mode', type=str, default='layer',
                        choices=['none', 'layer', 'row'])
    parser.add_argument('--flash-attn', action='store_true',
                        help='Enable flash attention (faster attention, less VRAM)')
    parser.add_argument('--spec-draft', type=str, default=None,
                        help='DSpark draft GGUF (Qwen3.8-27B-DSpark-Q8_0.gguf) — spec mode via llama-server')
    parser.add_argument('--spec-n-max', type=int, default=4,
                        help='Draft tokens per proposal in spec mode (default: 4)')
    parser.add_argument('--spec-bin', type=str, default=None,
                        help='llama-server binary with draft-dspark support (default: DSPARK_SPEC_BIN or LM Studio backend)')
    parser.add_argument('--llama-server', action='store_true',
                        help='Serve the target via a llama-server binary instead of llama-cpp-python '
                             '(handles Qwen3 thinking templates; also via DSPARK_LLAMA_SERVER=1)')

    args = parser.parse_args()

    def resolve(name: str, kind: str) -> str:
        if os.path.isfile(name):
            return os.path.abspath(name)
        path = resolve_gguf(name)
        if not path:
            print(f"ERROR: Could not resolve {kind} model '{name}'. "
                  f"Is it installed via `ollama pull {name.split(':')[0]}`?", file=sys.stderr)
            sys.exit(1)
        return path

    target_path = resolve(args.target, 'target')
    # Draft model is only needed for --draft-mode model; don't require it otherwise.
    draft_path: Optional[str] = None
    if args.draft_mode == 'model':
        draft_path = resolve(args.draft, 'draft')

    n_threads = args.n_threads if args.n_threads > 0 else None
    tensor_split = None
    if args.tensor_split:
        try:
            tensor_split = [float(x) for x in args.tensor_split.split(',')]
        except ValueError:
            print('ERROR: --tensor-split must be comma-separated floats, e.g. 0.5,0.5', file=sys.stderr)
            sys.exit(1)

    # Resolve the target's GPU layer count. 'auto' (new default) fits the model
    # to the visible VRAM so the server boots on any machine; '-1'/N pass through.
    n_gpu_layers = resolve_n_gpu_layers(args.n_gpu_layers, target_path)
    use_llama_server = args.llama_server or os.environ.get('DSPARK_LLAMA_SERVER') == '1'

    # A tensor split that references GPUs that don't exist (the old 3-way
    # default on a single-GPU box) makes llama.cpp fail the whole load — drop it.
    n_gpus = gpu_count()
    if tensor_split and (n_gpus == 0 or len(tensor_split) > n_gpus):
        print(f'[DSpark] Dropping tensor-split {tensor_split}: only {n_gpus} GPU(s) detected', flush=True)
        tensor_split = None
    elif tensor_split and n_gpu_layers == 0:
        print(f'[DSpark] Dropping tensor-split {tensor_split}: target runs on CPU', flush=True)
        tensor_split = None

    # Spec mode: resolve the DRAFT's GPU layers against the remaining VRAM
    # (reserve what the target already claimed), independent of the llama-cpp
    # draft path.
    draft_gpu_layers = args.draft_gpu_layers
    if args.spec_draft:
        if not os.path.isfile(args.spec_draft):
            print(f'ERROR: --spec-draft GGUF not found: {args.spec_draft}', file=sys.stderr)
            sys.exit(1)
        try:
            target_size_mb = os.path.getsize(target_path) / 1048576.0
        except OSError:
            target_size_mb = 0.0
        draft_gpu_layers = resolve_n_gpu_layers('auto', args.spec_draft, reserve_mb=int(target_size_mb) + 1024)

    app = create_app(
        target_path=target_path,
        draft_path=draft_path,
        n_gpu_layers=n_gpu_layers,
        n_ctx=args.n_ctx,
        n_threads=n_threads,
        tensor_split=tensor_split,
        split_mode=args.split_mode,
        n_batch=args.n_batch,
        model_id=args.model_id,
        draft_gpu_layers=draft_gpu_layers,
        draft_num_pred_tokens=args.draft_num_pred_tokens,
        draft_mode=args.draft_mode,
        flash_attn=args.flash_attn,
        spec_draft_path=args.spec_draft,
        spec_n_max=args.spec_n_max,
        spec_bin=args.spec_bin,
        spec_port=args.port,
        llama_server=use_llama_server,
    )

    # Graceful shutdown
    def _handle_signal(signum, frame):
        print('\n[DSpark] Shutting down...', flush=True)
        global _SPEC_CHILD
        if _SPEC_CHILD is not None and _SPEC_CHILD.poll() is None:
            try:
                os.killpg(os.getpgid(_SPEC_CHILD.pid), signal.SIGTERM)
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    uvicorn.run(app, host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
