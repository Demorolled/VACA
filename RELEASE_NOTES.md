# Veronica 1.0.0 — Linux x64 · Windows x64

First public build of Veronica (VACA), the AI code architect: describe an app in
plain English and it builds it.

> **This is a time-limited demo.** It runs normally until **9 December 2026**,
> then refuses to launch. The date is fixed rather than counted per machine, so
> every copy stops on the same day. Nothing is deleted when it expires — see
> "Demo builds" in the README for exactly what it does and does not do.

## Downloads

| File | Use |
|---|---|
| `veronica_1.0.0_amd64.deb` | Ubuntu/Debian system install. `sudo apt install ./veronica_1.0.0_amd64.deb` |
| `Veronica-1.0.0.AppImage` | Portable, no install. Needs `libfuse2`. |
| `Veronica-1.0.0-linux-x64.tar.gz` | Self-contained runtime directory. Extract anywhere and run `linux-unpacked/veronica`. |
| `Veronica-Setup-1.0.0.exe` | Windows x64 installer. Per-user NSIS, no admin prompt, creates shortcuts. Unsigned. |
| `SHA256SUMS` | Checksums for the four files above. |

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
  Q4_K_M**, created in Ollama as `vaca-r20-q4`. It is hosted on Hugging Face, not
  attached here — see **The tuned model** in the README.
- Without a reachable model the UI loads and the app runs, but generation does
  nothing: `/health` reports `llm.up:false`.

## Requirements

- Linux: Ubuntu/Debian x86-64. GTK3, NSS, libsecret and the usual Chromium
  runtime libraries (the `.deb` declares them). Windows: 10/11 x64.
- The Windows installer was cross-built with wine on Linux and its packaged
  payload was verified, but it has **not** been installed and launched on a real
  Windows machine. Expect to shake out first-run issues.
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

## License

Proprietary — all rights reserved. Source is published for reference; that is
not a license to reuse it. Electron, Chromium and the vendored packages keep
their own licenses, and the model carries its own.

---

<!-- TODO(publish): link the Hugging Face GGUF here, and confirm the checksums
     against the assets you actually uploaded. -->
