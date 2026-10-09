# scripts/hf-hub — what the Hugging Face model repo must contain

The tuned weights live on Hugging Face, not in this repo and not as a GitHub
Release asset (a 9 GB GGUF is over GitHub's 2 GB per-asset cap). These are the
files that make that repository self-describing, so `ollama pull hf.co/…` works
with no script:

| File | Purpose |
|---|---|
| `template` | `{{ .Prompt }}` — the bare template VACA R20 was trained on. Without it Ollama picks the GGUF's built-in chat template and the model degrades. |
| `params` | Sampling settings, mirroring `scripts/Modelfile.vaca-r20-q4`. |
| `README.md` | The model card. |

`template` has **no trailing newline** on purpose: a newline is a real character
in the prompt this model was trained on.

These are copies of what was uploaded, kept here so the recipe is reviewable in
the same place as the app. They are what `scripts/install-model.sh --tuned`
reproduces locally through a `Modelfile`, for people who would rather not pull
through Ollama's Hugging Face integration.

## Publishing (maintainer)

```bash
hf auth login                                  # write token, from hf.co/settings/tokens

hf repo create demorolled/veronica-r20-q4-GGUF --repo-type model   # first time only

# the weights (~9 GB; resumable, it is an upload of an existing file)
hf upload demorolled/veronica-r20-q4-GGUF \
  models/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf \
  Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf

# the three recipe files
hf upload demorolled/veronica-r20-q4-GGUF scripts/hf-hub/template  template
hf upload demorolled/veronica-r20-q4-GGUF scripts/hf-hub/params    params
hf upload demorolled/veronica-r20-q4-GGUF scripts/hf-hub/README.md README.md
```

Then set `TUNED_GGUF_URL` in `scripts/install-model.sh` and fill the same URL
into `README.md` and `RELEASE_NOTES.md`, so `install-model.sh --tuned` works
with no flags.

Verify before announcing anything:

```bash
hf download demorolled/veronica-r20-q4-GGUF template   # reachable anonymously
ollama run hf.co/demorolled/veronica-r20-q4-GGUF        # the one-command path
./scripts/install-model.sh --tuned --dry-run            # the scripted path
```
