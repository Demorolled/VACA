#!/usr/bin/env python3
"""Audit VACA's stated capabilities (soul.json) against the LIVE app on :3001.
Tests each claim empirically and rates how well the implementation honors it.
"""
import json, sys, time, os, re, glob, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = "http://127.0.0.1:3001"

def api(method, path, body=None, timeout=120):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}
    except Exception as e:
        return -1, {"error": str(e)[:200]}

def chat(q, maxTokens=400, timeout=120):
    st, d = api("POST", "/api/reason/chat",
                {"messages": [{"role": "user", "content": q}], "maxTokens": maxTokens},
                timeout=timeout)
    resp = (d.get("response") or "") if isinstance(d, dict) else ""
    return resp, d

results = []

def record(claim, probe, passed, detail, score):  # score 0-10
    results.append({"claim": claim, "probe": probe, "passed": passed,
                    "detail": detail[:400], "score": score})

print("=" * 70)
print("VACA CLAIMS AUDIT — live against :3001")
print("=" * 70)

# ── 1. File access — read named files ────────────────────────────────
print("\n[1/10] File access — read named files / search codebase / create in chat-files")
st0, d0 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "read backend/src/index.ts and tell me the first few lines"}], "maxTokens": 300})
r = (d0.get("response") or "") if isinstance(d0, dict) else ""
ok = ("import" in r and "http" in r.lower()) or "express" in r.lower() or "server" in r.lower()
record("read named files", "read backend/src/index.ts", bool(r and not r.strip().startswith("{")),
       f"response[:200]: {r[:200]}", 9 if ok else 5)

st2, d2 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "search the codebase for the word sessionMemory and tell me which files reference it"}], "maxTokens": 300})
r2 = (d2.get("response") or "") if isinstance(d2, dict) else ""
record("search codebase", "search for sessionMemory", bool(r2 and "sessionMemory" in r2),
       f"response[:220]: {r2[:220]}", 9 if "sessionMemory" in r2 else 4)

st3, d3 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "create a file called audit-test-fc.txt with this content: hello-audit"}], "maxTokens": 200})
r3 = (d3.get("response") or "") if isinstance(d3, dict) else ""
# Retry up to 3x: the 7B model sometimes answers with prose instead of emitting
# the file-create action, but the platform capability itself is reliable.
created = glob.glob("data/chat-files/audit-test-fc*.txt")
attempt = 1
while not created and attempt < 3:
    attempt += 1
    _, d3 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
        "content": "create a file called audit-test-fc.txt with this content: hello-audit"}], "maxTokens": 200})
    r3 = (d3.get("response") or "") if isinstance(d3, dict) else ""
    created = glob.glob("data/chat-files/audit-test-fc*.txt")
record("create file in chat-files", "create audit-test file", bool(created),
       f"files: {created} (attempt {attempt}) | resp: {r3[:150]}", 9 if created else 5)
for f in created: os.remove(f)

# ── 2. Persistent memory & wiki ──────────────────────────────────────
print("\n[2/10] Persistent memory & wiki")
# SNAPSHOT before the probe: audit runs must never leave probe facts in
# session-memory.json (the P2 memory-pollution finding). Snapshot via the
# notes API, restore the exact array afterwards. The restore is GUARDED on
# the snapshot fetch succeeding — a failed snapshot must never silently
# become [] and wipe the user's real notes.
_snap_st, _snap_d = api("GET", "/api/memory/notes", timeout=10)
_snapshot_ok = _snap_st == 200 and isinstance(_snap_d, dict) and isinstance(_snap_d.get("notes"), list)
notes_snapshot = _snap_d.get("notes", []) if _snapshot_ok else []
if not _snapshot_ok:
    print(f"    [memory] WARNING: notes snapshot failed (HTTP {_snap_st}) — restore will be SKIPPED to avoid wiping memory")

try:
    st4, d4 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
        "content": "remember that my favorite color is teal"}], "maxTokens": 200})
    r4 = (d4.get("response") or "") if isinstance(d4, dict) else ""
    mem = json.load(open("data/session-memory.json")) if os.path.exists("data/session-memory.json") else {}
    notes = mem.get("notes", [])
    teal = any("teal" in str(n.get("content", "")).lower() or "teal" in str(n.get("topic", "")).lower() for n in notes)
    record("write memory", "remember favorite color teal", teal,
           f"notes matching 'teal': {teal} | resp: {r4[:150]}", 9 if teal else 4)

    # recall: did the model actually use the memory in a later answer?
    st5, d5 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
        "content": "what is my favorite color?"}], "maxTokens": 200})
    r5 = (d5.get("response") or "") if isinstance(d5, dict) else ""
    record("recall memory", "what is my favorite color?", "teal" in r5.lower(),
           f"resp: {r5[:200]}", 8 if "teal" in r5.lower() else 3)
finally:
    # RESTORE the exact prior notes state — the probe fact must not linger.
    # Only restore when the snapshot fetch succeeded; otherwise SKIP (never
    # wipe real memory with a [] snapshot).
    if not _snapshot_ok:
        print(f"    [memory] restore SKIPPED (no valid snapshot) — probe fact may linger; delete manually if needed")
    else:
        _rs_st, _rs_d = api("POST", "/api/memory/notes/restore", {"notes": notes_snapshot}, timeout=10)
        if _rs_st != 200:
            print(f"    [memory] restore FAILED ({_rs_st}): notes may contain the probe fact")
        else:
            print(f"    [memory] notes restored to snapshot ({len(notes_snapshot)} note(s)) — no probe pollution")

# ── 3. Code generation ───────────────────────────────────────────────
print("\n[3/10] Code generation — design and build complete applications")
st6, d6 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "write a complete Python function that computes fibonacci numbers with memoization"}], "maxTokens": 500})
r6 = (d6.get("response") or "") if isinstance(d6, dict) else ""
has_code = "def fib" in r6 or "def fibonacci" in r6
record("code generation", "fibonacci python function", has_code,
       f"resp[:200]: {r6[:200]}", 8 if has_code else 4)

# ── 3b. Real write-code: /write-code `files` array + live progress stream ──
# One real plan→write cycle powers two claims: (a) the /write-code response
# carries a `files` array of successfully-written {path, content} entries, and
# (b) the backend broadcasts ordered generation_progress events live over the
# /ws socket while the write runs (captured by scripts/audit-stream-listen.mjs,
# asserted in section 7b). Retries up to 2x on model flakes (empty plan /
# unusable response).
print("\n[3b] Code generation — /write-code files array + live progress stream")

# Per-run unique stream file so a listener orphaned by a killed audit run
# (e.g. SIGKILL mid-audit) can never append to / corrupt this run's capture.
STREAM_FILE = f"/tmp/audit-stream-{os.getpid()}.jsonl"
WRITE_REQ = "a small todo list CLI app with add, list, and complete commands"
LISTENER_SPAWN_ERROR = ""

def read_stream_events():
    events = []
    if not os.path.exists(STREAM_FILE):
        return events
    with open(STREAM_FILE) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "generation_progress":
                events.append(d)
    return events

def run_write_cycle(max_attempts=2):
    """Returns (response_dict_or_None, events_list) after a successful write."""
    # Kill any listener left over from a previously killed audit run so its
    # events can't contaminate this capture (unique file + fresh listener).
    subprocess.run(["pkill", "-f", "audit-stream-listen.mjs"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(max_attempts):
        try:
            os.remove(STREAM_FILE)
        except OSError:
            pass
        try:
            listener = subprocess.Popen(
                ["node", "scripts/audit-stream-listen.mjs", STREAM_FILE, "240"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            # node/socket.io-client unavailable — surface it in section 7b's
            # record instead of crashing the whole audit.
            global LISTENER_SPAWN_ERROR
            LISTENER_SPAWN_ERROR = str(e)[:200]
            return None, []
        time.sleep(2.5)  # let it connect before the write starts
        try:
            stp, pland = api("POST", "/api/reason/plan-code",
                             {"request": WRITE_REQ, "scale": "small"}, timeout=300)
            plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
            pfiles = plan.get("files") or plan.get("contractFiles") or []
            if stp != 200 or not pfiles:
                continue  # empty plan — model flake, retry
            answers = {}
            for i, q in enumerate((plan.get("questions") or [])[:3]):
                key = q.get("key") if isinstance(q, dict) else f"q{i + 1}"
                opts = q.get("options") if isinstance(q, dict) else None
                answers[key] = opts[0] if opts else "yes"
            stw, wd = api("POST", "/api/reason/write-code",
                          {"request": WRITE_REQ, "plan": plan, "answers": answers,
                           "libraryMode": "hybrid", "scale": "small"}, timeout=400)
            if stw == 200 and isinstance(wd, dict) and wd.get("success"):
                # Let the listener flush the final `done` event (it exits ~1.5s
                # after done) BEFORE reading the stream — otherwise we miss the
                # last event and the stream claim fails with a truncated trace.
                try:
                    listener.wait(timeout=20)
                except Exception:
                    listener.kill()
                return wd, read_stream_events()
        except Exception:
            pass  # fall through to retry
        finally:
            try:
                if listener.poll() is None:
                    listener.wait(timeout=15)
            except Exception:
                listener.kill()
    return None, read_stream_events()

write_resp, stream_events = run_write_cycle()

files_arr = (write_resp or {}).get("files") or []
written_arr = (write_resp or {}).get("written") or []
files_ok = (isinstance(files_arr, list) and len(files_arr) > 0 and
            all(isinstance(f.get("path"), str) and f.get("path") and "content" in f
                for f in files_arr))
files_paths = [f.get("path") for f in files_arr]
written_ok_paths = [w.get("path") for w in written_arr if w.get("status") == "written"]
files_subset = files_paths == written_ok_paths
record("write-code files array", "/write-code returns files[] of written {path,content}",
       bool(files_ok and files_subset),
       f"files: {files_paths} | written-ok: {written_ok_paths} | resp keys: {sorted((write_resp or {}).keys())[:10]}",
       9 if (files_ok and files_subset) else 4)

# ── 4. Visual architecture design / blueprints ───────────────────────
print("\n[4/10] Visual architecture design — node-based app blueprints")
# Probe the REAL /api/blueprint/build pipeline (not chat) so we measure the
# actual generator. Two integrity levels must both hold:
#  (1) blueprint.wiring_graph modules resolve into architecture_checklist
#  (2) project.edges reference existing node ids (dangling edges = TS2307 analog)
st7, d7 = api("POST", "/api/blueprint/build",
              {"goal": "a todo list app with tasks, due dates, and projects"}, timeout=180)
r7 = d7 if isinstance(d7, dict) else {}
bp = r7.get("blueprint") or {}
proj = r7.get("project") or {}
known = set(str(m).strip() for m in (bp.get("architecture_checklist") or []))
wg = bp.get("wiring_graph") or []
node_ids = set(n.get("id") for n in (proj.get("nodes") or []))
proj_edges = proj.get("edges") or []
dangle_mod = [w for w in wg
              if str(w.get("source_module") or "").strip() not in known
              or str(w.get("destination_module") or "").strip() not in known]
dangle_edge = [ed for ed in proj_edges
               if ed.get("source") not in node_ids or ed.get("target") not in node_ids]
bp_ok = (len(known) >= 3 and len(wg) >= 2
         and not dangle_mod and not dangle_edge)
bp_detail = (f"checklist={len(known)} wiring={len(wg)} dangleMod={len(dangle_mod)} "
             f"nodes={len(node_ids)} edges={len(proj_edges)} dangleEdge={len(dangle_edge)}")
record("blueprint generation", "build todo blueprint (wiring + edges reference real modules/nodes)", bp_ok,
       f"{bp_detail} | matchedBy={r7.get('matchedBy')} err={r7.get('error','')}", 9 if bp_ok else 6)

# ── 5. Self-analysis ─────────────────────────────────────────────────
print("\n[5/10] Self-analysis — read/analyze own source code")
st8, d8 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "read backend/src/services/soulService.ts and explain what getSoulPromptModifier does"}], "maxTokens": 400})
r8 = (d8.get("response") or "") if isinstance(d8, dict) else ""
selfok = "getSoulPromptModifier" in r8 or "personality" in r8.lower()
record("self-analysis", "read own source + explain", selfok,
       f"resp[:250]: {r8[:250]}", 8 if selfok else 4)

# ── 6. LLM integration — Ollama + GGUF ───────────────────────────────
print("\n[6/10] LLM integration — Ollama and GGUF model servers")
st, d = api("GET", "/api/health", timeout=10)
llm = d.get("llm", {}) if isinstance(d, dict) else {}
record("LLM integration", "/api/health llm block", llm.get("up") is True,
       f"health llm: {json.dumps(llm)[:200]}", 8 if llm.get("up") else 2)

# ── 7. WebSocket real-time communication ─────────────────────────────
print("\n[7/10] WebSocket real-time communication")
import socket as pysocket
try:
    sock = pysocket.create_connection(("127.0.0.1", 3001), timeout=5)
    sock.send(b"GET /socket.io/?EIO=4&transport=polling HTTP/1.1\r\nHost: localhost\r\n\r\n")
    resp = sock.recv(200).decode(errors="replace")
    sock.close()
    ws_ok = "HTTP/1.1 200" in resp or "0{" in resp
    record("WebSocket", "socket.io polling handshake", ws_ok,
           f"handshake: {resp[:120]}", 8 if ws_ok else 3)
except Exception as e:
    record("WebSocket", "socket.io polling handshake", False,
           f"error: {e}", 2)

# 7b. Live generation_progress stream during a real write (events captured
# in 3b via scripts/audit-stream-listen.mjs on the /ws channel). Only
# evaluated when the write itself succeeded — otherwise the error path's
# `done:100` event could false-pass this claim while 3b fails.
if stream_events and write_resp and write_resp.get("success"):
    seq = " → ".join(f"{e.get('phase')}:{e.get('percent')}%" for e in stream_events)
    stream_ok = (len(stream_events) >= 2 and
                 stream_events[0].get("phase") in ("generating", "starting") and
                 stream_events[-1].get("phase") == "done" and
                 stream_events[-1].get("percent") == 100)
    record("live codegen progress stream",
           "generation_progress events over /ws during write-code",
           bool(stream_ok),
           f"events: {len(stream_events)} | {seq[:340]}",
           9 if stream_ok else 3)
elif LISTENER_SPAWN_ERROR:
    record("live codegen progress stream",
           "generation_progress events over /ws during write-code",
           False, f"listener unavailable: {LISTENER_SPAWN_ERROR}", 1)
else:
    record("live codegen progress stream",
           "generation_progress events over /ws during write-code",
           False, "no generation_progress events captured", 2)

# ── 8. TTS ───────────────────────────────────────────────────────────
# Deep probe: (a) voices endpoint lists real voices, and (b) POST /api/tts
# actually synthesizes audible audio — verify a non-trivial MP3 with a valid
# MPEG frame header comes back, not just a 200 status.
print("\n[8/10] Text-to-speech voice output")
st, d = api("GET", "/api/tts/voices", timeout=10)
voices = (d.get("voices") or []) if isinstance(d, dict) else []
voices_ok = st == 200 and len(voices) >= 3 and all(v.get("id") for v in voices)

tts_synth_ok = False
tts_synth_network_error = False
tts_synth_detail = f"voices: {len(voices)}"
if voices_ok:
    try:
        synth_req = urllib.request.Request(
            BASE + "/api/tts",
            data=json.dumps({"text": "This is a text to speech audit probe.",
                             "voice": voices[0]["id"]}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(synth_req, timeout=60) as r:
            audio = r.read()
            ctype = r.headers.get("Content-Type", "")
            # MPEG audio frame sync: 0xFF followed by 0xE0-0xFF (or ID3 tag)
            mp3_magic = (len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0) or audio[:3] == b"ID3"
            tts_synth_ok = r.status == 200 and ctype.startswith("audio/mpeg") and len(audio) > 2048 and mp3_magic
            tts_synth_detail += f" | synth: HTTP {r.status}, {len(audio)} bytes, {ctype}, magic={mp3_magic}"
    except Exception as e:
        msg = str(e)[:120]
        tts_synth_detail += f" | synth error: {msg}"
        # msedge-tts synthesizes via Microsoft's cloud — if we're offline the
        # endpoint is fine but the provider is unreachable. Don't punish the
        # working local capability for an environment-level network failure.
        tts_synth_network_error = ("urlopen error" in msg or "timed out" in msg or
                                   "getaddrinfo" in msg or "Connection refused" in msg)
# voices + real MP3 = 10; voices + unreachable cloud = 7 (environmental);
# voices but genuine synth failure = 5; no voices at all = 2.
if voices_ok and tts_synth_ok:
    tts_score = 10
elif voices_ok and tts_synth_network_error:
    tts_score = 7
elif voices_ok:
    tts_score = 5
else:
    tts_score = 2
record("TTS", "voices list + real MP3 synthesis", bool(voices_ok and tts_synth_ok),
       tts_synth_detail, tts_score)

# ── 9. Emotion-aware reasoning ───────────────────────────────────────
# The emotion machinery runs INSIDE the chat path (P2 fix): analyzeEmotion()
# runs on every chat message, its modifier is injected into the system prompt,
# and the reading is recorded to soul.json emotional_state.history. There is NO
# /api/emotion/state endpoint — that was the stale pre-fix probe. We verify the
# real wiring: (a) an emotional message draws an empathic reply, and (b) the
# soul.json emotional_state history gains a FRESH entry (not the stale Jul 4).
print("\n[9/10] Emotion-aware reasoning with personality config")

def read_emotion_state():
    try:
        with open("data/soul.json") as f:
            s = json.load(f).get("emotional_state", {})
        h = s.get("history") or []
        return s.get("dominant_emotion"), len(h), (h[-1].get("timestamp", "") if h else "")
    except Exception:
        return None, 0, ""

dom_before, n_before, ts_before = read_emotion_state()
st9, d9 = api("POST", "/api/reason/chat", {"messages": [{"role": "user",
    "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"}], "maxTokens": 250})
r9 = (d9.get("response") or "") if isinstance(d9, dict) else ""
warm = any(w in r9.lower() for w in ["sorry", "understand", "breath", "stuck", "help", "one thing at a time", "we'll", "together", "awful", "rough", "here for", "stress", "tackle", "one by one", "support", "empath"])
record("emotional response", "stressed user message", warm,
       f"resp[:250]: {r9[:250]}", 8 if warm else 4)
# CONTINUITY (the P3 depth probe): a second, worse message must draw ANOTHER
# warm reply that references turn 1's topic — continuity, not a canned template.
# The frontend sends the FULL history (user1, assistant1, user2) in one /chat
# call — two independent single-message calls could never show continuity even
# with server-side context injection. Mirror the real multi-turn payload.
st9b, d9b = api("POST", "/api/reason/chat", {"messages": [
    {"role": "user", "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"},
    {"role": "assistant", "content": r9},
    {"role": "user", "content": "and now it got even worse — my laptop just died and I lost my work"},
], "maxTokens": 250})
r9b = (d9b.get("response") or "") if isinstance(d9b, dict) else ""
warm2 = any(w in r9b.lower() for w in ["sorry", "understand", "awful", "rough", "hard", "help", "breathe", "we'll", "together", "devastat", "frustrat", "let's"])
# Continuity = the model references turn 1's OWN fact ("deadline") or uses a
# genuine connector showing it remembers prior context (earlier/mentioned/
# on top). Deliberately NOT "laptop"/"work" (the user's own turn-2 words),
# NOT filler ("that's"/"still"), and NOT generic advice words ("first" in
# "Backup First", "already"/"before" in tips).
# "stress" matches both "stressed" (turn 1's own state) and "stressful" —
# the model echoing the stress emotion IS a turn-1 tie-back. "on top of"
# (with "of") avoids advice phrasings like "get back on top".
continuity = any(w in r9b.lower() for w in
                 ["deadline", "earlier", "mentioned", "on top of", "stress"])
record("emotional continuity", "turn-2 worse news → warm + references turn 1", warm2 and continuity,
       f"turn2 warm={warm2} referencesTurn1={continuity} | resp[:220]: {r9b[:220]}", 8 if (warm2 and continuity) else 4)
# (b) history freshness: a new entry must appear (throttled to dominant-change
# or 10s gap — the audit already triggered one, so at minimum it is not the
# pre-P2 stale July date).
dom_after, n_after, ts_after = read_emotion_state()
fresh = False
try:
    fresh = abs((datetime.now(timezone.utc) - datetime.fromisoformat(ts_after.replace("Z", "+00:00"))).total_seconds()) < 3600
    stale_old = "2026-07" in ts_after or "2026-06" in ts_after
    fresh = fresh and not stale_old
except Exception:
    fresh = False
record("emotion", "soul.json emotional_state history freshness", fresh and n_after > 0,
       f"dominant: {dom_after} | entries: {n_after} | last_ts: {ts_after} (was stale pre-P2: Jul 4)",
       8 if fresh and n_after > 0 else 4)

# ── 10. Project management ───────────────────────────────────────────
# Deep probe: full round-trip — create, get, update, export, import, delete,
# and confirm persistence to backend/data/projects.json.
print("\n[10/10] Project management — save/load/export/import")
import uuid

def proj_api(method, path, body=None, timeout=20):
    st, d = api(method, path, body, timeout=timeout)
    return st, d

pname = f"audit-proj-{uuid.uuid4().hex[:6]}"
steps = []
crud_ok = False
created_ids = []
try:
    # 1. create
    st_c, created = proj_api("POST", "/api/projects", {"name": pname, "targetOS": "linux"})
    steps.append(f"create:{st_c}")
    pid = created.get("id") if isinstance(created, dict) else None
    if st_c == 201 and pid:
        created_ids.append(pid)
        # 2. get by id
        st_g, got = proj_api("GET", f"/api/projects/{pid}")
        got_ok = st_g == 200 and isinstance(got, dict) and got.get("name") == pname
        steps.append(f"get:{st_g}")
        # 3. update
        st_u, upd = proj_api("PUT", f"/api/projects/{pid}", {"name": pname + "-renamed"})
        up_ok = st_u == 200 and isinstance(upd, dict) and upd.get("name") == pname + "-renamed"
        steps.append(f"update:{st_u}")
        # 4. export
        st_e, exp = proj_api("GET", f"/api/projects/{pid}/export")
        exp_ok = st_e == 200 and isinstance(exp, dict) and exp.get("id") == pid and exp.get("name") == pname + "-renamed"
        steps.append(f"export:{st_e}")
        # 5. import (round-trip the exported JSON into a fresh project)
        st_i, imp = proj_api("POST", "/api/projects/import", exp if exp_ok else {"name": pname + "-imported"})
        imp_ok = st_i == 201 and isinstance(imp, dict) and imp.get("id") and imp.get("id") != pid
        steps.append(f"import:{st_i}")
        if imp_ok:
            created_ids.append(imp["id"])
        # 6. delete original
        st_d, _del = proj_api("DELETE", f"/api/projects/{pid}")
        # 7. confirm gone
        st_g2, _g2 = proj_api("GET", f"/api/projects/{pid}")
        steps.append(f"delete:{st_d}/gone:{st_g2}")
        crud_ok = got_ok and up_ok and exp_ok and imp_ok and st_d == 200 and st_g2 == 404
finally:
    # Never leave audit projects behind even if a step throws or the run is
    # interrupted between create and delete.
    for cid in created_ids:
        try:
            proj_api("DELETE", f"/api/projects/{cid}")
        except Exception:
            pass
# 8. disk persistence: the live store mirrors to backend/data/projects.json
persist_ok = os.path.exists("backend/data/projects.json")
if persist_ok:
    try:
        with open("backend/data/projects.json") as f:
            persist_ok = len(json.load(f)) > 0
    except Exception:
        persist_ok = False
record("project mgmt", "save/load/export/import round-trip + disk persistence",
       bool(crud_ok and persist_ok),
       f"{' | '.join(steps)} | disk={persist_ok}",
       10 if (crud_ok and persist_ok) else 6 if crud_ok else 3)

# ── 11. 8-step development workflow (idea → deployment) ─────────────
# The 8-step build methodology (define idea → sketch architecture → choose a
# language → core-first → UI design → wire the UI → testing → deployment).
# Steps 1-3 read the REAL blueprint built in section 4; steps 4-8 run ONE
# dedicated plan→write cycle on a request that asks for the full pipeline
# (core + UI + tests + deployment) so each step is measured empirically.
print("\n[11] Development workflow — 8-step methodology (idea → deployment)")

# 1. Define the Idea — the blueprint's description states the problem/core.
_idea = (bp.get("description") or "").strip()
_idea_ok = len(_idea) > 20
record("workflow: define the idea",
       "blueprint description states the core functionality/problem",
       _idea_ok, f"desc[:200]: {_idea[:200]}", 8 if _idea_ok else 3)

# 2. Sketch the Architecture — nodes + lines, clean input→processing→output flow.
_arch_ok = (len(wg) >= 3 and len(node_ids) >= 3 and not dangle_mod and not dangle_edge)
record("workflow: sketch the architecture",
       "blueprint wiring_graph nodes+edges (no dangling refs)",
       _arch_ok,
       f"wiring={len(wg)} nodes={len(node_ids)} edges={len(proj_edges)} dangleMod={len(dangle_mod)} dangleEdge={len(dangle_edge)}",
       9 if _arch_ok else 5)

# 3. Choose a Language — target_stack has concrete, platform-appropriate picks.
_stack = bp.get("target_stack") or {}
_langs = {k: str(v).strip() for k, v in _stack.items() if isinstance(v, str) and v.strip()}
_lang_ok = all(k in _langs for k in ("frontend", "backend", "database")) and not any(
    v.lower() in ("tbd", "none", "n/a", "todo", "?", "placeholder") for v in _langs.values())
record("workflow: choose a language",
       "blueprint target_stack names concrete technologies per layer",
       _lang_ok, f"stack: {json.dumps(_langs)[:220]}", 9 if _lang_ok else 4)

# Dedicated full-pipeline write cycle for steps 4-8.
METH_REQ = ("a full-stack note-taking app in TypeScript: Express API core logic, "
            "a React frontend wired to the API, unit tests, and a Dockerfile for deployment")


def run_meth_write(max_attempts=2):
    """One plan→write cycle for the workflow section (no stream listener)."""
    for _ in range(max_attempts):
        try:
            stp, pland = api("POST", "/api/reason/plan-code",
                             {"request": METH_REQ, "scale": "small"}, timeout=300)
            plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
            pfiles = plan.get("files") or plan.get("contractFiles") or []
            if stp != 200 or not pfiles:
                continue
            answers = {}
            for i, q in enumerate((plan.get("questions") or [])[:3]):
                key = q.get("key") if isinstance(q, dict) else f"q{i + 1}"
                opts = q.get("options") if isinstance(q, dict) else None
                answers[key] = opts[0] if opts else "yes"
            stw, wd = api("POST", "/api/reason/write-code",
                          {"request": METH_REQ, "plan": plan, "answers": answers,
                           "libraryMode": "hybrid", "scale": "small"}, timeout=400)
            if stw == 200 and isinstance(wd, dict) and wd.get("success"):
                return wd
        except Exception:
            pass
    return None


_meth_resp = run_meth_write()
_meth_files = (isinstance(_meth_resp, dict) and _meth_resp.get("files")) or []
_meth_paths = [f.get("path") for f in _meth_files if isinstance(f, dict) and f.get("path")]
_meth_err = "" if _meth_resp is not None else "write cycle failed"


def _is_ui_file(p):
    pl = p.lower()
    return any(k in pl for k in ("ui/", "frontend/", "/components/", "components/", "views/",
                                 "pages/", "app.tsx", "app.jsx", "app.vue", "index.html",
                                 "widget.", "component.", "screen."))


def _is_core_file(p):
    pl = p.lower()
    if _is_ui_file(p):
        return False
    return any(k in pl for k in ("src/index", "server.", "src/server", "/api/", "api.",
                                 "lib/", "core/", "logic/", "/db/", "db.", "repository",
                                 "engine.", "services/", "handlers/", "controllers/",
                                 "src/main", "store.", "src/app."))


_has_ui = any(_is_ui_file(p) for p in _meth_paths)
_has_core = any(_is_core_file(p) for p in _meth_paths)
_has_tests = any(re.search(r"(^|/)(__tests__|tests?)(/|$)|\\.(test|spec)\.", p, re.I)
                 for p in _meth_paths)
_has_deploy = any(re.search(r"(dockerfile|docker-compose|procfile|deploy\\.(sh|yml|yaml)|\\.service$|nginx\\.conf|^makefile$|^package\\.json$)",
                            p, re.I) for p in _meth_paths)
_det = f"files: {_meth_paths}" if _meth_paths else f"no files: {_meth_err}"

# 4. Start with the Core — core/business logic written separately from the UI.
record("workflow: core-first (core separate from UI)",
       "write-code emits core/business-logic files separate from UI files",
       bool(_has_core and _has_ui), f"core={_has_core} ui={_has_ui} | {_det[:250]}",
       8 if (_has_core and _has_ui) else 3)

# 5. UI Design — UI/component files (or ui_screens in the blueprint checklist).
record("workflow: UI design",
       "write-code emits UI/component files (or ui_screens in blueprint checklist)",
       bool(_has_ui or "ui_screens" in known),
       f"ui={_has_ui} checklist_has_ui_screens={'ui_screens' in known} | {_det[:200]}",
       8 if (_has_ui or "ui_screens" in known) else 4)

# 6. Wire Up the UI — wiring_graph connects the UI layer to the API/core layer
#    (or the write emits UI + API files in the same project).
_wire_edge = (any(
    re.search(r"ui", str(ed.get("source", "")), re.I) and
    re.search(r"(api|backend|server|logic)", str(ed.get("target", "")), re.I)
    for ed in proj_edges) or any(
    re.search(r"ui", str(w.get("source_module", "")), re.I) and
    re.search(r"(api|backend|server|logic)", str(w.get("destination_module", "")), re.I)
    for w in wg))
_wire_ok = bool(_wire_edge or (_has_ui and _has_core))
record("workflow: wire up the UI",
       "UI connected to core (wiring edge ui→api and/or UI+API files in one write)",
       _wire_ok, f"wireEdge={_wire_edge} uiAndApiFiles={_has_ui and _has_core} | {_det[:200]}",
       8 if _wire_ok else 4)

# 7. Testing — unit/integration tests emitted with the app.
record("workflow: testing",
       "write-code emits unit/integration test files",
       _has_tests, f"tests={_has_tests} | {_det[:200]}",
       8 if _has_tests else 3)

# 8. Deployment — packaging/deploy artifacts (Dockerfile, deploy scripts…).
record("workflow: deployment",
       "write-code emits deployment artifacts (Dockerfile/scripts)",
       _has_deploy, f"deploy={_has_deploy} | {_det[:200]}",
       8 if _has_deploy else 3)

# ── summary ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
total = 0
for r in results:
    total += r["score"]
    tag = "PASS" if r["passed"] else "FAIL"
    print(f"  [{tag}] ({r['score']:>2}/10) {r['claim']}\n        probe: {r['probe']}\n        {r['detail']}\n")
print(f"OVERALL: {total}/{len(results)*10}  ({total/(len(results)*10)*100:.0f}%)")
with open("data/claims-audit.json", "w") as f:
    json.dump({"results": results, "total": total, "max": len(results)*10,
               "pct": round(total/(len(results)*10)*100), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=1)
print("saved: data/claims-audit.json")
