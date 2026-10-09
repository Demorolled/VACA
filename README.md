# Veronica — AI Code Architect (VACA)

Describe what you want in plain English and it builds the app. Electron desktop
app for Linux x64 (Ubuntu/Debian), bundling its own Node backend — no system
Node install required.

> **Before you publish:** the URLs below assume the repo is
> `demorolled/visual-ai-architect`, which is the value already baked into the
> app's `package.json` and the `.deb` metadata. Change it in one place —
> `scripts/repo-slug.sh` — if the real repo differs, and update the badges below.

---

## Two things are *not* in this repo

| Missing | Where it lives | Why |
|---|---|---|
| The packaged binaries (AppImage, `.deb`, runtime tarball) | **[Releases](../../releases)** | Two of them are past GitHub's 100 MB per-file limit, and build output does not belong in git. |
| The LLM — Qwen2.5 14B, ~9 GB | **Downloaded separately**, once per machine | Tens of GB, separately licensed, and it changes on its own schedule. See [The model](#the-model--downloaded-separately). |

Everything else — the Electron main process, the backend, the frontend, the
knowledge base, the scripts — is committed and readable.

---

## Install

### A. System install (Ubuntu/Debian)

```bash
sudo apt install ./veronica_1.0.0_amd64.deb
veronica
```

### B. Portable AppImage

```bash
chmod +x Veronica-1.0.0.AppImage
./Veronica-1.0.0.AppImage
```

Needs FUSE 2 (`sudo apt install libfuse2` on 22.04+). Without it, AppImage
refuses to start and says so.

### C. Straight from a clone of this repo

```bash
git clone https://github.com/demorolled/visual-ai-architect.git
cd visual-ai-architect
./scripts/fetch-release-assets.sh   # restores the prebuilt runtime from Releases
./scripts/run-from-checkout.sh      # launches it
```

`run-from-checkout.sh` also works without the download: it will install the
payload's dependencies and a matching Electron (~250 MB the first time) and run
the app from the source tree.

### First run

The app copies its payload into your user data dir and runs the backend from
there, because the install location is read-only:

```
~/.config/Veronica/runtime   ← working copy (data/, projects/, users/)
~/.config/Veronica/logs      ← main.log, backend.log
~/.config/Veronica/settings.json
```

Nothing is written back into the repo or into `/opt/Veronica`.

---

## The model — downloaded separately

Veronica is pinned to **one** Qwen2.5 14B model and talks to it over the
OpenAI-compatible API. Ollama is the expected host. Install the model with:

```bash
./scripts/install-model.sh            # the default, public model (see below)
```

That runs `ollama pull qwen2.5-coder:14b` (~9 GB), checks the server lists it,
then asks it to generate — because a model can be listed and still be broken.

### The tuned model

This build was developed against a **fine-tune**, not the stock model:

> Qwen2.5-Coder-14B-Instruct-Uncensored + VACA LoRA rounds, merged, quantised to
> Q4_K_M. ~9.0 GB. Built by `scripts/auto-deploy-r*.sh` / `quantize-r40-q4.sh`.

It is not hosted by this repo, so it has to come from somewhere you control —
Hugging Face is the normal place for a file this size (a GitHub Release caps at
2 GB per asset, so a 9 GB GGUF will not fit there):

```bash
./scripts/install-model.sh --tuned \
  --gguf-url https://huggingface.co/<your-org>/<your-repo>/resolve/main/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf
```

or, if the GGUF is already on disk:

```bash
./scripts/install-model.sh --tuned --gguf-path /mnt/models/vaca-r20.Q4_K_M.gguf
```

Either way the script writes a `Modelfile` and runs `ollama create vaca-r20-q4`.
The recipe is short enough to read: [`scripts/Modelfile.vaca-r20-q4`](scripts/Modelfile.vaca-r20-q4).

```dockerfile
FROM /abs/path/to/Qwen2.5-Coder-14B-Instruct-Uncensored.R20.Q4_K_M.gguf
TEMPLATE {{ .Prompt }}
PARAMETER num_ctx 16384
PARAMETER temperature 0.7
PARAMETER top_p 0.9
```

Two things about that are load-bearing, not decorative:

- **`FROM` must be an absolute path.** Ollama parses a relative one as a *model
  reference* and fails with `400 Bad Request: invalid model name`, which reads
  like a bad model name rather than a bad path.
- **`TEMPLATE {{ .Prompt }}` stays.** The tune was trained on bare prompt text;
  wrapping it in the default chat template moves it off-distribution. Every
  deployed VACA round carries this exact line.

### Point the app at it

Settings (`Ctrl+,`) ▸ **Model**:

```
LLM endpoint : http://127.0.0.1:11434/v1
Model        : qwen2.5-coder:14b      or  vaca-r20-q4  for the tune
```

then **Save & restart**. The shipped default is `qwen2.5-coder:14b`, so if you
installed the tune you have to change the Model field — otherwise the app asks
the server for a model that is not there.

A model on another machine is fine: put its URL in the endpoint field, e.g.
`http://192.168.1.234:11434/v1`. The same model has to exist *there*.

**If generation does not work** but the UI loads, the model is the reason:
`/health` reports `llm.up:false`.

---

## Repository layout

```
.
├── .gitignore / .gitattributes    what stays out of git, and how text is normalized
├── README.md
├── RELEASE_NOTES.md               notes for the release you are about to cut
├── scripts/                       ← the repo's own tooling (not the app's)
│   ├── install-model.sh           fetch the LLM, separately
│   ├── Modelfile.vaca-r20-q4      the tuned model's Ollama recipe
│   ├── build-release-assets.sh    maintainer: stage + hash the release assets
│   ├── fetch-release-assets.sh    restore the prebuilt runtime from Releases
│   ├── run-from-checkout.sh       run the app from a clone
│   ├── repo-slug.sh               which GitHub repo is this (for release URLs)
│   └── dspark-target.env.example  copy to dspark-target.env if you run dspark
└── linux-unpacked/
    └── resources/app/
        ├── main.js                Electron main process
        ├── preload.js             the only IPC bridge (contextIsolation on)
        ├── settings.html          the Settings window
        ├── package.json           app metadata
        └── payload/
            ├── backend/           the Node backend (dist/ = built JS)
            ├── frontend/          the UI the backend serves
            ├── apps/              bundled example apps
            ├── knowledge/         reference material for generation
            ├── data/              seeds: library, code-bible, soul.json
            ├── projects/          example outputs
            ├── scripts/           the app's own (large, legacy) script collection
            └── package.json       runtime deps — installed, not committed
```

Not tracked, on purpose (see [`.gitignore`](.gitignore)): `node_modules/`, the
Electron runtime inside `linux-unpacked/`, `*.AppImage`, `*.deb`, `*.tar.gz`,
logs, and machine-local `*.env` files.

---

## Scripts

| Script | What it does |
|---|---|
| `scripts/install-model.sh` | Pulls or creates the model, then verifies it actually generates. The only step that is not part of the app. |
| `scripts/run-from-checkout.sh` | Runs the app from a clone. Uses the prebuilt runtime if present, otherwise installs deps + Electron. Handles the Chromium sandbox. |
| `scripts/fetch-release-assets.sh` | Downloads release assets and verifies them against `SHA256SUMS`; extracts the runtime tarball over the checkout. |
| `scripts/build-release-assets.sh` | Maintainer: stages the AppImage, `.deb` and runtime tarball into `dist/`, writes `SHA256SUMS`, prints the `gh release create` line. |
| `scripts/repo-slug.sh` | Shared helper: resolves `owner/repo` from `$VACA_REPO`, then the `origin` remote, then the default. |

Every script takes `-h`. `install-model.sh`, `build-release-assets.sh` and
`fetch-release-assets.sh` also take `--dry-run` or `--list` where that makes
sense, so you can look before you leap.

---

## Cutting a release

```bash
./scripts/install-model.sh --tuned --gguf-url <HF URL>   # confirm the model story
./scripts/build-release-assets.sh                        # → dist/ + SHA256SUMS
gh release create v1.0.0 dist/* --title "Veronica 1.0.0" --notes-file RELEASE_NOTES.md
```

`build-release-assets.sh` prints the exact command with the right file list. The
tarball it produces has `linux-unpacked/` as its top-level entry, which is what
makes `fetch-release-assets.sh` able to extract it over a clone.

The model is **never** a release asset — a 9 GB GGUF cannot be one. Link it from
the release notes instead.

---

## Troubleshooting

**`The SUID sandbox helper binary was found, but is not configured correctly`**

Electron aborts on start. The packaged `chrome-sandbox` ships mode `755`, and
Ubuntu 24.04+ sets `kernel.apparmor_restrict_unprivileged_userns=1`, so the user
namespace fallback is closed too. Pick one:

```bash
# 1. run without the Chromium sandbox (simplest)
./linux-unpacked/veronica --no-sandbox
./Veronica-1.0.0.AppImage --no-sandbox

# 2. give the helper its setuid bit back (keeps the sandbox)
sudo chown root:root /opt/Veronica/chrome-sandbox
sudo chmod 4755 /opt/Veronica/chrome-sandbox

# 3. install the AppArmor profile the build already ships
sudo cp /opt/Veronica/resources/apparmor-profile /etc/apparmor.d/veronica
sudo apparmor_parser -r /etc/apparmor.d/veronica
```

The `.deb`'s menu entry is `Exec=/opt/Veronica/veronica %U` with no
`--no-sandbox`, so on 24.04+ it needs option 2 or 3 above to launch from the
menu, or:

```bash
sudo sed -i 's|^Exec=/opt/Veronica/veronica %U|Exec=/opt/Veronica/veronica --no-sandbox %U|' \
  /usr/share/applications/veronica.desktop
```

`scripts/run-from-checkout.sh` detects this case and adds `--no-sandbox` itself.

**`dlopen(): error loading libfuse.so.2`** — the AppImage needs FUSE 2:
`sudo apt install libfuse2`. Or use the `.deb`, or run the extracted directory.

**The UI loads but nothing generates** — check `/health`; `llm.up:false` means no
reachable model. See [The model](#the-model--downloaded-separately).

**`veronica` is not found after `apt install`** — the binary is
`/opt/Veronica/veronica`; the `.deb` puts a symlink on your `PATH`.

---

## Known rough edges

- **Unsigned build.** No code-signing certificate; some systems will warn.
- **`payload/scripts/` still carries workstation-specific junk** — `.desktop`
  files and `dspark-target.env` referring to directories under
  `/home/<user>/Desktop/visual-ai-architect`, which exist on exactly one
  machine. A few hundred scripts from the training rounds are in there too.
  Harmless at runtime, noise for a reader.
- **`data/` and `projects/` are seeds, not a clean slate.** They contain the
  author's accumulated library, designs and example outputs.
- **`payload/dist` is built output**, committed because this repo is a
  distribution tree rather than the app's source repo. There is no build config
  in here — Electron + `electron-builder` ran elsewhere.

## Metadata

- `package.json` / `.deb`: `author`, `homepage` and `maintainer` are placeholders.
- **License: `UNLICENSED`.** No license file is included, so the default
  "all rights reserved" applies until one is added. Add a `LICENSE` before
  inviting contributions.
- Built with Electron 44, packaged with electron-builder 26.
