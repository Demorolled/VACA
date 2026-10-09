# Veronica 1.0.0 — Linux x64

First public build of Veronica (VACA), the AI code architect: describe an app in
plain English and it builds it.

## Downloads

| File | Use |
|---|---|
| `veronica_1.0.0_amd64.deb` | Ubuntu/Debian system install. `sudo apt install ./veronica_1.0.0_amd64.deb` |
| `Veronica-1.0.0.AppImage` | Portable, no install. Needs `libfuse2`. |
| `Veronica-1.0.0-linux-x64.tar.gz` | Self-contained runtime directory. Extract anywhere and run `linux-unpacked/veronica`. |
| `SHA256SUMS` | Checksums for the three files above. |

## You also need the model — it is not in these files

The weights are ~9 GB and are deliberately not bundled. Install them once per
machine, separately:

```bash
./scripts/install-model.sh                    # public qwen2.5-coder:14b
./scripts/install-model.sh --tuned --gguf-url <URL>   # the VACA-tuned Qwen2.5 14B
```

See the README section “The model — downloaded separately”. Briefly:

- **The app ships pinned to `qwen2.5-coder:14b`**, served over the
  OpenAI-compatible API (Ollama by default, `http://127.0.0.1:11434/v1`).
- **This build was developed against a tuned Qwen2.5-Coder-14B-Instruct-Uncensored
  Q4_K_M**, created in Ollama as `vaca-r20-q4`. It is hosted separately — link it
  here before publishing this release.
- Without a reachable model the UI loads and the app runs, but generation does
  nothing: `/health` reports `llm.up:false`.

## Requirements

- Ubuntu/Debian x86-64. GTK3, NSS, libsecret and the usual Chromium runtime
  libraries (the `.deb` declares them).
- No system Node — the bundled backend runs on Electron's own Node.
- A GPU is not required, but a 14B Q4_K_M wants roughly 9–10 GB of VRAM to be
  usable. It will fall back to CPU, slowly.

## Known issues

- **On Ubuntu 24.04+ the app may abort at startup** with
  `The SUID sandbox helper binary was found, but is not configured correctly`.
  Run with `--no-sandbox`, or restore the setuid bit / install the AppArmor
  profile the build ships with — all three fixes are in the README's
  Troubleshooting section. This affects the `.deb`'s menu entry too.
- Unsigned binaries; some systems will warn.
- `chrome-sandbox` in the tarball is not setuid, so `linux-unpacked/veronica`
  needs `--no-sandbox` (or the same fix).

---

**Before publishing this file:** replace the placeholder above with the real
Hugging Face URL for the tuned GGUF, and confirm the checksums against the
uploaded assets.
