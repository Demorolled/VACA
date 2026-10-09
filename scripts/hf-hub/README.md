---
base_model: BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored
library_name: gguf
pipeline_tag: text-generation
language:
  - en
tags:
  - gguf
  - ollama
  - qwen2.5-coder
  - code
  - text-generation
---

# Veronica R20 — Q4_K_M (GGUF)

The model the **Veronica (VACA)** AI code architect was tuned against: an
uncensored Qwen2.5-Coder-14B with the VACA LoRA rounds merged in, quantised to
`Q4_K_M` (~9 GB).

- **Base:** [`BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored`](https://huggingface.co/BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored)
  (itself a fine-tune of `Qwen/Qwen2.5-Coder-14B-Instruct`)
- **Tuning:** VACA LoRA rounds, merged to 16-bit, then quantised to `Q4_K_M`
- **File:** `Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf`
- **App:** <https://github.com/Demorolled/VACA>

## Run it with Ollama

```bash
ollama run hf.co/demorolled/veronica-r20-q4-GGUF
```

That is the whole install. No account, no manual download, no Modelfile step.

## Run it with llama.cpp, LM Studio, or anything else

The repository is a plain GGUF. Download the `.gguf` and load it directly.

## The template matters — do not "fix" it

This fine-tune was trained on **raw prompt text**. It answers best when the
prompt is passed through unmangled, which is why `TEMPLATE {{ .Prompt }}` is the
recipe across every deployed VACA round. Wrapping the prompt in a chat template
(the usual `<|im_start|>…<|im_end|>` framing) puts the model off-distribution
and measurably degrades it.

Two files in this repository carry that recipe for the `hf.co` pull path:

| File | Contents | Why |
|---|---|---|
| `template` | `{{ .Prompt }}` | Overrides the auto-selected chat template Ollama would otherwise take from the GGUF metadata |
| `params` | `num_ctx` 16384, `temperature` 0.7, `top_p` 0.9 | The sampling settings the build was evaluated with |

Do not replace `template` with the model's built-in Qwen chat template. The
publisher of a derivative has to keep **all three** files (`template`, `params`,
and the GGUF) or the runtime silently changes behaviour.

## Hardware

`Q4_K_M` of a 14B is ~9 GB. Roughly 10 GB of VRAM makes it comfortable; it runs
on CPU, slowly. `num_ctx` 16384 raises the KV-cache cost above the default.

## Provenance and licence

- The weights are a **derivative** of the MIT-licensed
  `BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored`; they follow the upstream
  base model's terms.
- The **application** that uses them (Veronica / VACA) is proprietary — see its
  repository. That is separate from these weights.
- No warranty. Check what you need before shipping anything the model generated.
