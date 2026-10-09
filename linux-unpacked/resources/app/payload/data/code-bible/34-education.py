# -*- coding: utf-8 -*-
"""
Code Bible — Category 34: Education & Learning (atomic).
Convention: pure helpers for quizzes, grading, spaced repetition, progress; no deps.
"""
CHUNKS = [
    {
        "id": "edu-grading-scale",
        "name": "Percentage-to-Letter Grader",
        "category": "edu",
        "lang": "typescript",
        "when": "Converting a percentage score to a letter grade with boundaries",
        "why": "Atomic grader — score in, letter out; boundaries override for pass/fail scales",
        "tags": ["edu", "grade", "letter", "score", "scale"],
        "iface": r'''export function letterGrade(pct: number, boundaries?: Record<string, number>): string''',
        "code": r'''export function letterGrade(pct: number, boundaries: Record<string, number> = { A: 90, B: 80, C: 70, D: 60 }) {
  const entries = Object.entries(boundaries).sort((a, b) => b[1] - a[1]);
  for (const [grade, min] of entries) if (pct >= min) return grade;
  return 'F';
}''',
        "provides": "letterGrade(pct, boundaries)",
        "depends": [],
    },
    {
        "id": "edu-normal-curve",
        "name": "Normal Curve Grading (Curve)",
        "category": "edu",
        "lang": "typescript",
        "when": "Adjusting raw scores so the class mean maps to a target",
        "why": "Atomic curve — mean/std shift in, adjusted scores out; preserves ordering",
        "tags": ["edu", "curve", "normal", "grade", "adjust"],
        "iface": r'''export function curveScores(scores: number[], targetMean: number): number[]''',
        "code": r'''export function curveScores(scores: number[], targetMean: number) {
  const mean = scores.reduce((s, x) => s + x, 0) / (scores.length || 1);
  const shift = targetMean - mean;
  return scores.map((s) => Math.min(100, Math.max(0, s + shift)));
}''',
        "provides": "curveScores(scores, targetMean)",
        "depends": [],
    },
    {
        "id": "edu-gpa",
        "name": "GPA Calculator",
        "category": "edu",
        "lang": "typescript",
        "when": "Weighted grade-point average from credits and grade points",
        "why": "Atomic GPA — (credits, points) pairs in, weighted average out",
        "tags": ["edu", "gpa", "grade-point", "credits", "average"],
        "iface": r'''export function gpa(courses: Array<{ credits: number; points: number }>): number''',
        "code": r'''export function gpa(courses: Array<{ credits: number; points: number }>) {
  const totalCredits = courses.reduce((s, c) => s + c.credits, 0);
  if (totalCredits === 0) return 0;
  return courses.reduce((s, c) => s + c.credits * c.points, 0) / totalCredits;
}''',
        "provides": "gpa(courses)",
        "depends": [],
    },
    {
        "id": "edu-sm2",
        "name": "Spaced Repetition (SM-2)",
        "category": "edu",
        "lang": "typescript",
        "when": "Scheduling flashcard reviews with the classic SM-2 algorithm",
        "why": "Atomic SM-2 — quality (0-5), interval, easiness in; next interval + due date out",
        "tags": ["edu", "spaced", "repetition", "sm2", "flashcard"],
        "iface": r'''export interface Sm2Result { interval: number; easiness: number; repetitions: number; due: Date }
export function sm2(quality: number, interval: number, easiness: number, repetitions: number, now: Date): Sm2Result''',
        "code": r'''export function sm2(quality: number, interval: number, easiness: number, repetitions: number, now: Date) {
  const q = Math.max(0, Math.min(5, quality));
  let ef = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
  if (ef < 1.3) ef = 1.3;
  if (q < 3) return { interval: 1, easiness: ef, repetitions: 0, due: new Date(now.getTime() + 86400000) };
  const next = repetitions === 0 ? 1 : repetitions === 1 ? 6 : Math.round(interval * ef);
  return { interval: next, easiness: ef, repetitions: repetitions + 1, due: new Date(now.getTime() + next * 86400000) };
}''',
        "provides": "sm2(quality, interval, easiness, repetitions, now)",
        "depends": [],
    },
    {
        "id": "edu-forgetting-curve",
        "name": "Ebbinghaus Forgetting Curve",
        "category": "edu",
        "lang": "typescript",
        "when": "Estimating retention decay over time after learning",
        "why": "Atomic retention model — hours since study + strength in, pct retained out",
        "tags": ["edu", "forgetting", "curve", "retention", "memory"],
        "iface": r'''export function retentionAt(hoursElapsed: number, strength = 1): number''',
        "code": r'''export function retentionAt(hoursElapsed: number, strength = 1) {
  return Math.exp(-hoursElapsed / (strength * 24));
}''',
        "provides": "retentionAt(hoursElapsed, strength)",
        "depends": [],
    },
    {
        "id": "edu-quiz-shuffle",
        "name": "Seeded Question Shuffler",
        "category": "edu",
        "lang": "typescript",
        "when": "Presenting quiz questions in a reproducible random order",
        "why": "Atomic seeded shuffle — same seed gives every student the same order",
        "tags": ["edu", "quiz", "shuffle", "seed", "order"],
        "iface": r'''export function shuffleQuestions<T>(questions: T[], seed: number): T[]''',
        "code": r'''export function shuffleQuestions<T>(questions: T[], seed: number) {
  const rand = () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const arr = questions.slice();
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}''',
        "provides": "shuffleQuestions(questions, seed)",
        "depends": [],
    },
    {
        "id": "edu-score-normalize",
        "name": "Score Normalization (0-100)",
        "category": "edu",
        "lang": "typescript",
        "when": "Rescaling raw quiz scores to a 0-100 range",
        "why": "Atomic scaler — raw + max in, percentage with rounding out",
        "tags": ["edu", "score", "normalize", "percent", "scale"],
        "iface": r'''export function normalizeScore(raw: number, max: number, min = 0): number''',
        "code": r'''export function normalizeScore(raw: number, max: number, min = 0) {
  if (max === min) return 100;
  return Math.round(((raw - min) / (max - min)) * 100);
}''',
        "provides": "normalizeScore(raw, max, min)",
        "depends": [],
    },
    {
        "id": "edu-progress-ring",
        "name": "Course Progress Calculation",
        "category": "edu",
        "lang": "typescript",
        "when": "Tracking completed lessons out of a course total",
        "why": "Atomic progress — done + total in, pct + remaining out, NaN-guarded",
        "tags": ["edu", "progress", "course", "lesson", "percent"],
        "iface": r'''export interface CourseProgress { percent: number; completed: number; remaining: number }
export function courseProgress(done: number, total: number): CourseProgress''',
        "code": r'''export function courseProgress(done: number, total: number) {
  return { percent: total <= 0 ? 0 : (done / total) * 100, completed: done, remaining: Math.max(0, total - done) };
}''',
        "provides": "courseProgress(done, total)",
        "depends": [],
    },
    {
        "id": "edu-streak",
        "name": "Learning Streak Counter",
        "category": "edu",
        "lang": "typescript",
        "when": "Computing consecutive-day learning streaks from activity dates",
        "why": "Atomic streak — dates in, current + longest streaks out; timezone-safe via date keys",
        "tags": ["edu", "streak", "habit", "days", "activity"],
        "iface": r'''export interface Streak { current: number; longest: number }
export function streak(dates: Date[], today: Date): Streak''',
        "code": r'''export function streak(dates: Date[], today: Date) {
  const key = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  const set = new Set(dates.map(key));
  let current = 0, longest = 0, run = 0;
  const cursor = new Date(today);
  while (set.has(key(cursor))) { current++; cursor.setDate(cursor.getDate() - 1); }
  const sorted = [...set].sort();
  let prev: string | null = null;
  for (const k of sorted) {
    if (prev) {
      const [py, pm, pd] = prev.split('-').map(Number);
      const [cy, cm, cd] = k.split('-').map(Number);
      const diff = (new Date(cy, cm, cd).getTime() - new Date(py, pm, pd).getTime()) / 86400000;
      run = diff === 1 ? run + 1 : 1;
    } else run = 1;
    longest = Math.max(longest, run);
    prev = k;
  }
  return { current, longest };
}''',
        "provides": "streak(dates, today)",
        "depends": [],
    },
    {
        "id": "edu-passing-check",
        "name": "Pass/Fail Threshold Checker",
        "category": "edu",
        "lang": "typescript",
        "when": "Determining pass/fail with a configurable cutoff",
        "why": "Atomic check — score + cutoff in, pass boolean + margin out",
        "tags": ["edu", "pass", "fail", "threshold", "check"],
        "iface": r'''export function passing(score: number, cutoff = 60): { pass: boolean; margin: number }''',
        "code": r'''export function passing(score: number, cutoff = 60) {
  return { pass: score >= cutoff, margin: score - cutoff };
}''',
        "provides": "passing(score, cutoff)",
        "depends": [],
    },
    {
        "id": "edu-multiple-choice",
        "name": "Multiple-Choice Scorer",
        "category": "edu",
        "lang": "typescript",
        "when": "Scoring multiple-choice responses with partial credit",
        "why": "Atomic scorer — answers + key in, right/wrong/partial + pct out",
        "tags": ["edu", "multiple-choice", "score", "answers", "quiz"],
        "iface": r'''export interface McResult { correct: number; total: number; percent: number; wrong: number[] }
export function scoreMultipleChoice(answers: string[], key: string[], partialCredit = false): McResult''',
        "code": r'''export function scoreMultipleChoice(answers: string[], key: string[], partialCredit = false) {
  let score = 0;
  const wrong: number[] = [];
  answers.forEach((a, i) => {
    if (a === key[i]) score++;
    else if (partialCredit && a) score += 0.5;
    else wrong.push(i);
  });
  const total = key.length;
  return { correct: Math.round(score), total, percent: total === 0 ? 0 : (score / total) * 100, wrong };
}''',
        "provides": "scoreMultipleChoice(answers, key, partialCredit)",
        "depends": [],
    },
    {
        "id": "edu-cloze-check",
        "name": "Cloze / Fill-in-the-Blank Checker",
        "category": "edu",
        "lang": "typescript",
        "when": "Accepting fill-in answers with normalized comparison",
        "why": "Atomic matcher — trim, lowercase, collapse spaces, optional aliases",
        "tags": ["edu", "cloze", "fill-blank", "answer", "normalize"],
        "iface": r'''export function clozeMatches(input: string, expected: string, aliases: string[] = []): boolean''',
        "code": r'''export function clozeMatches(input: string, expected: string, aliases: string[] = []) {
  const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');
  return [expected, ...aliases].some((e) => norm(e) === norm(input));
}''',
        "provides": "clozeMatches(input, expected, aliases)",
        "depends": [],
    },
    {
        "id": "edu-timer-sessions",
        "name": "Study Session Timer",
        "category": "edu",
        "lang": "typescript",
        "when": "Tracking pomodoro-style study sessions and totals",
        "why": "Atomic session log — durations in, sessions count + total minutes out",
        "tags": ["edu", "timer", "session", "study", "pomodoro"],
        "iface": r'''export interface SessionStats { sessions: number; totalMinutes: number; avgMinutes: number }
export function sessionStats(durationsMin: number[]): SessionStats''',
        "code": r'''export function sessionStats(durationsMin: number[]) {
  const total = durationsMin.reduce((s, d) => s + d, 0);
  return { sessions: durationsMin.length, totalMinutes: total, avgMinutes: durationsMin.length ? total / durationsMin.length : 0 };
}''',
        "provides": "sessionStats(durationsMin)",
        "depends": [],
    },
    {
        "id": "edu-confidence-rating",
        "name": "Confidence-Based Learning Rating",
        "category": "edu",
        "lang": "typescript",
        "when": "Converting self-rated confidence into review priority",
        "why": "Atomic rating — 1-5 confidence in, review bucket + next-action hint out",
        "tags": ["edu", "confidence", "rating", "review", "priority"],
        "iface": r'''export interface ConfidencePlan { bucket: 'relearn' | 'review' | 'reinforce' | 'mastered'; priority: number }
export function confidencePlan(rating: number): ConfidencePlan''',
        "code": r'''export function confidencePlan(rating: number) {
  if (rating <= 2) return { bucket: 'relearn', priority: 4 };
  if (rating === 3) return { bucket: 'review', priority: 3 };
  if (rating === 4) return { bucket: 'reinforce', priority: 2 };
  return { bucket: 'mastered', priority: 1 };
}''',
        "provides": "confidencePlan(rating)",
        "depends": [],
    },
    {
        "id": "edu-vocab-list",
        "name": "Vocabulary List Builder",
        "category": "edu",
        "lang": "typescript",
        "when": "Building an alphabetized vocab list with dedupe",
        "why": "Atomic builder — words in, unique + sorted + count out",
        "tags": ["edu", "vocab", "list", "dedupe", "sort"],
        "iface": r'''export function vocabList(words: string[]): { words: string[]; count: number }''',
        "code": r'''export function vocabList(words: string[]) {
  const unique = [...new Set(words.map((w) => w.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  return { words: unique, count: unique.length };
}''',
        "provides": "vocabList(words)",
        "depends": [],
    },
    {
        "id": "edu-quiz-timer",
        "name": "Quiz Time Remaining",
        "category": "edu",
        "lang": "typescript",
        "when": "Computing remaining time and pace for a timed quiz",
        "why": "Atomic pace — questions done, total, time left in; per-question pace out",
        "tags": ["edu", "quiz", "timer", "pace", "remaining"],
        "iface": r'''export interface QuizPace { remainingMs: number; perQuestion: number }
export function quizPace(startedAt: number, durationMs: number, done: number, total: number, now: number): QuizPace''',
        "code": r'''export function quizPace(startedAt: number, durationMs: number, done: number, total: number, now: number) {
  const remainingMs = Math.max(0, startedAt + durationMs - now);
  const remainingQs = Math.max(0, total - done);
  return { remainingMs, perQuestion: remainingQs === 0 ? 0 : remainingMs / remainingQs };
}''',
        "provides": "quizPace(startedAt, durationMs, done, total, now)",
        "depends": [],
    },
    {
        "id": "edu-answer-feedback",
        "name": "Answer Feedback Generator",
        "category": "edu",
        "lang": "typescript",
        "when": "Generating canned feedback text for right/wrong answers",
        "why": "Atomic feedback — correct flag in, encouraging message with the answer out",
        "tags": ["edu", "feedback", "answer", "message", "quiz"],
        "iface": r'''export function answerFeedback(correct: boolean, answer: string): { correct: boolean; text: string }''',
        "code": r'''export function answerFeedback(correct: boolean, answer: string) {
  return correct
    ? { correct, text: `Correct! The answer is ${answer}.` }
    : { correct, text: `Not quite — the answer is ${answer}. Review and try again.` };
}''',
        "provides": "answerFeedback(correct, answer)",
        "depends": [],
    },
    {
        "id": "edu-learning-plan",
        "name": "Study Plan Distributor",
        "category": "edu",
        "lang": "typescript",
        "when": "Splitting topics across available study days",
        "why": "Atomic planner — topics + days in, even day-by-day plan out",
        "tags": ["edu", "plan", "study", "schedule", "distribute"],
        "iface": r'''export function studyPlan(topics: string[], days: number): string[][]''',
        "code": r'''export function studyPlan(topics: string[], days: number) {
  const plan: string[][] = Array.from({ length: days }, () => []);
  topics.forEach((t, i) => plan[i % days].push(t));
  return plan.filter((d) => d.length);
}''',
        "provides": "studyPlan(topics, days)",
        "depends": [],
    },
    {
        "id": "edu-mastery-level",
        "name": "Mastery Level Estimator",
        "category": "edu",
        "lang": "typescript",
        "when": "Classifying a learner by recent performance history",
        "why": "Atomic estimator — recent scores in, mastery level + next recommendation out",
        "tags": ["edu", "mastery", "level", "estimate", "scores"],
        "iface": r'''export function masteryLevel(scores: number[]): { level: string; avg: number; next: string }''',
        "code": r'''export function masteryLevel(scores: number[]) {
  if (!scores.length) return { level: 'untested', avg: 0, next: 'Take a first assessment' };
  const avg = scores.reduce((s, x) => s + x, 0) / scores.length;
  if (avg >= 90) return { level: 'mastered', avg, next: 'Challenge with advanced topics' };
  if (avg >= 75) return { level: 'proficient', avg, next: 'Reinforce with mixed practice' };
  if (avg >= 60) return { level: 'developing', avg, next: 'Review missed concepts' };
  return { level: 'beginning', avg, next: 'Restart with foundational lessons' };
}''',
        "provides": "masteryLevel(scores)",
        "depends": [],
    },
    {
        "id": "edu-flashcard-deck",
        "name": "Flashcard Deck Manager",
        "category": "edu",
        "lang": "typescript",
        "when": "Managing a deck with due/undue card filtering",
        "why": "Atomic deck — cards in, due cards + counts out; due = next review <= now",
        "tags": ["edu", "flashcard", "deck", "due", "review"],
        "iface": r'''export interface Card { front: string; back: string; due: Date }
export function dueCards(cards: Card[], now: Date): { due: Card[]; notDue: number }''',
        "code": r'''export function dueCards(cards: Card[], now: Date) {
  const due = cards.filter((c) => c.due.getTime() <= now.getTime());
  return { due, notDue: cards.length - due.length };
}''',
        "provides": "dueCards(cards, now)",
        "depends": [],
    },
    {
        "id": "edu-text-difficulty",
        "name": "Reading Difficulty (Flesch)",
        "category": "edu",
        "lang": "typescript",
        "when": "Estimating text readability for level-appropriate materials",
        "why": "Atomic Flesch reading-ease — syllables + words + sentences in, 0-100 score out",
        "tags": ["edu", "reading", "flesch", "difficulty", "readability"],
        "iface": r'''export function fleschReadingEase(words: number, sentences: number, syllables: number): number''',
        "code": r'''export function fleschReadingEase(words: number, sentences: number, syllables: number) {
  if (!words || !sentences) return 0;
  return Math.max(0, Math.min(100, 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)));
}''',
        "provides": "fleschReadingEase(words, sentences, syllables)",
        "depends": [],
    },
    {
        "id": "edu-badge-progress",
        "name": "Achievement Badge Unlocker",
        "category": "edu",
        "lang": "typescript",
        "when": "Determining which achievement badges a learner has earned",
        "why": "Atomic checker — milestones map + stats in, earned + locked out",
        "tags": ["edu", "badge", "achievement", "unlock", "milestone"],
        "iface": r'''export function badgesEarned(stats: Record<string, number>, milestones: Record<string, number>): { earned: string[]; locked: string[] }''',
        "code": r'''export function badgesEarned(stats: Record<string, number>, milestones: Record<string, number>) {
  const earned: string[] = [], locked: string[] = [];
  for (const [badge, need] of Object.entries(milestones)) (stats[badge] ?? 0) >= need ? earned.push(badge) : locked.push(badge);
  return { earned, locked };
}''',
        "provides": "badgesEarned(stats, milestones)",
        "depends": [],
    },
    {
        "id": "edu-syllable-count",
        "name": "Syllable Counter",
        "category": "edu",
        "lang": "typescript",
        "when": "Estimating syllable counts for reading-level tools",
        "why": "Atomic counter \u2014 vowel-group heuristic with silent-e handling",
        "tags": [
            "edu",
            "syllable",
            "count",
            "reading",
            "word"
        ],
        "iface": "export function countSyllables(word: string): number",
        "code": "export function countSyllables(word: string) {\n  const w = word.toLowerCase().replace(/[^a-z]/g, '');\n  if (!w) return 0;\n  let count = (w.match(/[aeiouy]+/g) ?? []).length;\n  if (w.endsWith('e') && !/le$/.test(w) && count > 1) count--;\n  return Math.max(1, count);\n}",
        "provides": "countSyllables(word)",
        "depends": []
    },
    {
        "id": "edu-lesson-lock",
        "name": "Lesson Unlock Chain",
        "category": "edu",
        "lang": "typescript",
        "when": "Sequential course gating \u2014 unlock N+1 only when N is passed",
        "why": "Atomic gate \u2014 pass events in, next unlocked index out",
        "tags": [
            "edu",
            "lesson",
            "unlock",
            "gate",
            "course"
        ],
        "iface": "export function unlockedLessons(passedCount: number, total: number): Array<{ index: number; unlocked: boolean }>",
        "code": "export function unlockedLessons(passedCount: number, total: number) {\n  return Array.from({ length: total }, (_, i) => ({ index: i, unlocked: i <= passedCount }));\n}",
        "provides": "unlockedLessons(passedCount, total)",
        "depends": []
    },
    {
        "id": "edu-review-mix",
        "name": "Review Mixer (new + due)",
        "category": "edu",
        "lang": "typescript",
        "when": "Interleaving new cards with due reviews for daily sessions",
        "why": "Atomic mixer \u2014 interleave due and new, cap daily new cards",
        "tags": [
            "edu",
            "review",
            "mix",
            "interleave",
            "schedule"
        ],
        "iface": "export function mixReview<T>(due: T[], fresh: T[], dailyNewCap: number): T[]",
        "code": "export function mixReview<T>(due: T[], fresh: T[], dailyNewCap: number) {\n  const out: T[] = [];\n  const d = due.slice(), f = fresh.slice(0, dailyNewCap);\n  while (d.length || f.length) {\n    if (d.length) out.push(d.shift()!);\n    if (f.length) out.push(f.shift()!);\n  }\n  return out;\n}",
        "provides": "mixReview(due, fresh, dailyNewCap)",
        "depends": []
    },
]
