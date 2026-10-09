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

hf repo create StevenWoods/veronica-r20-q4-GGUF --repo-type model   # first time only

# the weights (~9 GB; resumable, it is an upload of an existing file)
hf upload StevenWoods/veronica-r20-q4-GGUF \
  models/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf \
  Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf

# the three recipe files
hf upload StevenWoods/veronica-r20-q4-GGUF scripts/hf-hub/template  template
hf upload StevenWoods/veronica-r20-q4-GGUF scripts/hf-hub/params    params
hf upload StevenWoods/veronica-r20-q4-GGUF scripts/hf-hub/README.md README.md
```

The repository must be **public**. `hf.co` pulls and the `curl` in
`install-model.sh` are both anonymous, so a private repo makes every documented
install path fail with a 401.

The URLs are already wired up: `TUNED_GGUF_URL` in `scripts/install-model.sh`,
the model section in `README.md`, and the link in `RELEASE_NOTES.md` all point
at `StevenWoods/veronica-r20-q4-GGUF`. Nothing else needs editing — but until the
upload actually happens, those three files point at nothing.

Verify before announcing anything:

```bash
# must be HTTP 200 with no token in the environment
curl -sSI https://huggingface.co/StevenWoods/veronica-r20-q4-GGUF/resolve/main/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf \
  | head -1

ollama run hf.co/StevenWoods/veronica-r20-q4-GGUF        # the one-command path
./scripts/install-model.sh --tuned --dry-run            # the scripted path
```

A 401 above means private or absent — from outside, the two are indistinguishable,
so check with `hf auth whoami` while logged in rather than guessing.

The weights' SHA-256 is `27b12082b0ec01e31ec0161d75131ed32278fbbda643c433ab5f12bc3dcac4fc`
(8,988,110,688 bytes). Confirm the uploaded file matches before publishing the
card, or the verification instructions it gives are wrong.
