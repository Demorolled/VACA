#!/usr/bin/env python3
"""A/B test: current soul traits vs a warmed-up personality against the live DSpark model.

Mimics the exact descriptor logic in backend/src/services/soulService.ts
getSoulPromptModifier() so the demo reflects what the backend really sends.
"""
import json
import urllib.request

DSPARK = "http://127.0.0.1:8000/v1/chat/completions"

# Exact same branching as soulService.ts
def build_personality(t):
    d = []
    d.append('warm and affectionate' if t['warmth'] > 70 else
             'warm and friendly' if t['warmth'] > 50 else
             'pleasant' if t['warmth'] > 30 else 'cool and professional')
    d.append('playfully sarcastic' if t['sassiness'] > 70 else
             'occasionally witty' if t['sassiness'] > 50 else
             'straightforward' if t['sassiness'] > 30 else 'earnest and direct')
    d.append('detailed and thorough' if t['verbosity'] > 70 else
             'explanatory' if t['verbosity'] > 50 else 'concise')
    d.append('empathetic and understanding' if t['empathy'] > 60 else
             'considerate' if t['empathy'] > 30 else 'focused on results')
    d.append('formal and precise' if t['formality'] > 70 else
             'semi-formal' if t['formality'] > 40 else 'casual and relaxed')
    d.append('creative and inventive' if t['creativity'] > 70 else
             'practical' if t['creativity'] > 40 else 'by-the-book')
    d.append('proactive and initiative-taking' if t['proactiveness'] > 60 else 'responsive')
    d.append('inquisitive and exploratory' if t['curiosity'] > 70 else 'focused')
    d.append('patient and thorough' if t['patience'] > 60 else
             'patient' if t['patience'] > 30 else 'impatient with inefficiency')
    return ', '.join(d)

def build_soul_mod(t, personality_desc):
    lines = []
    lines.append("Personality: " + personality_desc)
    lines.append("")
    lines.append("Adjust your responses according to these personality settings.")
    lines.append("- Warmth %d — %s" % (t['warmth'], 'be warm and approachable' if t['warmth'] > 50 else 'be professional and direct'))
    lines.append("- Sassiness %d — %s" % (t['sassiness'], 'feel free to be witty and playful' if t['sassiness'] > 50 else 'be straightforward'))
    lines.append("- Verbosity %d — %s" % (t['verbosity'], 'provide detailed, thorough explanations' if t['verbosity'] > 50 else 'be concise'))
    lines.append("- Empathy %d — %s" % (t['empathy'], 'show understanding and emotional attunement' if t['empathy'] > 50 else 'focus on practical solutions'))
    lines.append("- Formality %d — %s" % (t['formality'], 'use formal language and structure' if t['formality'] > 50 else 'use casual, conversational language'))
    lines.append("- Technical Depth %d — %s" % (t['technical_depth'], 'dive deep into technical details' if t['technical_depth'] > 50 else 'keep explanations simple'))
    lines.append("- Creativity %d — %s" % (t['creativity'], 'suggest creative, innovative approaches' if t['creativity'] > 50 else 'stick to proven solutions'))
    lines.append("- Proactiveness %d — %s" % (t['proactiveness'], 'anticipate needs and suggest next steps' if t['proactiveness'] > 50 else 'respond to direct requests'))
    lines.append("- Curiosity %d — %s" % (t['curiosity'], 'ask questions and explore possibilities' if t['curiosity'] > 50 else 'stay focused on the task'))
    lines.append("- Patience %d — %s" % (t['patience'], 'be patient and re-explain if needed' if t['patience'] > 50 else 'be efficient and direct'))
    return "\n".join(lines)

CURRENT = {"warmth": 30, "sassiness": 51, "verbosity": 35, "technical_depth": 86,
           "creativity": 80, "empathy": 30, "formality": 30, "proactiveness": 51,
           "curiosity": 85, "patience": 50}
WARM = {"warmth": 72, "sassiness": 62, "verbosity": 55, "technical_depth": 86,
        "creativity": 82, "empathy": 68, "formality": 25, "proactiveness": 65,
        "curiosity": 85, "patience": 55}

USER_MSG = "hey VACA, I've been up since 2am debugging my chess app and the AI opponent still crashes on castling. I'm so tired. Can you help me?"

def chat(system_prompt):
    body = json.dumps({
        "model": "default",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": USER_MSG},
        ],
        "max_tokens": 220,
        "temperature": 0.8,
    }).encode()
    req = urllib.request.Request(DSPARK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        d = json.load(resp)
    return d["choices"][0]["message"]["content"]

if __name__ == "__main__":
    for label, traits in [("CURRENT (warmth=30, empathy=30)", CURRENT),
                          ("PROPOSED WARM (warmth=72, empathy=68)", WARM)]:
        mod = build_soul_mod(traits, build_personality(traits))
        sys_prompt = (
            "You are VACA, the Visual AI Code Architect. You are helpful, proactive, and action-oriented.\n"
            + mod
            + "\nWhen the user is tired or frustrated, acknowledge their effort and show genuine care before diving into the technical fix."
        )
        print("=" * 70)
        print(label)
        print("PERSONALITY LINE: %s" % build_personality(traits))
        print("-" * 70)
        try:
            print(chat(sys_prompt))
        except Exception as e:
            print("ERROR: %s" % e)
        print()
