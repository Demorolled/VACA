#!/usr/bin/env python3
"""monitor-vaca.py — watch VACA live from the terminal.

Two things at once:
  1. WebSocket  ws://127.0.0.1:3001/ws  → app actions broadcast live
     (status_update, intent, generation_progress, architect_progress,
     tool_manifest). VACA emits these while the frontend works.
  2. Chat log     data/monitor/conversations.jsonl  → every chat turn the
     backend recorded (user message → response, with flags for canned/echo/
     interceptor paths). The tap is in backend/src/routes/reasoning.ts
     (recordChatTurn).

Usage:
  python3 scripts/monitor-vaca.py            # watch both, live
  python3 scripts/monitor-vaca.py --once     # print current chat log, exit
  python3 scripts/monitor-vaca.py --no-ws    # chat log only
  python3 scripts/monitor-vaca.py --incorrect-only  # only flagged turns

The incorrections file (data/monitor/INCORRECTIONS.md) is where observed
issues get written for the fix pass — run scripts/monitor-vaca.py --incorrect
to append the flagged turns from this session.
"""
import argparse, json, os, subprocess, sys, threading, time

# Unbuffered output so piping/redirecting (setsid nohup … > file) still shows
# lines live instead of waiting for the buffer to fill.
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "monitor", "conversations.jsonl")
INC = os.path.join(ROOT, "data", "monitor", "INCORRECTIONS.md")

WS_URL = "ws://127.0.0.1:3001/ws"

FLAG_EMOJI = {
    "canned:not-sure-how-to-respond": "🚩 canned 'not sure how to respond'",
    "canned:redirect-to-build": "🚩 canned redirect-to-build",
    "role-confusion-interceptor": "🧩 role-confusion interceptor",
    "empty-response": "🚩 empty response",
    "file-write-handled": "📝 file write handled (no LLM)",
    "memory-write-handled": "🧠 memory write handled (no LLM)",
    "declined": "🚫 declined",
    "served-from-cache": "🗄️ served from cache",
    "tool-used": "🔧 tool used",
}


def tail_chat_log(once=False, incorrect_only=False):
    """Print new chat-log lines. If once: print existing lines and return."""
    if not os.path.exists(LOG):
        print(f"[monitor] no chat log yet at {LOG} (backend must serve a chat turn first)")
        return
    pos = 0
    while True:
        try:
            with open(LOG, "r", encoding="utf-8") as f:
                f.seek(pos)
                lines = f.readlines()
                pos = f.tell()
        except FileNotFoundError:
            return
        for line in lines:
            try:
                turn = json.loads(line)
            except Exception:
                continue
            flags = turn.get("flags", []) or []
            if incorrect_only and not flags:
                continue
            if flags and incorrect_only:
                print(f"\n🚩 {turn['ts']} [{turn['route']}]")
                print(f"   user:     {turn['user'][:120]}")
                print(f"   response: {turn['response'][:200]}")
                for fl in flags:
                    print(f"   flag:     {FLAG_EMOJI.get(fl, fl)}")
            elif not incorrect_only:
                fl_txt = f"  {FLAG_EMOJI.get(flags[0], '')}" if flags else ""
                print(f"[{turn['ts']}] {turn['route']}: {turn['user'][:60]} → {turn['response'][:80]}{fl_txt}")
        if once:
            return
        time.sleep(1.0)


def watch_ws():
    """Spawn the Socket.IO watcher (scripts/monitor-ws.mjs) and print events.
    VACA uses Socket.IO (engine.io protocol, path /ws), not raw WebSocket — a
    plain websocket-client cannot decode it, so we shell out to node + the
    bundled socket.io-client."""
    ws_script = os.path.join(ROOT, "scripts", "monitor-ws.mjs")
    try:
        proc = subprocess.Popen(
            ["node", ws_script],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        print("[monitor] node not found — skipping WS. Chat-log monitor still works.")
        return
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except Exception:
            print(f"[ws] {line[:200]}")
            continue
        wtype = evt.get("ws")
        if wtype == "connected":
            print(f"[ws] ✅ connected ({evt.get('id')})")
        elif wtype == "connect_error":
            print(f"[ws] ⚠️ connect error: {evt.get('error')} (is the backend on :3001?)")
        elif wtype == "disconnected":
            print(f"[ws] ❌ disconnected: {evt.get('reason')} (monitor-ws will reconnect)")
        else:
            name = wtype or evt.get("name")
            data = evt.get("data") or {}
            msg = data.get("message") or data.get("status") or data.get("text") or ""
            if name == "status_update":
                print(f"[ws:status] thinking={data.get('thinking')} gen={data.get('isGenerating')} {data.get('projectName','')}")
            elif name == "intent":
                print(f"[ws:intent] {json.dumps(data)[:200]}")
            elif name in ("generation_progress", "architect_progress"):
                print(f"[ws:{name}] {msg} ({data.get('percent')}%)")
            elif name == "tool_manifest":
                print(f"[ws:tool_manifest] ({len(data.get('manifest', []))} tools)")
            else:
                print(f"[ws:{name}] {json.dumps(data)[:200]}")


def append_flagged_to_incorrections():
    """Append today's flagged turns to INCORRECTIONS.md as candidate issues."""
    if not os.path.exists(LOG):
        print("no chat log — nothing to do")
        return
    flagged = []
    with open(LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("flags"):
                flagged.append(t)
    if not flagged:
        print("no flagged turns found")
        return
    os.makedirs(os.path.dirname(INC), exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    with open(INC, "a", encoding="utf-8") as f:
        f.write(f"\n## Flagged turns ({today})\n\n")
        for t in flagged:
            f.write(f"- **{t['ts']}** [{t['route']}] flags={','.join(t['flags'])}\n")
            f.write(f"  - user: {t['user'][:150]}\n")
            f.write(f"  - resp: {t['response'][:200]}\n")
    print(f"appended {len(flagged)} flagged turns → {INC}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="print current chat log and exit")
    ap.add_argument("--no-ws", action="store_true", help="chat log only, no WebSocket")
    ap.add_argument("--incorrect-only", action="store_true", help="only flagged turns")
    ap.add_argument("--incorrect", action="store_true", help="append flagged turns to INCORRECTIONS.md")
    args = ap.parse_args()

    if args.incorrect:
        append_flagged_to_incorrections()
        return

    if args.once:
        tail_chat_log(once=True, incorrect_only=args.incorrect_only)
        return

    print(f"[monitor] VACA live monitor — WS {WS_URL} + chat log {LOG}")
    print(f"[monitor] Ctrl+C to stop. Flagged turns → {INC}\n")
    threads = []
    if not args.no_ws:
        t = threading.Thread(target=watch_ws, daemon=True)
        threads.append(t)
        t.start()
    try:
        tail_chat_log(once=False, incorrect_only=args.incorrect_only)
    except KeyboardInterrupt:
        print("\n[monitor] stopped")


if __name__ == "__main__":
    main()
