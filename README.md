# Veronica — AI Code Architect (VACA)

[![Release](https://img.shields.io/github/v/release/demorolled/vaca?label=release&sort=semver)](https://github.com/demorolled/vaca/releases)
[![Platform](https://img.shields.io/badge/platform-linux--x64-blue)](#install)
[![Electron](https://img.shields.io/badge/electron-44-47848f)](https://www.electronjs.org/)
[![License](https://img.shields.io/badge/license-proprietary-red)](#license)

Describe what you want in plain English and it builds the app. Electron desktop
app for Linux x64 (Ubuntu/Debian) and Windows x64, bundling its own Node backend
— no system Node install required.

> **Status: 1.0.0, Linux x64 and Windows x64.** Prebuilt binaries live on the
> [releases page](https://github.com/demorolled/vaca/releases); the model is
> installed separately (see below).

> **⚠ This is a time-limited demo.** These builds run normally until
> **9 December 2026**, then refuse to launch. The date is fixed, not counted per
> machine — every copy stops on the same day however late it was installed.
> Nothing is deleted when it expires. See [Demo builds](#demo-builds).

---

## Two things are *not* in this repo

| Missing | Where it lives | Why |
|---|---|---|
| The packaged binaries (AppImage, `.deb`, runtime tarball, Windows installer) | **[Releases](../../releases)** | Most are past GitHub's 100 MB per-file limit, and build output does not belong in git. |
| The LLM — Qwen2.5 14B, ~9 GB | **Downloaded separately**, once per machine | Tens of GB, separately licensed, and it changes on its own schedule. See [The model](#the-model--downloaded-separately). |

Everything else — the Electron main process, the backend, the frontend, the
knowledge base, the scripts — is committed and readable.

---

## Demo builds

Both installers (Linux and Windows) are the same demo: full functionality until
**2026-12-09**, then a dialog and exit.

The whole mechanism is 12 lines in `linux-unpacked/resources/app/main.js`:

```js
const DEMO = true;
const DEMO_EXPIRES = '2026-12-09';
```

At startup, before any staging or backend launch, an expired copy shows
*"This demo copy of Veronica has expired"* with the path to the user's data and
then quits. `DEMO_EXPIRES` is the last day it runs, compared against the local
clock, so the 9th itself still works.

What it deliberately does **not** do:

- **No phone-home.** Nothing contacts a licence server, and no network call is
  made to check the date — the build works offline forever.
- **No telemetry and no fingerprinting.** It never records who installed it,
  where, or how often.
- **No deletion.** Expiry removes nothing: projects, settings and logs stay put.
- **No hidden state.** The only thing written is a line in the app's own
  `main.log`.

The trade-off, stated plainly: because there is no stored state, the check
**trusts the machine's clock**. Winding the system date back keeps the demo
running. A build that resists that needs to remember a "highest date ever seen"
and is a deliberate next step, not an oversight.

To build without the gate, set `DEMO = false` (the settings window then reads
"Licensed build"), or move `DEMO_EXPIRES` forward. The Windows build is produced
from the same source, so it carries the same constants.

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

### C. Windows installer

```powershell
.\Veronica-Setup-1.0.0.exe
```

A per-user NSIS install (no admin prompt) that creates Start Menu and desktop
shortcuts. The installer is unsigned, so SmartScreen will warn on first run.

> **Not verified on real Windows.** This installer was cross-built on Linux with
> wine, and everything below was checked against its packaged payload — same
> `main.js`, same demo deadline, same `payload/` — but it has not been
> installed and launched on an actual Windows machine. Treat the first Windows
> run as a test.

### D. Straight from a clone of this repo

```bash
git clone https://github.com/demorolled/vaca.git
cd vaca
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

It is hosted on **Hugging Face**, not here — a GitHub Release caps at 2 GB per
asset, so a 9 GB GGUF cannot be one, and shipping weights inside a git repo is
not a thing anyone should do:

**<https://huggingface.co/demorolled/veronica-r20-q4-GGUF>**

That repository carries the `template` and `params` files alongside the weights,
so Ollama can pull it directly — no download step first, and no Modelfile to
write:

```bash
ollama run hf.co/demorolled/veronica-r20-q4-GGUF
```

If you would rather not use Ollama's Hugging Face integration, the scripted path
reproduces the same model locally. `TUNED_GGUF_URL` near the top of
`scripts/install-model.sh` already points at that file, so the bare form works:

```bash
./scripts/install-model.sh --tuned
```

You can also point it at a copy you already have — downloaded by hand, mirrored
internally, or rebuilt from the merged LoRA yourself:

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
| `scripts/build-release-assets.sh` | Maintainer: stages the AppImage, `.deb`, runtime tarball and (with `--windows`) the Windows installer into `dist/`, writes `SHA256SUMS` over everything it finds, prints the `gh release create` line. |
| `scripts/repo-slug.sh` | Shared helper: resolves `owner/repo` from `$VACA_REPO`, then the `origin` remote, then the default. |

Every script takes `-h`. `install-model.sh` takes `--dry-run` and
`fetch-release-assets.sh` takes `--list`, so you can look before you leap.
`build-release-assets.sh` never uploads anything — it stages what it finds and
prints the `gh release create` command for you to run.

`scripts/hf-hub/` is not a script. It holds the files that are uploaded to the
model's Hugging Face repository — the `template` and `params` that make
`ollama run hf.co/…` work, and the model card — so the model's recipe is
reviewable in the same place as the app. See
[`scripts/hf-hub/PUBLISH.md`](scripts/hf-hub/PUBLISH.md).

---

## Cutting a release

```bash
./scripts/install-model.sh --tuned --gguf-url <HF URL>   # confirm the model story
./scripts/build-release-assets.sh \
  --windows ~/path/to/Veronica-Setup-1.0.0.exe           # → dist/ + SHA256SUMS
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
  `/home/<user>/Desktop/…` that exist on exactly one machine. A few hundred
  scripts from the training rounds are in there too. Harmless at runtime, noise
  for a reader.
- **`data/` and `projects/` are seeds, not a clean slate.** They contain the
  author's accumulated library, designs and example outputs.
- **The payload carries some build-tool noise.** `payload/scripts/dspark.pid`
  and `.terminal-speak-seen.json` are machine state that churns on every
  rebuild, and `payload/scripts/batch-results/` is captured output from the
  language-matrix harness. Harmless, but they make rebuild diffs noisier than
  the actual code change.
- **`payload/package-lock.json` is absent from the packaged tree**, although it
  is present in the source payload. `electron-builder` strips it by default. The
  app does not need it; only a manual `npm install` inside the payload would.
- **`payload/dist` is built output**, committed because this repo is a
  distribution tree rather than the app's source repo. There is no build config
  in here — Electron + `electron-builder` ran elsewhere.

## License

**Proprietary — all rights reserved.** There is deliberately no `LICENSE` file,
and the app's `package.json` says `UNLICENSED`. Publishing the source is not a
grant: no copying, modification, redistribution or commercial use without
written permission. Open an issue if you want to talk about terms.

This does **not** change the terms of anything bundled with it:

- **Electron, Chromium and the vendored Node packages** keep their own licenses
  (MIT and friends). Their notices ship inside the app.
- **The model weights** are a separate download under their own terms — the
  upstream base is `BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored`. Check
  those before you ship anything the model generated.

## Metadata

- Author: `demorolled`.
- Built with Electron 44, packaged with electron-builder 26.
- Canonical repo: <https://github.com/demorolled/vaca>. The release helper
  scripts resolve it from `scripts/repo-slug.sh`, or from your `origin` remote
  if you are working in a fork.
