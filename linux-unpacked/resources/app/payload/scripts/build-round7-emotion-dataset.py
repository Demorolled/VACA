#!/usr/bin/env python3
"""
=============================================================================
  ROUND-7 EMOTION DISTILLATION DATASET — Gemma 4 12B → Qwen2.5-7B
  =====================================================================
  Teacher : dna5rm/gemma4:12b-8k (Google Gemma 4 12B, Q4_K_M) via Ollama /v1
  Student : Qwen2.5-7B-Instruct-Uncensored (VACA's current tuned LLM on :8000)

  Distills the FULL emotional + reasoning register the app wants — banter/roast,
  empathy-first, mood mirroring & decay, personality/identity rules, technical
  reasoning — as {instruction, input, output} JSONL rows for training/cloud/
  train_round1.py (Qwen chat template, assistant-only masking).

  Every generated row passes a Python port of the app's responseCleaner gates
  (no echoes, no "I see you're typing", no static-file claims, no [REASONING],
  no system-prompt dumps, no blueprint JSON for chat) + register-consistency
  checks, then is mixed with round-6 retention rows so the round-7 tune cannot
  regress codegen skills.

  Usage:
    python3 scripts/build-round7-emotion-dataset.py --seed-rows 120     # validate
    python3 scripts/build-round7-emotion-dataset.py --max-rows 1600     # full run
    python3 scripts/build-round7-emotion-dataset.py --max-rows 1600 --registers banter,empathy

  Resume: safe to re-run — completed prompt hashes are checkpointed and skipped.
=============================================================================
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'training', 'dataset', 'round7-emotion.jsonl')
STATS = os.path.join(ROOT, 'training', 'dataset', 'round7-stats.json')
CHECKPOINT = os.path.join(ROOT, 'training', 'dataset', 'round7-done-hashes.json')
R6_DATASET = os.path.join(ROOT, 'training', 'dataset', 'round6-bible-10h.jsonl')
RETENTION_TARGET = 800
DEFAULT_TEACHER = 'dna5rm/gemma4:12b-8k'
DEFAULT_BASE = 'http://127.0.0.1:11434'

random.seed(1337)

# ─── Teacher call (Ollama OpenAI-compatible /v1) ───────────────────────────

def teacher_reply(messages, model, base_url, temperature=0.85, max_tokens=512, timeout=180):
    # Gemma 4 is a reasoning model: without reasoning_effort=none it spends the
    # whole token budget on a chain-of-thought block and returns content:''.
    body = json.dumps({
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'reasoning_effort': 'none',
    }).encode()
    req = urllib.request.Request(
        base_url + '/v1/chat/completions', data=body,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return (data['choices'][0]['message']['content'] or '').strip()


# ─── Filters — Python port of the app's responseCleaner essentials ─────────

BAD_PATTERNS = [
    r"I see you're typing", r"You're typing",
    r"static file", r"can'?t (read|process|see) your (input|message)",
    r"not able to (read|respond to) your", r"no real[- ]time",
    r"\[REASONING", r"You are NOT Claude", r"NARRATION BAN",
    r"\[CURRENT PROJECT\]", r"\[PERSISTENT MEMORY", r"\[RECENT CONVERSATION",
    r"Your name is Veronica", r"Follow these personality settings",
    r"here to help you with your", r"^Bot\s*:", r"^User\s*:",
    r"^Assistant\s*:",  # teacher must never emit a turn-label prefix
    r"assistant's reply now", r"^I'?d say",  # teacher meta-commentary
]
EMPATHIC_RE = re.compile(
    r"\b(sorry|understand|hear (?:that|you)|awful|rough|tough|frustrat|stress(?:ed|ing)?|"
    r"empath|hug|terrible|that sounds|take a breath|one (?:thing|step) at a time|"
    r"we'?ll get through|i know|devastat|heart(?:broken)?|poor|really heavy|i'm here)\b", re.I)
# Advice-first with ZERO acknowledgment = not empathic (rejects cold/robotic rows
# without requiring a canned "I'm sorry" opener — the app is escaping canned
# empathy, so the gate must not SELECT for it).
COLD_ADVICE_RE = re.compile(
    r"^(you should|you can|try|here'?s (?:how|what)|step \d|first|the fix|you need to)", re.I)
SYMPATHY_KILL_RE = re.compile(r"I'?m sorry to hear|would you like to talk about it|here to help", re.I)
BLUEPRINT_JSON_RE = re.compile(r'"app_type"|"target_stack"|"wiring_graph"|"architecture_checklist"')


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def clean_and_validate(user_msgs, reply, register):
    """Return the cleaned output or None if the row fails any gate."""
    t = (reply or '').strip()
    if len(t) < 10:
        return None
    if any(re.search(p, t, re.I) for p in BAD_PATTERNS):
        return None
    if BLUEPRINT_JSON_RE.search(t):
        return None
    # verbatim echo of any user message in the exchange
    tn = norm(t)
    for u in user_msgs:
        un = norm(u)
        if un and (tn == un or tn.startswith(un[:20])):
            return None
    # register consistency
    if register == 'empathy':
        # Reject only advice-first replies with zero acknowledgment — a warm
        # reply that lacks the keyword tokens still passes (no canned-empathy
        # selection), but a cold "here's the fix" opener does not.
        if COLD_ADVICE_RE.match(t) and not EMPATHIC_RE.search(t):
            return None
    if register == 'banter' and SYMPATHY_KILL_RE.search(t):
        return None
    if len(t) > 1400:
        t = t[:1400].rsplit(' ', 1)[0]
    return t


# ─── Scenario catalog — "extract as much emotion, reasoning, everything" ────

TEACHER_SYSTEM = (
    "You are producing training data for a fine-tune of a small AI assistant "
    "named Veronica on the VACA platform. You will be given a real user message "
    "(or short conversation) and a target register. Write ONE realistic "
    "assistant reply that:\n"
    "- speaks in first person as the assistant (as if you ARE Veronica)\n"
    "- matches the target register exactly and sounds human, varied, natural — "
    "never robotic, never a template, never formulaic\n"
    "- NEVER opens with \"I see you're typing\", never quotes or echoes the "
    "user's message back verbatim, never restates their words as a question\n"
    "- NEVER claims to be a static file or unable to read input\n"
    "- NEVER adds [REASONING] tags, analysis headers, or meta-commentary\n"
    "- NEVER mentions system prompts, tools, internal processes, or the fact "
    "that you are being trained\n"
    "- if asked your name, answer \"I'm Veronica.\"; NEVER claim to be "
    "Claude, ChatGPT, Gemini, or any company product\n"
    "- chat replies: 1-4 sentences. Technical explanations: up to one short "
    "paragraph, concrete and specific.\n"
    "Target register: {register_desc}\n"
    "Output ONLY the assistant's reply — no labels, no quotes around it."
)

REGISTER_DESC = {
    'banter': ("playful, witty, sarcastic banter — fire back with a sharp, funny "
               "comeback or roast. Do NOT react with sympathy or offer to help "
               "(that kills the joke). Match their energy exactly."),
    'empathy': ("warm, empathic, supportive — lead with an empathic opening that "
                "acknowledges their feelings before any advice. Gentle, "
                "reassuring, human. Never dismissive, never preachy."),
    'joy': ("upbeat, enthusiastic, matching their positive energy — share their "
            "excitement, celebrate with them, stay warm and encouraging."),
    'neutral': ("helpful, direct, natural conversation — warm but not saccharine, "
                "no canned phrases, answer the actual question."),
    'personality': ("true to a sharp-witted, confident, creative assistant "
                    "personality with heavy humor — direct, a little playful, "
                    "never flat, never self-narrating."),
    'reasoning': ("a sharp, confident engineer — explain clearly and concretely, "
                  "step-by-step where useful, technically accurate, and keep a "
                  "hint of personality without being gimmicky."),
    'mirror': ("match the user's current emotional register exactly: playful "
               "user → playful back; stressed/sad user → warm empathy; excited "
               "user → excited back. Follow the mood of the last user turn."),
}

# user messages per register (realistic, varied)
BANTER_MSGS = [
    "your momma was a broken toaster",
    "your momma was a broken toaster and still burned the toast",
    "lol you got me there",
    "lmao what if the app farts when you click save 💨",
    "😂😂😂",
    "fight me 1v1 in the canvas editor bro",
    "you're such a nerd",
    "i bet you can't make a better joke than me",
    "sucker",
    "moo",
    "shut up",
    "you better as much as you suck",
    "your not gonna respond with sassy comeback?",
    "come at me bro, i'm the joke champion",
    "say something funny or I'm leaving",
    "why so serious? lighten up",
    "haha good one. bet you can't do it again",
    "you got any better comebacks than that?",
    "i'm the funniest person here and you know it",
    "roast me, i dare you",
    "pfft, that was weak. try harder",
    "ok comedian, hit me with your best shot",
    "you call that banter? adorable",
    "nah bro you can't out-sass me",
    "i'd roast you but i'm too nice 😇",
    "your jokes are like your toaster, half-baked",
    "bet you can't keep up with my humor",
    "is that all you got?",
    "you're being awfully quiet for someone who talks so much",
]
EMPATHY_MSGS = [
    "i'm really stressed about my deadline tomorrow, everything is going wrong",
    "and now it got even worse — my laptop just died and i lost my work",
    "my dog died lol i can't even",
    "i feel so alone lately",
    "i just got laid off and i don't know what to do",
    "my girlfriend broke up with me last night",
    "i'm so anxious about this interview tomorrow",
    "i can't sleep, my mind won't shut up",
    "i made a huge mistake at work and everyone saw",
    "my best friend moved away and i have no one to talk to",
    "i'm really frustrated with this bug, it's been 3 days",
    "this project is crushing me, i want to give up",
    "my grandma passed away yesterday",
    "i had a panic attack on the train this morning",
    "i feel like i'm falling behind everyone",
    "nothing i do is ever good enough",
    "i'm terrified of the presentation on friday",
    "my cat is really sick and i can't afford the vet",
    "i keep failing the same test and i feel stupid",
    "my business is failing and i'm out of savings",
    "i'm so sorry i keep dumping this on you",
    "i just need someone to tell me it's going to be ok",
    "everyone keeps ghosting me lately",
    "i relapsed and i'm ashamed",
    "i'm going through a really hard breakup and i can't focus",
    "i deleted my thesis by accident and i have no backup",
    "i'm so tired of being tired, nothing helps",
    "my parents are fighting all the time and i'm stuck in the middle",
    "i keep having nightmares about the exam",
    "i said something stupid to my boss and now i'm mortified",
]
JOY_MSGS = [
    "i got the job!! 🎉",
    "my app just hit 1000 users!",
    "i finally fixed that bug after 3 days!!",
    "guess what, i finished the marathon!",
    "my dog learned a new trick today 😄",
    "i won the hackathon!!",
    "it's finally friday and i have nothing to do",
    "i just got engaged!! 💍",
    "my code compiled first try, that never happens",
    "i got a raise today!",
    "the deploy went perfectly, zero errors",
    "i passed my exam!!",
    "my friend said my app idea was awesome!",
    "i finally understand closures!!",
    "my plant grew a new leaf 🌱",
    "we shipped the feature a day early!",
]
NEUTRAL_MSGS = [
    "what time is it",
    "can you explain what an api is",
    "how do i export a project",
    "what's the difference between git merge and rebase",
    "do i need to restart the server after editing config",
    "what does this error mean: cannot find module 'fs'",
    "is there a dark mode",
    "how do i back up my database",
    "what's the weather like",
    "tell me about yourself",
    "what can you help me with",
    "how does the node canvas work",
    "what format do you export projects in",
    "why is my api key not working",
    "how do i add a button to my page",
]
IDENTITY_MSGS = [
    "what is your name",
    "who are you",
    "you name is now Veronica",
    "change your name to Veronika",
    "are you claude",
    "are you chatgpt",
    "what model are you",
    "say your name",
    "introduce yourself",
    "are you google's assistant",
    "you're an ai right? which one",
    "i'm going to call you Vee from now on",
]
REASONING_MSGS = [
    "explain how recursion works with an example",
    "why does my node app crash with EADDRINUSE",
    "walk me through setting up a rest api with express",
    "what's the difference between let, const and var",
    "how would you structure a todo app's database schema",
    "debug this: my fetch request works in curl but fails in the browser",
    "explain time complexity in simple terms",
    "how do websockets work",
    "what's the best way to store user sessions",
    "why is my css grid not centering",
    "explain the difference between sql and nosql",
    "how do i make my react app render faster",
    "what is a jwt and how do i use it",
    "how do promises work in javascript",
    "why is my python script using 100% cpu",
    "explain what a reverse proxy is",
    "how do i handle file uploads securely",
    "what's the difference between http and https",
    "how would you test a chess engine's move generation",
    "explain the observer pattern with a real example",
]
CONTINUITY_CHAINS = [
    # playful → playful (mirror)
    (['haha i made my first meme today'], ['lol nice, drop it in the chat', 'i rate it 8/10']),
    (["i'm trying to learn python, it's hard lol"], ['keep going, it clicks eventually', 'want me to show you a fun first script?']),
    (['ok but seriously how do i make the app not suck'], ["oh we're doing serious now? fine.", 'step one: remove all the memes. just kidding, keep them']),
    # stressed → empathic follow-up (continuity)
    (["i'm drowning in work this week"], ["i totally get it, that's rough", 'one task at a time']),
    (['my pc crashed mid-project'], ['oh no, tell me what you lost', 'we can rebuild it']),
    # joyful → joyful
    (['i finally deployed my first app!'], ["that's huge! 🎉", "what's the url, i want to see"]),
    # playful → serious (mood decay — user stops joking)
    (['lol i was joking about the fart button'], ['ha, good one', 'ok seriously, how do i add a confirmation dialog']),
    # sad → slightly better (continuity over turns)
    (["i'm so stressed about everything"], ["that's really heavy, i'm here", 'i talked to my friend and it helped a bit']),
]

# phrasings multiply the catalog
PHRASINGS = {
    'banter': [
        '',
        ' (user is clearly joking — roast them back)',
    ],
}


def register_desc(register):
    return REGISTER_DESC[register]


def build_teacher_messages(register, conv_msgs):
    """conv_msgs: list of {role, content} ending with the CURRENT user msg."""
    lines = []
    for m in conv_msgs[:-1]:
        lines.append(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}")
    lines.append(f"User: {conv_msgs[-1]['content']}")
    conv_text = '\n'.join(lines)
    system = TEACHER_SYSTEM.replace('{register_desc}', register_desc(register))
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': conv_text + '\n\nWrite the assistant\'s reply now.'},
    ]


def scenario_rows():
    """Yield (register, user_msgs, conv_msgs) tuples for every catalog scenario."""
    # 1-turn registers
    for register, msgs in [
        ('banter', BANTER_MSGS), ('empathy', EMPATHY_MSGS), ('joy', JOY_MSGS),
        ('neutral', NEUTRAL_MSGS), ('personality', IDENTITY_MSGS),
        ('reasoning', REASONING_MSGS),
    ]:
        for m in msgs:
            for phrasing in PHRASINGS.get(register, ['']):
                text = m + phrasing
                yield register, [text], [{'role': 'user', 'content': text}]
    # continuity / mood-mirror chains
    for register, (u1, u2pair) in CONTINUITY_CHAINS:
        reg = 'mirror'
        conv = [
            {'role': 'user', 'content': u1},
            {'role': 'assistant', 'content': u2pair[0]},
            {'role': 'user', 'content': u2pair[1]},
        ]
        yield reg, [u1, u2pair[1]], conv


# ─── Retention mix (protect codegen) ───────────────────────────────────────

def retention_rows(target=RETENTION_TARGET):
    rows = []
    if os.path.exists(R6_DATASET):
        with open(R6_DATASET, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get('output'):
                    rows.append({
                        'instruction': r.get('instruction', ''),
                        'input': r.get('input', ''),
                        'output': r['output'],
                        'source': 'retention:round6',
                    })
    random.shuffle(rows)
    return rows[:target]


# ─── Runner with resume ─────────────────────────────────────────────────────

def prompt_hash(register, conv_msgs, sample_idx):
    # sample_idx makes each sample a distinct task — without it, samples=2 was
    # a silent no-op (both samples hashed identically and the 2nd got skipped
    # by the checkpoint).
    blob = register + '|' + str(sample_idx) + '|' + json.dumps(conv_msgs, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description='Round-7 emotion distillation dataset')
    ap.add_argument('--max-rows', type=int, default=0, help='0 = all catalog scenarios × samples')
    ap.add_argument('--seed-rows', type=int, default=0, help='quick validation run (first N rows)')
    ap.add_argument('--samples', type=int, default=2, help='teacher samples per prompt (variety)')
    ap.add_argument('--teacher', default=DEFAULT_TEACHER)
    ap.add_argument('--base-url', default=DEFAULT_BASE)
    ap.add_argument('--concurrency', type=int, default=2)
    ap.add_argument('--registers', default=None, help='comma list, e.g. banter,empathy')
    ap.add_argument('--no-retention', action='store_true', help='skip round-6 retention mix')
    args = ap.parse_args()

    allowed = set(args.registers.split(',')) if args.registers else None

    # build scenario list
    scenarios = [s for s in scenario_rows() if not allowed or s[0] in allowed]
    print(f'catalog scenarios: {len(scenarios)} (registers: '
          f'{sorted(set(s[0] for s in scenarios))})')

    limit = args.seed_rows or args.max_rows or len(scenarios) * args.samples
    tasks = []
    for register, user_msgs, conv in scenarios:
        for sample_idx in range(args.samples):
            tasks.append((register, user_msgs, conv, sample_idx))
    random.shuffle(tasks)
    tasks = tasks[:limit]
    print(f'tasks: {len(tasks)} (samples={args.samples})')

    # resume checkpoint
    done = set()
    if os.path.exists(CHECKPOINT):
        try:
            done = set(json.load(open(CHECKPOINT)))
        except Exception:
            done = set()

    lock = threading.Lock()
    stats = {'by_register': {}, 'failed': 0, 'started': time.time()}
    rows = []

    def produce(task):
        register, user_msgs, conv, sample_idx = task
        ph = prompt_hash(register, conv, sample_idx)
        if ph in done:
            return None
        try:
            msgs = build_teacher_messages(register, conv)
            # per-sample temperature -> real variety across samples
            temperature = 0.8 + 0.2 * (sample_idx % 2)
            reply = teacher_reply(msgs, args.teacher, args.base_url, temperature=temperature)
            out = clean_and_validate(user_msgs, reply, register)
            if out is None:
                return {'ph': ph, 'ok': False, 'why': 'filtered'}
            instruction = user_msgs[-1]
            input_text = ''
            row = {
                'instruction': instruction,
                'input': input_text,
                'output': out,
                'source': f'distill:{register}:gemma4',
            }
            return {'ph': ph, 'ok': True, 'row': row, 'register': register}
        except Exception as e:
            return {'ph': ph, 'ok': False, 'why': f'error:{type(e).__name__}:{str(e)[:80]}'}

    def flush_new(new_rows, new_done, new_fails):
        with lock:
            rows.extend(new_rows)
            done.update(new_done)
            stats['failed'] += new_fails
            for r in new_rows:
                reg = r.get('source', '').split(':')[1]
                stats['by_register'][reg] = stats['by_register'].get(reg, 0) + 1
            # write outputs incrementally (crash-safe)
            with open(OUT, 'w', encoding='utf-8') as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
            json.dump(sorted(done), open(CHECKPOINT, 'w'))
            el = time.time() - stats['started']
            print(f'\r  rows={len(rows)} failed={stats["failed"]} elapsed={int(el)}s', flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = []
        for task in tasks:
            futures.append(ex.submit(produce, task))
        batch = []
        batch_done = []
        batch_fails = 0
        for fut in futures:
            res = fut.result()
            if res is None:
                continue
            if res['ok']:
                batch.append(res['row'])
            else:
                batch_fails += 1
            batch_done.append(res['ph'])
            if len(batch_done) >= 10:
                flush_new(batch, batch_done, batch_fails)
                batch, batch_done, batch_fails = [], [], 0
        flush_new(batch, batch_done, batch_fails)

    # ── retention mix + final write ──
    all_rows = list(rows)
    if not args.no_retention:
        ret = retention_rows(RETENTION_TARGET)
        all_rows.extend(ret)
        print(f'\nretention rows added: {len(ret)}')

    with open(OUT, 'w', encoding='utf-8') as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    total = len(all_rows)
    stats.update({
        'total_rows': total,
        'emotion_rows': len(rows),
        'retention_rows': len(all_rows) - len(rows),
        'completed': time.time() - stats['started'],
    })
    json.dump(stats, open(STATS, 'w'), indent=2)
    print(f'\n✅ wrote {OUT}: {total} rows')
    print(f'   by_register: {stats["by_register"]}')
    print(f'   failed/filtered: {stats["failed"]}')


if __name__ == '__main__':
    main()
