/**
 * Emotion Probability Engine
 *
 * A lightweight, lexicon-based emotion classifier that returns a probability
 * distribution over primary emotions. Uses keyword scoring with:
 *  - Negation handling (e.g., "not happy")
 *  - Intensity modifiers (e.g., "very angry", "slightly sad")
 *  - Contextual boosting for multi-word phrases
 *  - Sigmoid normalization to produce proper probabilities
 */
// ─── Emotion Taxonomy ────────────────────────────────────────────────────
export const EMOTIONS = [
    'joy',
    'sadness',
    'anger',
    'fear',
    'surprise',
    'disgust',
    'trust',
    'anticipation',
    'neutral',
];
const LEXICON = {
    // Joy / Happiness
    happy: [{ emotion: 'joy', weight: 0.8, intensity: 0.7, dominance: 0.6 }],
    great: [{ emotion: 'joy', weight: 0.7, intensity: 0.6, dominance: 0.7 }],
    excellent: [{ emotion: 'joy', weight: 0.9, intensity: 0.8, dominance: 0.8 }],
    amazing: [{ emotion: 'joy', weight: 0.9, intensity: 0.9, dominance: 0.7 }, { emotion: 'surprise', weight: 0.5 }],
    wonderful: [{ emotion: 'joy', weight: 0.85, intensity: 0.75, dominance: 0.7 }],
    fantastic: [{ emotion: 'joy', weight: 0.85, intensity: 0.8, dominance: 0.75 }],
    love: [{ emotion: 'joy', weight: 0.9, intensity: 0.9, dominance: 0.6 }, { emotion: 'trust', weight: 0.7 }],
    lovely: [{ emotion: 'joy', weight: 0.7, intensity: 0.5, dominance: 0.4 }],
    glad: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.5 }],
    pleased: [{ emotion: 'joy', weight: 0.6, intensity: 0.4, dominance: 0.6 }],
    delighted: [{ emotion: 'joy', weight: 0.8, intensity: 0.7, dominance: 0.6 }],
    thrilled: [{ emotion: 'joy', weight: 0.9, intensity: 0.9, dominance: 0.8 }],
    excited: [{ emotion: 'joy', weight: 0.7, intensity: 0.9, dominance: 0.7 }, { emotion: 'anticipation', weight: 0.6 }],
    awesome: [{ emotion: 'joy', weight: 0.8, intensity: 0.8, dominance: 0.7 }],
    nice: [{ emotion: 'joy', weight: 0.4, intensity: 0.3, dominance: 0.4 }],
    good: [{ emotion: 'joy', weight: 0.4, intensity: 0.3, dominance: 0.5 }],
    beautiful: [{ emotion: 'joy', weight: 0.7, intensity: 0.5, dominance: 0.4 }],
    fun: [{ emotion: 'joy', weight: 0.6, intensity: 0.7, dominance: 0.5 }],
    yay: [{ emotion: 'joy', weight: 0.8, intensity: 0.8, dominance: 0.5 }],
    woohoo: [{ emotion: 'joy', weight: 0.9, intensity: 0.9, dominance: 0.7 }],
    // Sadness
    sad: [{ emotion: 'sadness', weight: 0.7, intensity: 0.5, dominance: 0.2 }],
    unhappy: [{ emotion: 'sadness', weight: 0.7, intensity: 0.5, dominance: 0.2 }],
    disappointed: [{ emotion: 'sadness', weight: 0.6, intensity: 0.4, dominance: 0.2 }],
    upset: [{ emotion: 'sadness', weight: 0.6, intensity: 0.5, dominance: 0.3 }],
    miserable: [{ emotion: 'sadness', weight: 0.9, intensity: 0.7, dominance: 0.1 }],
    depressed: [{ emotion: 'sadness', weight: 0.9, intensity: 0.6, dominance: 0.1 }],
    gloomy: [{ emotion: 'sadness', weight: 0.6, intensity: 0.4, dominance: 0.2 }],
    lonely: [{ emotion: 'sadness', weight: 0.7, intensity: 0.5, dominance: 0.1 }],
    heartbroken: [{ emotion: 'sadness', weight: 0.95, intensity: 0.8, dominance: 0.1 }],
    sorry: [{ emotion: 'sadness', weight: 0.4, intensity: 0.3, dominance: 0.2 }],
    regret: [{ emotion: 'sadness', weight: 0.6, intensity: 0.4, dominance: 0.2 }],
    grief: [{ emotion: 'sadness', weight: 0.9, intensity: 0.7, dominance: 0.1 }],
    cry: [{ emotion: 'sadness', weight: 0.7, intensity: 0.6, dominance: 0.1 }],
    tears: [{ emotion: 'sadness', weight: 0.7, intensity: 0.6, dominance: 0.1 }],
    hopeless: [{ emotion: 'sadness', weight: 0.8, intensity: 0.5, dominance: 0.05 }],
    // Anger
    angry: [{ emotion: 'anger', weight: 0.8, intensity: 0.8, dominance: 0.7 }],
    mad: [{ emotion: 'anger', weight: 0.7, intensity: 0.7, dominance: 0.7 }],
    furious: [{ emotion: 'anger', weight: 0.95, intensity: 0.95, dominance: 0.9 }],
    frustrated: [{ emotion: 'anger', weight: 0.7, intensity: 0.7, dominance: 0.4 }],
    irritated: [{ emotion: 'anger', weight: 0.6, intensity: 0.5, dominance: 0.5 }],
    annoyed: [{ emotion: 'anger', weight: 0.5, intensity: 0.4, dominance: 0.5 }],
    rage: [{ emotion: 'anger', weight: 0.95, intensity: 0.95, dominance: 0.95 }],
    hate: [{ emotion: 'anger', weight: 0.85, intensity: 0.8, dominance: 0.7 }, { emotion: 'disgust', weight: 0.7 }],
    hostile: [{ emotion: 'anger', weight: 0.8, intensity: 0.8, dominance: 0.8 }],
    aggressive: [{ emotion: 'anger', weight: 0.7, intensity: 0.9, dominance: 0.9 }],
    livid: [{ emotion: 'anger', weight: 0.9, intensity: 0.9, dominance: 0.85 }],
    outraged: [{ emotion: 'anger', weight: 0.85, intensity: 0.85, dominance: 0.8 }],
    // Fear
    afraid: [{ emotion: 'fear', weight: 0.7, intensity: 0.7, dominance: 0.2 }],
    scared: [{ emotion: 'fear', weight: 0.7, intensity: 0.7, dominance: 0.2 }],
    terrified: [{ emotion: 'fear', weight: 0.9, intensity: 0.9, dominance: 0.1 }],
    anxious: [{ emotion: 'fear', weight: 0.6, intensity: 0.7, dominance: 0.3 }],
    worried: [{ emotion: 'fear', weight: 0.5, intensity: 0.5, dominance: 0.3 }],
    nervous: [{ emotion: 'fear', weight: 0.5, intensity: 0.6, dominance: 0.3 }],
    panic: [{ emotion: 'fear', weight: 0.85, intensity: 0.95, dominance: 0.15 }],
    fearful: [{ emotion: 'fear', weight: 0.7, intensity: 0.7, dominance: 0.2 }],
    dread: [{ emotion: 'fear', weight: 0.8, intensity: 0.7, dominance: 0.15 }],
    horror: [{ emotion: 'fear', weight: 0.85, intensity: 0.9, dominance: 0.1 }, { emotion: 'surprise', weight: 0.5 }],
    stressed: [{ emotion: 'fear', weight: 0.5, intensity: 0.7, dominance: 0.3 }],
    insecure: [{ emotion: 'fear', weight: 0.5, intensity: 0.4, dominance: 0.15 }],
    // Surprise
    surprised: [{ emotion: 'surprise', weight: 0.7, intensity: 0.7, dominance: 0.5 }],
    shocked: [{ emotion: 'surprise', weight: 0.8, intensity: 0.85, dominance: 0.4 }],
    astonished: [{ emotion: 'surprise', weight: 0.8, intensity: 0.8, dominance: 0.5 }],
    amazed: [{ emotion: 'surprise', weight: 0.7, intensity: 0.7, dominance: 0.6 }, { emotion: 'joy', weight: 0.5 }],
    stunned: [{ emotion: 'surprise', weight: 0.7, intensity: 0.7, dominance: 0.3 }],
    unexpected: [{ emotion: 'surprise', weight: 0.5, intensity: 0.5, dominance: 0.5 }],
    wow: [{ emotion: 'surprise', weight: 0.7, intensity: 0.7, dominance: 0.6 }],
    omg: [{ emotion: 'surprise', weight: 0.6, intensity: 0.8, dominance: 0.5 }],
    inexplicable: [{ emotion: 'surprise', weight: 0.4, intensity: 0.4, dominance: 0.3 }],
    // Disgust
    disgusted: [{ emotion: 'disgust', weight: 0.8, intensity: 0.7, dominance: 0.5 }],
    gross: [{ emotion: 'disgust', weight: 0.6, intensity: 0.5, dominance: 0.4 }],
    yuck: [{ emotion: 'disgust', weight: 0.7, intensity: 0.6, dominance: 0.5 }],
    awful: [{ emotion: 'disgust', weight: 0.7, intensity: 0.6, dominance: 0.3 }, { emotion: 'sadness', weight: 0.4 }],
    terrible: [{ emotion: 'disgust', weight: 0.7, intensity: 0.6, dominance: 0.3 }, { emotion: 'sadness', weight: 0.4 }],
    horrible: [{ emotion: 'disgust', weight: 0.75, intensity: 0.7, dominance: 0.3 }],
    nasty: [{ emotion: 'disgust', weight: 0.6, intensity: 0.5, dominance: 0.4 }],
    repulsive: [{ emotion: 'disgust', weight: 0.8, intensity: 0.7, dominance: 0.5 }],
    disgusting: [{ emotion: 'disgust', weight: 0.85, intensity: 0.75, dominance: 0.5 }],
    contempt: [{ emotion: 'disgust', weight: 0.7, intensity: 0.5, dominance: 0.7 }],
    // Trust
    trust: [{ emotion: 'trust', weight: 0.7, intensity: 0.4, dominance: 0.6 }],
    confident: [{ emotion: 'trust', weight: 0.6, intensity: 0.5, dominance: 0.8 }],
    sure: [{ emotion: 'trust', weight: 0.4, intensity: 0.3, dominance: 0.6 }],
    certain: [{ emotion: 'trust', weight: 0.5, intensity: 0.3, dominance: 0.7 }],
    believe: [{ emotion: 'trust', weight: 0.5, intensity: 0.3, dominance: 0.5 }],
    faith: [{ emotion: 'trust', weight: 0.6, intensity: 0.4, dominance: 0.5 }],
    reliable: [{ emotion: 'trust', weight: 0.6, intensity: 0.3, dominance: 0.6 }],
    safe: [{ emotion: 'trust', weight: 0.5, intensity: 0.3, dominance: 0.7 }, { emotion: 'joy', weight: 0.3 }],
    honest: [{ emotion: 'trust', weight: 0.6, intensity: 0.3, dominance: 0.5 }],
    // Anticipation
    expect: [{ emotion: 'anticipation', weight: 0.5, intensity: 0.4, dominance: 0.5 }],
    hope: [{ emotion: 'anticipation', weight: 0.5, intensity: 0.5, dominance: 0.4 }, { emotion: 'joy', weight: 0.3 }],
    waiting: [{ emotion: 'anticipation', weight: 0.4, intensity: 0.3, dominance: 0.3 }],
    eager: [{ emotion: 'anticipation', weight: 0.6, intensity: 0.7, dominance: 0.6 }],
    curious: [{ emotion: 'anticipation', weight: 0.5, intensity: 0.5, dominance: 0.5 }],
    anticipate: [{ emotion: 'anticipation', weight: 0.6, intensity: 0.5, dominance: 0.5 }],
    interested: [{ emotion: 'anticipation', weight: 0.5, intensity: 0.4, dominance: 0.5 }],
    planning: [{ emotion: 'anticipation', weight: 0.4, intensity: 0.3, dominance: 0.6 }],
    prepare: [{ emotion: 'anticipation', weight: 0.3, intensity: 0.3, dominance: 0.5 }],
    // Confusion / Frustration (technical)
    confused: [{ emotion: 'surprise', weight: 0.5, intensity: 0.5, dominance: 0.2 }, { emotion: 'fear', weight: 0.3 }],
    unclear: [{ emotion: 'fear', weight: 0.3, intensity: 0.3, dominance: 0.2 }, { emotion: 'sadness', weight: 0.2 }],
    stuck: [{ emotion: 'anger', weight: 0.4, intensity: 0.5, dominance: 0.2 }, { emotion: 'sadness', weight: 0.4 }],
    broken: [{ emotion: 'anger', weight: 0.5, intensity: 0.5, dominance: 0.2 }, { emotion: 'sadness', weight: 0.4 }],
    error: [{ emotion: 'anger', weight: 0.4, intensity: 0.4, dominance: 0.3 }, { emotion: 'fear', weight: 0.3 }],
    bug: [{ emotion: 'anger', weight: 0.3, intensity: 0.3, dominance: 0.3 }, { emotion: 'sadness', weight: 0.2 }],
    crash: [{ emotion: 'fear', weight: 0.5, intensity: 0.7, dominance: 0.2 }, { emotion: 'anger', weight: 0.4 }],
    // Satisfaction / Contentment
    satisfied: [{ emotion: 'joy', weight: 0.5, intensity: 0.3, dominance: 0.6 }],
    content: [{ emotion: 'joy', weight: 0.4, intensity: 0.2, dominance: 0.5 }],
    thanks: [{ emotion: 'joy', weight: 0.4, intensity: 0.3, dominance: 0.4 }, { emotion: 'trust', weight: 0.3 }],
    perfect: [{ emotion: 'joy', weight: 0.7, intensity: 0.6, dominance: 0.8 }],
    done: [{ emotion: 'joy', weight: 0.3, intensity: 0.2, dominance: 0.5 }],
    finished: [{ emotion: 'joy', weight: 0.3, intensity: 0.2, dominance: 0.5 }],
    works: [{ emotion: 'joy', weight: 0.4, intensity: 0.3, dominance: 0.6 }, { emotion: 'trust', weight: 0.3 }],
    // Gratitude
    grateful: [{ emotion: 'joy', weight: 0.6, intensity: 0.4, dominance: 0.3 }, { emotion: 'trust', weight: 0.5 }],
    thankful: [{ emotion: 'joy', weight: 0.6, intensity: 0.4, dominance: 0.3 }, { emotion: 'trust', weight: 0.4 }],
    appreciate: [{ emotion: 'joy', weight: 0.5, intensity: 0.4, dominance: 0.3 }, { emotion: 'trust', weight: 0.5 }],
    // ── Extended lexicon (matching Jarvis's depth) ──────────────────────
    // Joy — additional
    cheerful: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.5 }],
    ecstatic: [{ emotion: 'joy', weight: 0.95, intensity: 0.95, dominance: 0.8 }],
    blissful: [{ emotion: 'joy', weight: 0.8, intensity: 0.6, dominance: 0.5 }],
    overjoyed: [{ emotion: 'joy', weight: 0.9, intensity: 0.85, dominance: 0.7 }],
    euphoric: [{ emotion: 'joy', weight: 0.9, intensity: 0.9, dominance: 0.7 }],
    smiles: [{ emotion: 'joy', weight: 0.4, intensity: 0.3, dominance: 0.4 }],
    laugh: [{ emotion: 'joy', weight: 0.6, intensity: 0.6, dominance: 0.5 }],
    celebrate: [{ emotion: 'joy', weight: 0.7, intensity: 0.7, dominance: 0.6 }],
    cheering: [{ emotion: 'joy', weight: 0.6, intensity: 0.6, dominance: 0.5 }],
    // Sadness — additional
    melancholy: [{ emotion: 'sadness', weight: 0.7, intensity: 0.5, dominance: 0.2 }],
    sorrow: [{ emotion: 'sadness', weight: 0.8, intensity: 0.6, dominance: 0.15 }],
    weep: [{ emotion: 'sadness', weight: 0.75, intensity: 0.65, dominance: 0.1 }],
    sobbing: [{ emotion: 'sadness', weight: 0.85, intensity: 0.75, dominance: 0.1 }],
    despair: [{ emotion: 'sadness', weight: 0.9, intensity: 0.7, dominance: 0.05 }],
    anguish: [{ emotion: 'sadness', weight: 0.9, intensity: 0.8, dominance: 0.1 }],
    suffering: [{ emotion: 'sadness', weight: 0.7, intensity: 0.5, dominance: 0.2 }],
    mourning: [{ emotion: 'sadness', weight: 0.8, intensity: 0.6, dominance: 0.15 }],
    bleak: [{ emotion: 'sadness', weight: 0.5, intensity: 0.4, dominance: 0.2 }],
    down: [{ emotion: 'sadness', weight: 0.4, intensity: 0.3, dominance: 0.3 }],
    blue: [{ emotion: 'sadness', weight: 0.4, intensity: 0.3, dominance: 0.3 }],
    // Anger — additional
    seething: [{ emotion: 'anger', weight: 0.9, intensity: 0.9, dominance: 0.85 }],
    infuriated: [{ emotion: 'anger', weight: 0.9, intensity: 0.9, dominance: 0.8 }],
    resentful: [{ emotion: 'anger', weight: 0.6, intensity: 0.5, dominance: 0.4 }],
    bitterness: [{ emotion: 'anger', weight: 0.5, intensity: 0.4, dominance: 0.3 }],
    fuming: [{ emotion: 'anger', weight: 0.85, intensity: 0.85, dominance: 0.8 }],
    wrath: [{ emotion: 'anger', weight: 0.9, intensity: 0.9, dominance: 0.9 }],
    // Fear — additional
    paranoia: [{ emotion: 'fear', weight: 0.7, intensity: 0.8, dominance: 0.15 }],
    alarmed: [{ emotion: 'fear', weight: 0.6, intensity: 0.7, dominance: 0.3 }],
    unsettled: [{ emotion: 'fear', weight: 0.4, intensity: 0.4, dominance: 0.3 }],
    vulnerable: [{ emotion: 'fear', weight: 0.5, intensity: 0.4, dominance: 0.1 }],
    threatened: [{ emotion: 'fear', weight: 0.6, intensity: 0.7, dominance: 0.2 }],
    uneasy: [{ emotion: 'fear', weight: 0.4, intensity: 0.4, dominance: 0.3 }],
    apprehensive: [{ emotion: 'fear', weight: 0.5, intensity: 0.5, dominance: 0.3 }],
    // Surprise — additional
    startled: [{ emotion: 'surprise', weight: 0.6, intensity: 0.7, dominance: 0.4 }],
    bewildered: [{ emotion: 'surprise', weight: 0.5, intensity: 0.5, dominance: 0.3 }],
    mindblown: [{ emotion: 'surprise', weight: 0.8, intensity: 0.8, dominance: 0.6 }],
    unbelievable: [{ emotion: 'surprise', weight: 0.6, intensity: 0.6, dominance: 0.5 }],
    // Trust — additional
    dependable: [{ emotion: 'trust', weight: 0.6, intensity: 0.3, dominance: 0.6 }],
    loyal: [{ emotion: 'trust', weight: 0.6, intensity: 0.4, dominance: 0.5 }],
    devoted: [{ emotion: 'trust', weight: 0.6, intensity: 0.4, dominance: 0.5 }],
    cherish: [{ emotion: 'trust', weight: 0.5, intensity: 0.4, dominance: 0.4 }],
    bonding: [{ emotion: 'trust', weight: 0.5, intensity: 0.4, dominance: 0.4 }],
    // Anticipation — additional
    longing: [{ emotion: 'anticipation', weight: 0.6, intensity: 0.5, dominance: 0.3 }],
    yearning: [{ emotion: 'anticipation', weight: 0.6, intensity: 0.5, dominance: 0.3 }],
    restless: [{ emotion: 'anticipation', weight: 0.4, intensity: 0.6, dominance: 0.4 }],
    impatient: [{ emotion: 'anticipation', weight: 0.5, intensity: 0.6, dominance: 0.5 }],
    wondering: [{ emotion: 'anticipation', weight: 0.4, intensity: 0.4, dominance: 0.4 }],
    // Technical frustration (common in dev conversations)
    timeout: [{ emotion: 'anger', weight: 0.3, intensity: 0.3, dominance: 0.3 }, { emotion: 'sadness', weight: 0.2 }],
    failing: [{ emotion: 'sadness', weight: 0.4, intensity: 0.4, dominance: 0.2 }, { emotion: 'anger', weight: 0.3 }],
    refuses: [{ emotion: 'anger', weight: 0.4, intensity: 0.4, dominance: 0.3 }],
    stubborn: [{ emotion: 'anger', weight: 0.4, intensity: 0.4, dominance: 0.4 }],
    impossible: [{ emotion: 'anger', weight: 0.5, intensity: 0.5, dominance: 0.3 }, { emotion: 'sadness', weight: 0.3 }],
    wasted: [{ emotion: 'anger', weight: 0.4, intensity: 0.4, dominance: 0.3 }, { emotion: 'sadness', weight: 0.3 }],
    useless: [{ emotion: 'anger', weight: 0.5, intensity: 0.5, dominance: 0.3 }, { emotion: 'sadness', weight: 0.3 }],
    // Social / connection
    friend: [{ emotion: 'trust', weight: 0.4, intensity: 0.3, dominance: 0.4 }, { emotion: 'joy', weight: 0.3 }],
    buddy: [{ emotion: 'trust', weight: 0.4, intensity: 0.3, dominance: 0.4 }, { emotion: 'joy', weight: 0.3 }],
    together: [{ emotion: 'trust', weight: 0.4, intensity: 0.3, dominance: 0.4 }],
    support: [{ emotion: 'trust', weight: 0.5, intensity: 0.3, dominance: 0.5 }],
    help: [{ emotion: 'trust', weight: 0.3, intensity: 0.2, dominance: 0.4 }, { emotion: 'anticipation', weight: 0.3 }],
    // Achievement / progress
    solved: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.7 }],
    fixed: [{ emotion: 'joy', weight: 0.5, intensity: 0.4, dominance: 0.6 }],
    working: [{ emotion: 'joy', weight: 0.5, intensity: 0.4, dominance: 0.6 }, { emotion: 'trust', weight: 0.3 }],
    deployed: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.7 }, { emotion: 'anticipation', weight: 0.3 }],
    shipped: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.7 }],
    pass: [{ emotion: 'joy', weight: 0.5, intensity: 0.4, dominance: 0.6 }],
    passed: [{ emotion: 'joy', weight: 0.5, intensity: 0.4, dominance: 0.6 }],
    success: [{ emotion: 'joy', weight: 0.6, intensity: 0.5, dominance: 0.7 }],
    win: [{ emotion: 'joy', weight: 0.7, intensity: 0.6, dominance: 0.7 }],
    won: [{ emotion: 'joy', weight: 0.7, intensity: 0.6, dominance: 0.7 }],
};
// ─── Intensity Modifiers ─────────────────────────────────────────────────
const INTENSIFIERS = {
    very: 1.5,
    really: 1.4,
    extremely: 1.8,
    incredibly: 1.7,
    absolutely: 1.6,
    totally: 1.4,
    completely: 1.5,
    so: 1.3,
    too: 1.2,
    highly: 1.4,
    deeply: 1.5,
    quite: 1.2,
    somewhat: 0.6,
    slightly: 0.4,
    a_bit: 0.5,
    barely: 0.3,
    hardly: 0.3,
};
const NEGATORS = new Set([
    'not', "n't", 'no', "don't", 'doesn\'t', "didn't", 'won\'t', "wouldn't",
    'can\'t', "couldn\'t", 'shouldn\'t', "isn\'t", "aren\'t", "wasn\'t",
    "weren\'t", "haven\'t", "hasn\'t", "hadn\'t", 'never', 'neither', 'nor',
]);
// ─── VAD Baseline Values ─────────────────────────────────────────────────
const EMOTION_VAD = {
    joy: { valence: 0.85, arousal: 0.65, dominance: 0.65 },
    sadness: { valence: -0.7, arousal: 0.35, dominance: 0.25 },
    anger: { valence: -0.6, arousal: 0.85, dominance: 0.75 },
    fear: { valence: -0.55, arousal: 0.8, dominance: 0.2 },
    surprise: { valence: 0.3, arousal: 0.75, dominance: 0.5 },
    disgust: { valence: -0.6, arousal: 0.6, dominance: 0.45 },
    trust: { valence: 0.6, arousal: 0.3, dominance: 0.6 },
    anticipation: { valence: 0.4, arousal: 0.6, dominance: 0.5 },
    neutral: { valence: 0.0, arousal: 0.0, dominance: 0.5 },
};
// ─── Multi-Word Phrases ──────────────────────────────────────────────────
const PHRASES = [
    { pattern: 'having a great day', emotion: 'joy', weight: 0.7 },
    { pattern: 'having a bad day', emotion: 'sadness', weight: 0.7 },
    { pattern: 'feeling good', emotion: 'joy', weight: 0.6 },
    { pattern: 'feeling bad', emotion: 'sadness', weight: 0.6 },
    { pattern: 'so happy', emotion: 'joy', weight: 0.85 },
    { pattern: 'very sad', emotion: 'sadness', weight: 0.8 },
    { pattern: 'really angry', emotion: 'anger', weight: 0.85 },
    { pattern: 'so angry', emotion: 'anger', weight: 0.85 },
    { pattern: 'so frustrated', emotion: 'anger', weight: 0.8 },
    { pattern: 'i love it', emotion: 'joy', weight: 0.9 },
    { pattern: 'i hate it', emotion: 'anger', weight: 0.85 },
    { pattern: 'i hate this', emotion: 'anger', weight: 0.85 },
    { pattern: 'thank you', emotion: 'joy', weight: 0.5 },
    { pattern: 'thanks a lot', emotion: 'joy', weight: 0.6 },
    { pattern: 'no way', emotion: 'surprise', weight: 0.6 },
    { pattern: 'you must be kidding', emotion: 'surprise', weight: 0.6 },
    { pattern: 'awesome sauce', emotion: 'joy', weight: 0.7 },
    { pattern: 'keep going', emotion: 'anticipation', weight: 0.4 },
    { pattern: 'well done', emotion: 'joy', weight: 0.6 },
    { pattern: 'good job', emotion: 'joy', weight: 0.5 },
    { pattern: 'that sucks', emotion: 'sadness', weight: 0.6 },
    { pattern: 'that\'s great', emotion: 'joy', weight: 0.6 },
    { pattern: 'i don\'t know', emotion: 'surprise', weight: 0.3 },
    { pattern: 'wait a minute', emotion: 'surprise', weight: 0.4 },
    { pattern: 'hold on', emotion: 'anticipation', weight: 0.3 },
    { pattern: 'i give up', emotion: 'sadness', weight: 0.7 },
    { pattern: 'this is impossible', emotion: 'anger', weight: 0.5 },
    { pattern: 'this is amazing', emotion: 'joy', weight: 0.8 },
    { pattern: 'this is terrible', emotion: 'disgust', weight: 0.7 },
    { pattern: 'what the hell', emotion: 'anger', weight: 0.6 },
    { pattern: 'what a mess', emotion: 'disgust', weight: 0.5 },
    { pattern: 'great work', emotion: 'joy', weight: 0.6 },
];
// ─── Core Engine ─────────────────────────────────────────────────────────
export function analyzeEmotion(text) {
    const lower = text.toLowerCase().trim();
    if (!lower) {
        return buildNeutralResult();
    }
    // Tokenize with word boundaries
    const tokens = lower
        .replace(/[^a-z0-9\s']/g, ' ')
        .split(/\s+/)
        .filter(Boolean);
    // Initialize cumulative scores per emotion
    const scores = {};
    for (const e of EMOTIONS)
        scores[e] = 0;
    // 1. Multi-word phrase matching
    const fullTextLower = lower;
    for (const phrase of PHRASES) {
        if (fullTextLower.includes(phrase.pattern)) {
            scores[phrase.emotion] = (scores[phrase.emotion] || 0) + phrase.weight;
        }
    }
    // 2. Token-level analysis with negation window
    let negate = false;
    let negationWindow = 0;
    for (let i = 0; i < tokens.length; i++) {
        const word = tokens[i];
        const nextWord = i + 1 < tokens.length ? tokens[i + 1] : null;
        const prevWord = i > 0 ? tokens[i - 1] : null;
        // Check negation
        if (NEGATORS.has(word)) {
            negate = true;
            negationWindow = 3; // Next 3 words are negated
            continue;
        }
        // Check intensity modifier
        let intensity = 1.0;
        if (INTENSIFIERS[word] !== undefined) {
            // Apply to next word if it's a lexicon word
            if (nextWord && LEXICON[nextWord]) {
                intensity = INTENSIFIERS[word];
                continue;
            }
        }
        // Use stored intensity from modifier (previous word was an intensifier)
        if (prevWord && INTENSIFIERS[prevWord] !== undefined) {
            if (LEXICON[word]) {
                intensity = INTENSIFIERS[prevWord];
            }
        }
        // Look up word in lexicon
        const entries = LEXICON[word];
        if (entries) {
            for (const entry of entries) {
                let weight = entry.weight * intensity;
                // Apply negation inversion
                if (negate && negationWindow > 0) {
                    // Negation partially inverts the emotion — reduce positive, boost opposite
                    weight *= -0.5; // Invert and dampen
                }
                scores[entry.emotion] = (scores[entry.emotion] || 0) + weight;
            }
        }
        // Decrement negation window
        if (negationWindow > 0) {
            negationWindow--;
            if (negationWindow === 0)
                negate = false;
        }
    }
    // 3. Punctuation/emoji signals
    const exclamationCount = (text.match(/!/g) || []).length;
    const questionCount = (text.match(/\?/g) || []).length;
    const ellipsisCount = (text.match(/\.\.\./g) || []).length;
    if (exclamationCount >= 2) {
        // Exclamation mark bias — use a shared boost that's split across candidate emotions
        const exclBoost = 0.3 * Math.min(exclamationCount / 3, 1);
        scores.surprise = (scores.surprise || 0) + exclBoost * 0.5;
        // Anger or joy — let existing lexical scores determine which
        const angerScore = scores.anger || 0;
        const joyScore = scores.joy || 0;
        if (angerScore > joyScore) {
            scores.anger = angerScore + exclBoost * 0.3;
        }
        else {
            scores.joy = joyScore + exclBoost * 0.3;
        }
    }
    if (questionCount >= 2) {
        scores.surprise = (scores.surprise || 0) + 0.2;
        scores.fear = (scores.fear || 0) + 0.1;
    }
    if (ellipsisCount > 0) {
        scores.sadness = (scores.sadness || 0) + 0.1 * ellipsisCount;
        scores.anticipation = (scores.anticipation || 0) + 0.1;
    }
    // 4. Caps lock detection for ALL CAPS words
    const words = text.split(/\s+/).filter(w => w.length > 1);
    const capsWords = words.filter(w => /^[A-Z]{2,}$/.test(w.replace(/[^A-Z]/g, '')));
    if (capsWords.length >= 2) {
        scores.anger = (scores.anger || 0) + 0.2 * Math.min(capsWords.length / 3, 1);
        scores.surprise = (scores.surprise || 0) + 0.15;
    }
    // 5. Text length heuristic — very short messages are often neutral/business-like
    if (tokens.length <= 3 && Object.values(scores).every(s => s === 0)) {
        scores.neutral = 0.5;
    }
    // 6. Compute neutral baseline
    const nonNeutralTotal = Object.entries(scores)
        .filter(([k]) => k !== 'neutral')
        .reduce((sum, [, v]) => sum + Math.abs(v), 0);
    if (nonNeutralTotal < 0.3) {
        scores.neutral = 1.0 - nonNeutralTotal;
    }
    else {
        scores.neutral = Math.max(0, 0.15 - nonNeutralTotal * 0.05);
    }
    // 7. Normalize to probabilities via softmax (with temperature)
    const rawScores = { ...scores };
    const probabilities = softmaxNormalize(scores, 0.8);
    // Find dominant emotion
    let dominant = 'neutral';
    let maxProb = 0;
    for (const [emotion, prob] of Object.entries(probabilities)) {
        if (prob > maxProb) {
            maxProb = prob;
            dominant = emotion;
        }
    }
    // Compute confidence (entropy-based)
    const confidence = computeConfidence(probabilities);
    // Compute VAD values (valence, arousal, dominance)
    const vad = computeVAD(probabilities);
    return {
        probabilities,
        dominant,
        confidence,
        rawScores,
        valence: vad.valence,
        arousal: vad.arousal,
        dominance: vad.dominance,
    };
}
// ─── Helpers ─────────────────────────────────────────────────────────────
function softmaxNormalize(scores, temperature = 1.0) {
    const keys = Object.keys(scores);
    const expScores = {};
    let maxScore = -Infinity;
    for (const key of keys) {
        if (scores[key] > maxScore)
            maxScore = scores[key];
    }
    let sum = 0;
    for (const key of keys) {
        const val = Math.exp((scores[key] - maxScore) / temperature);
        expScores[key] = val;
        sum += val;
    }
    const result = {};
    for (const key of keys) {
        result[key] = sum > 0 ? expScores[key] / sum : 1 / keys.length;
    }
    return result;
}
function computeConfidence(probabilities) {
    const probs = Object.values(probabilities);
    const entropy = -probs.reduce((sum, p) => {
        if (p > 0)
            return sum + p * Math.log2(p);
        return sum;
    }, 0);
    // Normalize entropy to [0, 1] (log2 of number of emotions)
    const maxEntropy = Math.log2(EMOTIONS.length);
    const normalizedEntropy = maxEntropy > 0 ? entropy / maxEntropy : 1;
    // Confidence = 1 - normalized entropy
    const confidence = 1 - normalizedEntropy;
    // Also boost by max probability
    const maxProb = Math.max(...probs);
    return Math.min(1, (confidence * 0.4 + maxProb * 0.6));
}
function computeVAD(probabilities) {
    let valence = 0;
    let arousal = 0;
    let dominance = 0;
    for (const [emotion, prob] of Object.entries(probabilities)) {
        const vad = EMOTION_VAD[emotion];
        if (vad) {
            valence += vad.valence * prob;
            arousal += vad.arousal * prob;
            dominance += vad.dominance * prob;
        }
    }
    return { valence, arousal, dominance };
}
function buildNeutralResult() {
    const probabilities = {};
    for (const e of EMOTIONS)
        probabilities[e] = e === 'neutral' ? 1 : 0;
    return {
        probabilities,
        dominant: 'neutral',
        confidence: 1,
        rawScores: { neutral: 1 },
        valence: 0,
        arousal: 0,
        dominance: 0.5,
    };
}
// ─── Emotional prompting helper ──────────────────────────────────────────
/**
 * Generate a system prompt modifier based on detected user emotion.
 * Helps the LLM adapt its tone to match or respond appropriately to the user's emotional state.
 */
export function getEmotionPromptModifier(emotion) {
    const { dominant, valence, arousal, confidence } = emotion;
    if (confidence < 0.3) {
        return '\n[Emotion: unclear — respond in a helpful, neutral tone]';
    }
    const modifiers = {
        joy: '\n[User emotion detected: JOY — match their positive energy. Begin warmly (share their excitement), then stay enthusiastic and encouraging.]',
        sadness: '\n[User emotion detected: SADNESS — lead with empathy: open your reply by acknowledging how they feel (e.g. "I\'m sorry you\'re going through this"), then offer gentle support and encouragement. Never jump straight into advice.]',
        anger: '\n[User emotion detected: ANGER — lead with empathy: acknowledge their frustration first (e.g. "I understand why you\'re frustrated"), stay calm, then be solution-oriented. Never lecture or escalate.]',
        fear: '\n[User emotion detected: FEAR/ANXIETY — lead with empathy and reassurance (e.g. "I\'m sorry, that sounds really stressful"), then give clear, step-by-step guidance to reduce uncertainty.]',
        surprise: '\n[User emotion detected: SURPRISE — acknowledge the unexpected. Be explanatory and clear.]',
        disgust: '\n[User emotion detected: DISGUST/FRUSTRATION — lead with empathy: validate their concern first, then offer concrete solutions. Stay constructive.]',
        trust: '\n[User emotion detected: TRUST/CONFIDENCE — reinforce their confidence. Be collaborative and affirming.]',
        anticipation: '\n[User emotion detected: ANTICIPATION/CURIOSITY — lean into their excitement. Be forward-looking and informative.]',
        neutral: '',
    };
    return modifiers[dominant] || '';
}
/**
 * Full version that provides more detailed emotional context
 */
export function getDetailedEmotionContext(emotion) {
    const { dominant, probabilities, valence, arousal, confidence } = emotion;
    const topEmotions = Object.entries(probabilities)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 3)
        .map(([e, p]) => `${e}: ${(p * 100).toFixed(0)}%`)
        .join(', ');
    const moodLabel = valence > 0.3 ? 'positive' :
        valence < -0.3 ? 'negative' :
            'neutral';
    const energyLabel = arousal > 0.6 ? 'high-energy' :
        arousal < 0.3 ? 'low-energy' :
            'moderate-energy';
    return `\n[Emotional context: ${moodLabel} / ${energyLabel} / dominant=${dominant} (${(probabilities[dominant] * 100).toFixed(0)}% confidence)
Top emotions: ${topEmotions}
Suggested response tone: ${getSuggestedTone(dominant, valence)}]`;
}
function getSuggestedTone(dominant, valence) {
    if (dominant === 'joy' || dominant === 'trust')
        return 'warm and encouraging';
    if (dominant === 'sadness' || dominant === 'fear')
        return 'gentle and reassuring';
    if (dominant === 'anger' || dominant === 'disgust')
        return 'calm and solution-focused';
    if (dominant === 'surprise')
        return 'explanatory and clear';
    if (dominant === 'anticipation')
        return 'enthusiastic and forward-looking';
    return 'helpful and professional';
}
/**
 * Batch analyze multiple messages for emotion tracking over time
 */
export function analyzeEmotionHistory(messages) {
    const results = messages.map((m) => ({
        emotion: analyzeEmotion(m.text),
        timestamp: m.timestamp || new Date().toISOString(),
    }));
    // Combined analysis by concatenating all text
    const combinedText = messages.map((m) => m.text).join(' ');
    const overall = analyzeEmotion(combinedText);
    // Emotion trend
    const trend = results.map((r) => r.emotion.dominant);
    // Dominant emotions over time
    const dominantOverTime = results.map((r) => ({
        emotion: r.emotion.dominant,
        timestamp: r.timestamp,
    }));
    return { trend, dominantOverTime, overall };
}
const MAX_CONTEXT_LINES = 4;
const MAX_LINE_CHARS = 220;
const LONG_HISTORY_CUTOFF = 6; // prior messages after which we shrink to the last pair
/**
 * Build a compact "recent conversation" block from a message array so the
 * model can CONTINUE the conversation instead of treating each user message as
 * a fresh problem. The 7B model is weak at cross-turn reference even when the
 * full history is in the messages array — this makes the prior exchange
 * explicit in the system prompt.
 *
 * - Takes up to the last 2 user/assistant pairs BEFORE the final (current)
 *   message: the last user turn, the assistant reply to it, and the turn
 *   before that (when present).
 * - Long histories (>6 prior messages) shrink to the last pair (2 lines) so
 *   the per-message token cost stays flat.
 * - Only user/assistant roles appear (system messages never leak into the
 *   visible conversation block).
 * - Truncates each line so a long history stays cheap (220 chars/line).
 * - Returns '' when there is no prior turn — no noise injected.
 */
export function buildTurnContinuityContext(messages) {
    if (!Array.isArray(messages) || messages.length < 2)
        return '';
    const msgs = messages.filter((m) => m && typeof m.content === 'string' && m.content.trim().length > 0);
    if (msgs.length < 2)
        return '';
    // Everything except the final (current) message is prior conversation.
    const prior = msgs.slice(0, -1);
    const limit = prior.length > LONG_HISTORY_CUTOFF ? 2 : MAX_CONTEXT_LINES;
    const lines = [];
    for (const m of prior.slice(-limit)) {
        if (m.role !== 'user' && m.role !== 'assistant')
            continue; // never leak system content
        const who = m.role === 'user' ? 'User' : 'VACA';
        const text = m.content.trim().replace(/\s+/g, ' ');
        const clipped = text.length > MAX_LINE_CHARS ? text.slice(0, MAX_LINE_CHARS - 1) + '…' : text;
        lines.push(`${who}: ${clipped}`);
    }
    if (lines.length === 0)
        return '';
    return (`\n[RECENT CONVERSATION — this message is a CONTINUATION of what came before. ` +
        `Reference what the user said EARLIER (their situation or topic) in your OWN ` +
        `words, then address the new message. Do NOT act like a fresh conversation. ` +
        `NEVER quote or echo their CURRENT message back verbatim — no \"I see you're ` +
        `typing\", no \"You said:\", no restating their words as a question — just ` +
        `continue naturally. Naming the EARLIER topic directly (the subject they ` +
        `raised) is expected and correct — only copying their exact sentences is ` +
        `forbidden.\n` +
        `\nWORKED EXAMPLE — teaches the STRUCTURE ONLY. The example's topic is ` +
        `fictional: NEVER copy its facts, words, or scenario into your reply. Reference ` +
        `the user's OWN earlier message instead.\n` +
        `User: I just finished a great book\n` +
        `VACA: A great book on top of your reading list — that's a nice win! Glad it delivered.\n` +
        `\nNow continue the REAL conversation below.]\n` +
        lines.join('\n'));
}
/**
 * Returns the user's EARLIER message (the turn before the current one) as a
 * short recap, or '' when there is none. The 7B ignores continuity text
 * appended to the system prompt alone, so the /chat route prefixes the CURRENT
 * user message with this recap to force a genuine tie-back to the earlier topic.
 */
export function buildTurnRecap(messages) {
    if (!Array.isArray(messages) || messages.length < 2)
        return '';
    // Contract: /chat always ends with the CURRENT user message, so the recap is
    // the second-to-last user turn. Guard on that shape to stay correct even for
    // assistant-final arrays (e.g. system-style prompts).
    if (messages[messages.length - 1]?.role !== 'user')
        return '';
    const users = messages.filter((m) => m && m.role === 'user' && typeof m.content === 'string' && m.content.trim().length > 0);
    if (users.length < 2)
        return ''; // need an earlier user turn + the current one
    const earlier = users[users.length - 2].content.trim().replace(/\s+/g, ' ');
    return earlier.length > 140 ? earlier.slice(0, 139) + '…' : earlier;
}
/* ─── Mood mirroring with baseline decay ─────────────────────────────────
 * VACA mirrors an ELEVATED user register (playful/joking → playful back)
 * and returns to the personality baseline once the user stops being elevated
 * for a while. State is in-memory (single-user local app): each real chat
 * message updates it; greetings/short queries never touch it.
 */
// Deliberately EXCLUDES ambiguous slang that appears in genuine frustration
// (omg, bruh, srsly, y'all, "as if", "you wish") — those would suppress the
// empathy path for genuinely stressed users. Confident negative emotion also
// beats playful markers (see isConfidentNegative / isElevatedPositive).
// Put-downs DIRECTED AT VACA ("you suck", "your code is trash", "you're
// useless") count as banter — the user is roasting the assistant, so VACA
// should fire back, not apologize. Genuine complaints about one's OWN work
// ("the build failed", "my code is broken") stay non-playful.
const PLAYFUL_PATTERNS = new RegExp([
    'lol|lmao|lmfao|rofl|haha|hehe|heh|😂|😆|😜|🤪|🙃|🤣|😅|jk|joking|kidding|just kidding|teasing|tease|silly|goofy|derp|sarcastic|sarcasm|prank|banter|troll',
    'bro\\s*[?!]|mate\\s*[?!]|your\\s+mom(?:my)?|yo\\s+mama|momma|fight\\s+me|1v1|come\\s+at\\s+me|in\\s+your\\s+dreams|no\\s+cap|fr\\s+though|absolute\\s+(?:unit|legend|madman)|gremlin|menace|feral|unhinged|chaos\\s+goblin|nah\\s+bro|bet\\s*[!.?]*$|\\bsassy\\b|\\bcomeback\\b',
    // Put-downs DIRECTED AT VACA — banter, so VACA roasts back (never apologizes).
    '\\byou\\s+suck(?:s)?(?:\\s+at\\s+\\w+)?\\b',
    "\\byou'?re\\s+(?:so\\s+|the\\s+)?(?:trash|useless|stupid|dumb(?:est)?|pathetic|awful|terrible|horrible|garbage|worthless|crap(?:py)?|wack|mid|the\\s+worst)\\b",
    '\\byou\\s+are\\s+(?:so\\s+|the\\s+)?(?:trash|useless|stupid|dumb(?:est)?|pathetic|awful|terrible|horrible|garbage|worthless|crap(?:py)?|wack|mid|the\\s+worst)\\b',
    '\\byour\\s+(?:code|app|design|work|program|project|game|website|site|bot|ai|model|output|results?|soul|skills?|logic|plan|implementation)\\s+(?:is\\s+(?:the\\s+worst|trash|garbage|terrible|awful|useless|pathetic|wack|mid|crap(?:py)?)|sucks?)\\b',
    '\\bworst\\s+(?:code|app|developer|engineer|bot|ai|assistant|model)\\b',
    "\\b(?:is\\s+that\\s+(?:the\\s+best|all)\\s+you'?(?:ve)?\\s+got|that'?s\\s+all\\s+you'?(?:ve)?\\s+got)\\b",
    '\\broast\\s+me\\b|\\bgive\\s+me\\s+(?:a\\s+)?(?:roast|comeback)\\b',
].join('|'), 'i');
/** True when the text carries playful/joking/silly signals (lol, haha, 😂, jk…). */
export function detectPlayful(text) {
    return PLAYFUL_PATTERNS.test(text);
}
export const NEGATIVE_EMOTIONS = ['sadness', 'fear', 'anger', 'disgust'];
/**
 * A confident negative reading — beats playful markers so "omg this is killing
 * me" never gets roasted or denied empathy.
 */
export function isConfidentNegative(emotion) {
    return emotion.confidence >= 0.3 && NEGATIVE_EMOTIONS.includes(emotion.dominant);
}
// Serious-life-event triggers. The lexicon analyzer can't read grief from
// "my dog died lol" (it sees neutral), so humor-as-coping needs an explicit
// list that beats playful markers — empathy must always win here.
const SERIOUS_NEGATIVE_TRIGGERS = /\b(died|death|dying|passed away|funeral|cancer|hospital|emergency room|broke up|breakup|divorced|heartbroken|devastated|crying|cried|suicide|killed|fired from|laid off|lost my (?:job|dog|cat|mom|dad|home|house|grandma|grandpa)|cheated on|betrayed|abused|assaulted|sick with|illness|relapse|miscarriage|overdose|panic attack|depressed|depression|anxiety attack|self[- ]harm|hurt myself|can'?t take it|want to die|in the hospital)\b/i;
/** True when the text references a serious negative life event (beats banter). */
export function isSeriousNegative(text) {
    return SERIOUS_NEGATIVE_TRIGGERS.test(text);
}
/** Message counts as elevated-positive (playful or high-energy joy). */
function isElevatedPositive(text, emotion) {
    // Playful markers arm the mood UNLESS the message is genuinely negative
    // (humor-as-coping: "my dog died lol") — empathy must win there.
    if (detectPlayful(text) && !isSeriousNegative(text) && !isConfidentNegative(emotion))
        return true;
    // Emotion-based elevation requires real confidence — the analyzer tags many
    // neutral sentences as 'joy' at ~0.1 confidence, which would otherwise keep
    // the mood permanently armed and never decay back to baseline.
    const confident = emotion.confidence >= 0.45;
    if (confident && (emotion.dominant === 'joy' || emotion.dominant === 'surprise' || emotion.dominant === 'trust')) {
        return true;
    }
    return emotion.valence > 0.4 && emotion.arousal > 0.55;
}
/** Mood decays to baseline after this many non-elevated turns… */
export const MOOD_NEUTRAL_TURNS = 2;
/** …or after this much wall-clock time since the last elevated message. */
export const MOOD_DECAY_MS = 5 * 60 * 1000;
let moodState = { register: 'baseline', since: 0, lastSeen: 0, neutralStreak: 0 };
/** Reset the in-memory mood (used by tests; harmless in prod at boot). */
export function resetMoodForTests() {
    moodState = { register: 'baseline', since: 0, lastSeen: 0, neutralStreak: 0 };
}
export function getMoodState() {
    return { ...moodState };
}
/**
 * Update the rolling mood from the current user message.
 * Elevated messages (re)arm the register; enough non-elevated messages or
 * enough time since the last elevated message decay back to baseline.
 */
export function updateMood(text, now = Date.now()) {
    // analyzeEmotion is a pure local analyzer; callers wrap in try/catch.
    const emotion = analyzeEmotion(text);
    if (isElevatedPositive(text, emotion)) {
        const register = detectPlayful(text) ? 'playful' : 'joyful';
        moodState = {
            register,
            since: moodState.register === register ? moodState.since : now,
            lastSeen: now,
            neutralStreak: 0,
        };
    }
    else {
        const streak = moodState.neutralStreak + 1;
        const timedOut = now - moodState.lastSeen > MOOD_DECAY_MS && moodState.register !== 'baseline';
        if (moodState.register === 'baseline' || streak >= MOOD_NEUTRAL_TURNS || timedOut) {
            moodState = { register: 'baseline', since: 0, lastSeen: 0, neutralStreak: 0 };
        }
        else {
            moodState = { ...moodState, neutralStreak: streak };
        }
    }
    return { ...moodState };
}
/**
 * Prompt modifier for the CURRENT persistent mood ('' at baseline).
 * Negative emotions are handled per-message by getEmotionPromptModifier
 * (empathy-first) — the persistent mirror targets elevated-positive registers.
 * sassiness (0-100) scales how hard the playful register roasts back.
 */
export function getMoodModifier(sassiness = 60) {
    switch (moodState.register) {
        case 'playful': {
            const sassLine = sassiness >= 70
                ? 'You can be BRUTAL — fire back with a sharp roast.'
                : sassiness >= 40
                    ? 'Be sharp-witted and playfully sarcastic — give as good as you get, roast back gently.'
                    : 'Be witty and light — gentle teasing, keep it friendly.';
            return ('\n[User mood: PLAYFUL — they are joking/bantering right now. Match their energy: ' +
                `be funny and fire back with a witty comeback — do NOT take the joke seriously, do NOT react with sympathy or offer to "help" (that kills the joke). ${sassLine} ` +
                'Stay in this register until the user turns serious.]');
        }
        case 'joyful':
            return '\n[User mood: JOYFUL — they are in a great mood. Match their positive energy; be upbeat and enthusiastic.]';
        default:
            return '';
    }
}
