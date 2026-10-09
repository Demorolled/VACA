#!/usr/bin/env python3
"""
Convert Colab training-notebook cells that run `!python train_round1.py …` with
UN-INTERPOLATED `{PLACEHOLDER}` args into Python cells that build the command
from the notebook's config variables (defined in the "EDIT THIS CELL" step) and
run it via subprocess.

Why: Colab `!`-cells are shell — `{ROUNDS}` etc. are never expanded, so those
cells were broken AND failed `scripts/validate-cloud-notebooks.py` (which treats
any {UPPERCASE} placeholder in a shell cell as a hard error), which red-gates
`npm run build` via scripts/check-training.sh. A Python cell with an f-string /
str() interpolation is the validator-sanctioned fix and makes the cells runnable
as the author intended (MODE/ROUNDS/EPOCHS/LR driven).

Idempotent: cells already converted (they contain "subprocess.run") are skipped.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NOTEBOOKS = [
    "training/cloud/colab/train_vaca_colab.ipynb",
    "training/cloud/colab/train_vaca_colab_round2.ipynb",
    "training/cloud/colab/train_vaca_colab_rounds34.ipynb",
    "training/cloud/colab/train_round5_blueprints_q4.ipynb",
]

# {PLACEHOLDER} -> Python expression that yields the CLI token (string or None).
VAR_MAP = {
    "ROUNDS": "str(ROUNDS)",
    "FIRST_LR": "str(FIRST_LR)",
    "START_ROUND": "str(START_ROUND)",
    "LR": "str(LR)",
    "EPOCHS": "str(EPOCHS)",
    "LOAD_ARG": "LOAD_ARG",  # '' or '--load-adapter /path' — expanded separately
}


def build_python_cell(shell_source: str) -> str:
    lines = [l.rstrip() for l in shell_source.strip().splitlines()]
    # Drop the leading `!` and the trailing continuation backslashes.
    tokens: list[str] = []
    for line in lines:
        line = line.strip()
        if line.startswith("!"):
            line = line[1:]
        line = line.rstrip("\\").strip()
        tokens.extend(line.split())

    # The program (python train_round1.py) must be split off: `!python` may come
    # through as a single token when written without a space.
    cmd_tokens = []
    for tok in tokens:
        cmd_tokens.extend(tok.split(" "))

    # Remove the interpreter name; keep every real arg token.
    rest = cmd_tokens[1:] if cmd_tokens and cmd_tokens[0] in ("python", "python3") else cmd_tokens

    cmd_items: list[str] = []
    load_arg_parts: list[str] = []
    for tok in rest:
        stripped = tok.strip()
        if not stripped:
            continue
        key = stripped[1:-1] if stripped.startswith("{") and stripped.endswith("}") else None
        if key in VAR_MAP:
            expr = VAR_MAP[key]
            if key == "LOAD_ARG":
                load_arg_parts.append("    cmd += LOAD_ARG.split()")
            else:
                cmd_items.append(f'    {expr},')
        else:
            cmd_items.append(f'    "{stripped}",')

    body_lines = [
        "# Runs the trainer with the rounds/config selected in the 'EDIT THIS",
        "# CELL' step above. A shell `!`-cell cannot interpolate the Python",
        "# variables, so the command is built and executed here (subprocess).",
        "import subprocess",
        "",
        "cmd = [",
    ]
    body_lines += cmd_items
    body_lines += [
        "]",
        "",
    ]
    if load_arg_parts:
        body_lines += ["# --load-adapter continuation arg ('' when starting fresh)"]
        body_lines += [p.strip() for p in load_arg_parts]  # top-level statements, not list items
    body_lines += [
        'print("\u25b6  " + " ".join(cmd))',
        "subprocess.run(cmd, check=True)",
    ]
    return "\n".join(body_lines) + "\n"


def patch(path: Path, force: bool) -> bool:
    nb = json.loads(path.read_text())
    changed = False
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if "subprocess.run" in src and not force:
            continue  # already converted
        if not src.strip().startswith("!python"):
            continue
        if "{" not in src:
            continue
        new_src = build_python_cell(src)
        cell["source"] = new_src.splitlines(keepends=True)
        changed = True
        print(f"  converted cell: {path} — was: {src.strip().splitlines()[0][:60]}…")
    if changed:
        path.write_text(json.dumps(nb, indent=1))
    return changed


def main() -> int:
    force = "--force" in sys.argv
    any_changed = False
    for rel in NOTEBOOKS:
        p = ROOT / rel
        if not p.exists():
            print(f"!! missing notebook: {p}")
            return 1
        if patch(p, force):
            any_changed = True
    print("done" + (" — converted placeholder cells" if any_changed else " — nothing to convert"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
