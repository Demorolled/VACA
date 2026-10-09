#!/usr/bin/env python3
"""
train_r29_kaggle.py — VACA R29 QLoRA continue on Kaggle (14B, 26h budget)
==========================================================================
Continue-training the CURRENT VACA 14B (the R28 adapter, on top of
BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored) for a TOTAL of 26h across
Kaggle session segments, on a SINGLE 16 GB GPU (T4/P100).

  * Continuation : loads the R28 adapter (dataset vaca-r29-start) — or the
                   latest in-training snapshot (dataset vaca-r29-resume, kept
                   current by the remote monitor between segments). The LoRA is
                   loaded trainable (is_trainable=True) and trained onward.
  * 26h budget   : resume.json records cumulative training hours; each kernel
                   run trains up to min(SESSION_MAX_H=11.3h, remaining) then
                   saves final/ + resume.json and exits cleanly (COMPLETE).
                   Kaggle's 12h session cap never kills us mid-checkpoint.
  * Crash-safe   : save_steps=50 (~2.5 min) with Trainer checkpoints; the
                   monitor downloads the output after ANY end state, uploads
                   the newest checkpoint to vaca-r29-resume, and re-pushes —
                   so even a hard kill loses at most a few minutes.
  * GPU checks   : prints nvidia-smi + torch device at start; every heartbeat
                   carries the GPU name so the monitor can spot mid-run GPU
                   switches (T4↔P100 both fp16 — safe, just slower on P100).

Same proven R22/R23 engine as train_r28_kaggle.py: 4-bit QLoRA r8/α16,
LR 5e-5, fp16 (NEVER bf16 — P100/T4 lack bf16 units), seq 1280, batch 1 ×
accum 4, gradient checkpointing, offload_folder for the 2× load spike, masked
chat-template labels.

Output: /kaggle/working/round29-kaggle/{final/, checkpoint-*/, resume.json, progress.json}
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "bitsandbytes"],
               check=False)

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)
from peft import PeftModel, prepare_model_for_kbit_training

MODEL_NAME = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
SYSTEM_PROMPT = (
    "You are a Visual AI Architect assistant specializing in GUI development. "
    "You build complete web applications, explain UI patterns, generate code, "
    "and help with frontend development."
)
MAX_SEQ = 1024                 # v6 hardening: smaller activations on T4
TOTAL_BUDGET_H = 26.0          # exactly what we sell to the user
SESSION_MAX_H = 11.3           # stay well under Kaggle's 12h session cap
MIN_S_PER_STEP = 2.0           # gross upper-bound estimate for max_steps
OUT_DIR = Path("/kaggle/working/round29-kaggle")
RESUME_JSON = OUT_DIR / "resume.json"
PROGRESS = OUT_DIR / "progress.json"


def phase(msg):
    print(f"PHASE {msg}", flush=True)


def heartbeat(**kw):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}
    PROGRESS.write_text(json.dumps(data))
    print("HEARTBEAT " + json.dumps(data), flush=True)


class HeartbeatCallback(TrainerCallback):
    def __init__(self, every=5):
        self.every = every
        self.t0 = None
        self.last_step = 0
        self.s_per_step = None

    def on_train_begin(self, args, state, control, **kw):
        self.t0 = time.time()

    def on_log(self, args, state, control, logs=None, **kw):
        if state.global_step % self.every == 0:
            if self.t0 is None:
                self.t0 = time.time()
            dt = time.time() - self.t0
            if state.global_step > self.last_step:
                self.s_per_step = dt / max(state.global_step, 1)
                self.last_step = state.global_step
            heartbeat(step=state.global_step, status="training",
                      loss=round(logs.get("loss"), 4) if logs else None,
                      epoch=round(state.epoch, 3) if state.epoch is not None else None,
                      gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                      s_per_step=round(self.s_per_step, 3) if self.s_per_step else None,
                      seg_h=round((time.time() - self.t0) / 3600, 3),
                      remaining_h=round(self.remaining_h, 3) if hasattr(self, "remaining_h") else None)


class TimeBudgetCallback(TrainerCallback):
    """Stop mid-epoch when the segment (or the total 26h) budget is reached."""
    def __init__(self, budget_h, elapsed_h, total_h):
        self.budget_h = budget_h
        self.elapsed_h = elapsed_h
        self.total_h = total_h
        self.t0 = time.time()
        self.stop_at = min(budget_h, total_h - elapsed_h)
        self.remaining_h = self.stop_at
        self.stopped = False

    def on_step_end(self, args, state, control, **kw):
        seg = (time.time() - self.t0) / 3600
        self.remaining_h = self.stop_at - seg
        if seg >= self.stop_at and state.global_step > 0:
            control.should_training_stop = True
            self.stopped = True

    def on_log(self, args, state, control, logs=None, **kw):
        self.remaining_h = self.stop_at - (time.time() - self.t0) / 3600


TRAIN_T0 = {"t0": None}   # shared by the save callback (trainer-start wall clock)


class SaveResumeCallback(TrainerCallback):
    """Refresh resume.json next to every trainer checkpoint so any end state
    (even a crash mid-checkpoint) carries usable continuation metadata."""
    def __init__(self, elapsed_h, steps_done):
        self.elapsed_h = elapsed_h
        self.steps_done = steps_done

    def on_train_begin(self, args, state, control, **kw):
        TRAIN_T0["t0"] = time.time()

    def on_save(self, args, state, control, **kw):
        seg_h = None
        if TRAIN_T0["t0"]:
            seg_h = (time.time() - TRAIN_T0["t0"]) / 3600
        write_resume(elapsed_h=self.elapsed_h, seg_h=seg_h,
                     steps_total=self.steps_done + state.global_step,
                     gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")


def write_resume(elapsed_h, seg_h=None, steps_total=None, gpu=None, s_per_step=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "round": 29,
        "elapsed_h": round(elapsed_h + (seg_h or 0.0), 3) if seg_h else round(elapsed_h, 3),
        "seg_h": round(seg_h, 3) if seg_h else None,
        "steps_total": int(steps_total or 0),
        "gpu": gpu,
        "s_per_step": round(s_per_step, 3) if s_per_step else None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    RESUME_JSON.write_text(json.dumps(data, indent=1))
    return data


def find_dirs():
    """Locate the three datasets under /kaggle/input by marker file."""
    found = {"corpus": None, "start": None, "resume": None}
    inp = Path("/kaggle/input")
    if inp.exists():
        for d in sorted(inp.rglob("*")):
            if not d.is_dir():
                continue
            if found["corpus"] is None and (d / "corpus.json").exists() and (d / "train.jsonl").exists():
                found["corpus"] = d
            elif found["start"] is None and (d / "start.json").exists() and (d / "adapter_config.json").exists():
                found["start"] = d
            elif found["resume"] is None and (d / "resume.json").exists() and d is not found["corpus"]:
                found["resume"] = d
    return found


def ids_of(x):
    if hasattr(x, "ids"):
        return list(x.ids if isinstance(x.ids, list) else x.ids.tolist())
    if isinstance(x, dict):
        return list(x.get("input_ids"))
    return list(x)


def main():
    print("=" * 60)
    print("  VACA R29 — 14B QLoRA CONTINUE on Kaggle (26h budget)")
    print(f"  model : {MODEL_NAME}")
    dirs = find_dirs()
    print(f"  corpus: {dirs['corpus']}")
    print(f"  start : {dirs['start']}")
    print(f"  resume: {dirs['resume']}")
    gpus = torch.cuda.device_count()
    for i in range(gpus):
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    print("=" * 60)

    train_path = dirs["corpus"] / "train.jsonl" if dirs["corpus"] else None
    if train_path is None or not train_path.exists():
        print("❌ corpus dataset not found — /kaggle/input contents:", file=sys.stderr)
        inp = Path("/kaggle/input")
        if inp.exists():
            for d in sorted(inp.iterdir()):
                files = [f.name for f in d.iterdir()][:10] if d.is_dir() else []
                print(f"    {d.name}/ → {files}", file=sys.stderr)
        sys.exit(1)

    # ── Continuation state (elapsed hours + starting adapter) ─────────────
    elapsed_h = 0.0
    steps_done = 0
    resume_point = None        # trainer checkpoint path (exact step resume)
    adapter_source = dirs["start"]   # R28 adapter by default
    if dirs["resume"] is not None:
        rj = dirs["resume"] / "resume.json"
        try:
            rj_data = json.loads(rj.read_text())
            elapsed_h = float(rj_data.get("elapsed_h", 0.0))
            steps_done = int(rj_data.get("steps_total", 0))
        except Exception:
            elapsed_h = 0.0
        ckpts = sorted([d for d in dirs["resume"].glob("checkpoint-*")
                        if (d / "adapter_config.json").exists()],
                       key=lambda d: int(d.name.split("-")[-1]))
        if ckpts:
            resume_point = str(ckpts[-1])      # Trainer step-resume
            adapter_source = ckpts[-1]
        elif (dirs["resume"] / "adapter_config.json").exists():
            adapter_source = dirs["resume"]    # adapter-only resume
    if elapsed_h >= TOTAL_BUDGET_H:
        print(f"✅ 26h budget already complete ({elapsed_h}h) — nothing to train.")
        heartbeat(status="done_already", elapsed_h=elapsed_h)
        sys.exit(0)

    remaining = TOTAL_BUDGET_H - elapsed_h
    seg_budget_h = min(SESSION_MAX_H, remaining)
    print(f"  elapsed_h = {elapsed_h:.2f} | remaining = {remaining:.2f} | segment budget = {seg_budget_h:.2f}h")

    heartbeat(status="loading_model", elapsed_h=elapsed_h, resume_point=resume_point)

    # ── 4-bit base (proven R28 load path: fp16, offload_folder, RAM budget) ─
    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    print("Loading 14B (4-bit)…")
    os.makedirs("/tmp/offload", exist_ok=True)
    # v6 hardening: low_cpu_mem_usage kills the ~2x fp16-shard RAM spike during
    # load; GPU-only max_memory (no cpu budget) keeps the quantized weights on
    # the card instead of staging them in the VM's small RAM. The ~8min hard
    # kills on v2/v4 (empty output zip = cgroup kill, no python traceback)
    # pointed at RAM pressure at train-start, so bias everything to VRAM/RAM.
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, quantization_config=bnb, device_map="auto",
        max_memory={0: "14GB"},
        offload_folder="/tmp/offload", offload_state_dict=False,
        low_cpu_mem_usage=True,
        trust_remote_code=True, torch_dtype=torch.float16,
    )
    torch.cuda.empty_cache()
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    print(f"Attaching continue adapter from {adapter_source} (trainable)…")
    model = PeftModel.from_pretrained(model, adapter_source, is_trainable=True)
    model.gradient_checkpointing_enable()
    t, total = model.get_nb_trainable_parameters()
    print(f"Trainable: {t:,} / {total:,} ({100 * t / total:.2f}%)")
    torch.cuda.empty_cache()
    heartbeat(status="adapter_attached", elapsed_h=elapsed_h, adapter=str(adapter_source))

    # ── Dataset (masked chat template — R28-proven) ───────────────────────
    records = []
    for line in train_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        instruction = rec.get("instruction", "")
        inp = rec.get("input", "") or ""
        output = rec.get("output", "")
        if not output or len(output.strip()) < 10:
            continue
        user_text = f"{instruction}\n\n{inp}".strip() if inp else instruction
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": output.strip()},
        ]
        prompt_ids = ids_of(tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True))
        full_ids = ids_of(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False))
        full_ids = full_ids[:MAX_SEQ]
        m = min(len(prompt_ids), len(full_ids))
        records.append({"input_ids": full_ids,
                        "labels": [-100] * m + full_ids[m:]})
    if not records:
        print("❌ no valid rows", file=sys.stderr)
        sys.exit(1)

    from datasets import Dataset as HFDataset
    pad = tokenizer.pad_token_id or tokenizer.eos_token_id or 0
    for r in records:
        n = len(r["input_ids"])
        r["attention_mask"] = [1] * n
        if n < MAX_SEQ:
            r["input_ids"] += [pad] * (MAX_SEQ - n)
            r["labels"] += [-100] * (MAX_SEQ - n)
            r["attention_mask"] += [0] * (MAX_SEQ - n)
    # Kaggle image's datasets lib rejects writer_batch_size on from_list
    # (TypeError, verified 2026-08-31) AND its schema inference dies on the
    # equal-length int lists with 'ArrowTypeError: Expected bytes, got a int'
    # (every run v2–v7 crashed here). Fix: explicit Features so pyarrow never
    # infers — the Sequence(int32) columns handle the padded token ids/labels.
    from datasets import Features, Sequence, Value
    feats = Features({
        "input_ids": Sequence(Value("int32")),
        "labels": Sequence(Value("int32")),
        "attention_mask": Sequence(Value("int32")),
    })
    records = [
        {k: [int(v) for v in rec[k]] for k in ("input_ids", "labels", "attention_mask")}
        for rec in records
    ]
    ds = HFDataset.from_list(records, features=feats)
    print(f"rows: {len(ds)} train")
    phase("dataset-built")
    heartbeat(status="training", step=0, elapsed_h=elapsed_h)

    max_steps = int(seg_budget_h * 3600 / MIN_S_PER_STEP)
    targs = TrainingArguments(
        output_dir=str(OUT_DIR),
        num_train_epochs=50,          # max_steps governs; epochs never bind
        max_steps=max_steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=5e-5,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        weight_decay=0.01,
        bf16=False, fp16=True,
        logging_strategy="steps", logging_steps=5,
        save_strategy="steps", save_steps=50, save_total_limit=3,
        dataloader_num_workers=0,      # v6: no worker forks → no RAM doubling
        remove_unused_columns=False,
        report_to="none",
        gradient_checkpointing=True,
        seed=42,
    )
    cb_heart = HeartbeatCallback(every=5)
    cb_time = TimeBudgetCallback(budget_h=seg_budget_h, elapsed_h=elapsed_h, total_h=TOTAL_BUDGET_H)
    cb_save = SaveResumeCallback(elapsed_h=elapsed_h, steps_done=steps_done)
    phase(f"trainer-init (max_steps={max_steps}, rows={len(ds)})")
    trainer = Trainer(
        model=model, args=targs, train_dataset=ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True,
                                             max_length=MAX_SEQ, return_tensors="pt"),
        callbacks=[cb_heart, cb_time, cb_save],
    )

    t0 = time.time()
    try:
        phase("train-start")
        trainer.train(resume_from_checkpoint=resume_point)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb, flush=True)
        # Persist the traceback INTO the output dir so a crash harvest always
        # yields the real reason (Kaggle's output zip includes /kaggle/working).
        try:
            (OUT_DIR / "crash.log").write_text(tb)
        except Exception:
            pass
        # Still try to persist what we have — a mid-crash resume pack beats nothing.
        try:
            trainer.save_model(OUT_DIR / "crash-save")
            write_resume(elapsed_h=elapsed_h, seg_h=(time.time() - t0) / 3600,
                         steps_total=steps_done + (trainer.state.global_step if trainer.state else 0),
                         gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                         s_per_step=cb_heart.s_per_step)
        except Exception:
            pass
        heartbeat(status="error", elapsed_h=elapsed_h, phase="train")
        sys.exit(1)

    seg_h = (time.time() - t0) / 3600
    final = OUT_DIR / "final"
    trainer.save_model(final)
    try:
        tokenizer.save_pretrained(final)
    except Exception:
        pass
    resume = write_resume(elapsed_h=elapsed_h, seg_h=seg_h,
                          steps_total=steps_done + trainer.state.global_step,
                          gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                          s_per_step=cb_heart.s_per_step)
    heartbeat(status="session_done", remaining_h=max(0.0, TOTAL_BUDGET_H - resume["elapsed_h"]),
              elapsed_h=resume["elapsed_h"], seg_h=round(seg_h, 3))
    print(f"\n✅ segment done: {seg_h:.2f}h this segment → total {resume['elapsed_h']:.2f}h of 26h")
    for f in sorted(OUT_DIR.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(OUT_DIR)} ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()