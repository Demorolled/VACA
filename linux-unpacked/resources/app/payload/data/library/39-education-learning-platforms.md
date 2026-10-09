# 🎓 Education & Learning Platforms

> Reference for building education technology platforms — LMS, adaptive learning, spaced repetition, gamification, virtual classrooms, and learning analytics.
> Extracted from The Programming Bible's Education & Learning Platforms level.

---

## 1. EdTech Platform Architecture

### Platform Layers

```
┌──────────────────────────────────────────────┐
│              LEARNING EXPERIENCE              │
│  Courses  Quizzes  Assignments  Discussions   │
├──────────────────────────────────────────────┤
│           ADAPTIVE LEARNING ENGINE            │
│  Personalization  Recommendations  Remediation │
├──────────────────────────────────────────────┤
│           CONTENT MANAGEMENT                  │
│  Lessons  Media  Assessments  SCORM / xAPI    │
├──────────────────────────────────────────────┤
│           DATA & ANALYTICS                    │
│  Progress  Engagement  Mastery  Predictions   │
├──────────────────────────────────────────────┤
│           CORE INFRASTRUCTURE                 │
│  LMS  LTI  Gradebook  Enrollment  Payments    │
└──────────────────────────────────────────────┘
```

### Key Standards

| Standard | Purpose | Usage |
|---|---|---|
| **SCORM** | Content packaging & sequencing | Legacy LMS, course imports |
| **xAPI** | Experience tracking (any activity) | Modern learning analytics |
| **LTI 1.3** | Tool integration | Embed external tools in LMS |
| **QTI** | Question & test interoperability | Assessment portability |
| **Caliper** | IMS learning analytics | Real-time event streaming |

---

## 2. Course & Content Management

### Course Data Model

```typescript
// LMS course data model
interface Course {
    id: string;
    title: string;
    description: string;
    category: string;
    level: 'beginner' | 'intermediate' | 'advanced';
    duration: number;          // Total minutes
    modules: Module[];
    prerequisites: string[];   // Course IDs
    learningObjectives: string[];
    skills: string[];
    metadata: {
        author: string;
        version: string;
        language: string;
        lastUpdated: Date;
    };
}

interface Module {
    id: string;
    title: string;
    order: number;
    lessons: Lesson[];
    assessments: Assessment[];
    duration: number;
}

interface Lesson {
    id: string;
    title: string;
    type: 'video' | 'article' | 'interactive' | 'quiz' | 'assignment';
    content: LessonContent;
    duration: number;
    required: boolean;
}

type LessonContent =
    | { type: 'video'; url: string; transcript: string; captions: string }
    | { type: 'article'; body: string; references: string[] }
    | { type: 'interactive'; component: string; config: Record<string, unknown> }
    | { type: 'quiz'; questions: Question[] }
    | { type: 'assignment'; prompt: string; rubric: RubricCriterion[] };
```

### Content Versioning

```typescript
// Content versioning for collaborative course authoring
interface ContentVersion {
    id: string;
    courseId: string;
    version: number;
    snapshot: Course;
    author: string;
    changeLog: string;
    status: 'draft' | 'review' | 'published' | 'archived';
    createdAt: Date;
    parentVersion?: number;
}

class CourseAuthoringService {
    private versions: Map<string, ContentVersion[]> = new Map();

    async createVersion(
        courseId: string,
        course: Course,
        author: string,
        changeLog: string,
    ): Promise<ContentVersion> {
        const existing = this.versions.get(courseId) || [];
        const latestVersion = existing[existing.length - 1]?.version || 0;

        const version: ContentVersion = {
            id: crypto.randomUUID(),
            courseId,
            version: latestVersion + 1,
            snapshot: JSON.parse(JSON.stringify(course)), // Deep clone
            author,
            changeLog,
            status: 'draft',
            createdAt: new Date(),
            parentVersion: latestVersion || undefined,
        };

        existing.push(version);
        this.versions.set(courseId, existing);
        return version;
    }

    async publishVersion(versionId: string): Promise<void> {
        const version = this.findVersion(versionId);
        if (!version) throw new Error('Version not found');

        // Validate all required fields
        this.validateCourse(version.snapshot);

        version.status = 'published';

        // Archive previous published version
        const allVersions = this.versions.get(version.courseId) || [];
        for (const v of allVersions) {
            if (v.status === 'published' && v.id !== versionId) {
                v.status = 'archived';
            }
        }
    }

    async rollback(courseId: string, targetVersion: number): Promise<Course> {
        const version = this.versions.get(courseId)
            ?.find(v => v.version === targetVersion);
        if (!version) throw new Error('Version not found');

        return JSON.parse(JSON.stringify(version.snapshot)); // Return deep clone
    }
}
```

---

## 3. Adaptive Learning

### Knowledge Tracing (BKT)

```typescript
// Bayesian Knowledge Tracing
interface BKTParams {
    pLearn: number;      // Probability of learning per opportunity (0.1-0.5)
    pGuess: number;      // Probability of guessing correctly (0.1-0.3)
    pSlip: number;       // Probability of slipping (0.05-0.2)
    pKnown: number;      // Prior probability of knowing (0.1-0.3)
}

class KnowledgeTracer {
    private studentParams: Map<string, Map<string, BKTParams>> = new Map();

    // Update knowledge estimate after student response
    updateEstimate(
        studentId: string,
        skillId: string,
        correct: boolean,
    ): number {
        const params = this.getParams(studentId, skillId);
        const currentKnown = params.pKnown;

        // Probability student knew skill given their response
        const pCorrect = currentKnown * (1 - params.pSlip) +
                        (1 - currentKnown) * params.pGuess;

        const posterior = correct
            ? (currentKnown * (1 - params.pSlip)) / pCorrect
            : (currentKnown * params.pSlip) /
              (currentKnown * params.pSlip + (1 - currentKnown) * (1 - params.pGuess));

        // Probability of knowing after learning opportunity
        params.pKnown = posterior + (1 - posterior) * params.pLearn;

        return params.pKnown; // 0.0 - 1.0 mastery estimate
    }

    // Predict student's probability of correct response
    predictCorrect(studentId: string, skillId: string): number {
        const params = this.getParams(studentId, skillId);
        return params.pKnown * (1 - params.pSlip) +
               (1 - params.pKnown) * params.pGuess;
    }

    // Determine if skill is mastered (threshold)
    isMastered(studentId: string, skillId: string, threshold = 0.95): boolean {
        return this.getParams(studentId, skillId).pKnown >= threshold;
    }
}
```

### Spaced Repetition (SM-2 Algorithm)

```typescript
// SM-2 spaced repetition algorithm (used in Anki/SuperMemo)
interface SM2Card {
    id: string;
    deckId: string;
    question: string;
    answer: string;
    // SM-2 state
    easiness: number;       // Initial: 2.5
    interval: number;       // Days until next review
    repetitions: number;    // Consecutive correct answers
    nextReview: Date;
}

class SM2Scheduler {
    private readonly MIN_EASINESS = 1.3;

    // Quality: 0 (complete blackout) to 5 (perfect recall)
    schedule(card: SM2Card, quality: number): void {
        if (quality < 3) {
            // Failed — reset
            card.repetitions = 0;
            card.interval = 1;
        } else {
            // Passed
            switch (card.repetitions) {
                case 0:
                    card.interval = 1;
                    break;
                case 1:
                    card.interval = 6;
                    break;
                default:
                    card.interval = Math.round(card.interval * card.easiness);
                    break;
            }
            card.repetitions++;
        }

        // Update easiness factor
        card.easiness = Math.max(
            this.MIN_EASINESS,
            card.easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        );

        // Schedule next review
        card.nextReview = new Date(Date.now() + card.interval * 86400000);
    }

    // Get cards due for review
    getDueCards(cards: SM2Card[]): SM2Card[] {
        return cards.filter(c => c.nextReview <= new Date());
    }
}
```

---

## 4. Virtual Classroom (WebRTC)

### Classroom Architecture

```
┌─────────────────────────────────────────────┐
│              SIGNALING SERVER                │
│  Room management, participant events         │
└──────────────────┬──────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
┌────────▼────────┐  ┌──────▼───────┐
│   SFU (Selective Forwarding Unit)  │
│   Mediasoup / LiveKit / Jitsi      │
│   Forwarding video/audio streams   │
└────────────────┬───────────────────┘
         │                   │
┌────────▼────────┐  ┌──────▼───────┐
│   Student A     │  │  Student B   │
│   (publisher)   │  │ (subscriber) │
└─────────────────┘  └──────────────┘
```

### Classroom Features

```typescript
// Virtual classroom service
interface Classroom {
    id: string;
    courseId: string;
    instructorId: string;
    participants: Map<string, Participant>;
    state: 'waiting' | 'live' | 'recording' | 'ended';
    features: {
        screenshare: boolean;
        breakout: boolean;
        recording: boolean;
        chat: boolean;
        polls: boolean;
        handRaise: boolean;
        captions: boolean;
    };
}

interface Participant {
    userId: string;
    role: 'instructor' | 'ta' | 'student';
    joinedAt: Date;
    media: {
        video: boolean;
        audio: boolean;
        screenshare: boolean;
    };
    handRaised: boolean;
}

class ClassroomService {
    private classrooms = new Map<string, Classroom>();
    private sfu: SFUClient;

    async createRoom(courseId: string, instructorId: string): Promise<string> {
        const roomId = crypto.randomUUID();

        // Create SFU room
        await this.sfu.createRoom(roomId);

        const classroom: Classroom = {
            id: roomId,
            courseId,
            instructorId,
            participants: new Map(),
            state: 'waiting',
            features: {
                screenshare: true,
                breakout: true,
                recording: true,
                chat: true,
                polls: true,
                handRaise: true,
                captions: true,
            },
        };

        this.classrooms.set(roomId, classroom);
        return roomId;
    }

    async joinRoom(roomId: string, userId: string, role: Participant['role']) {
        const room = this.classrooms.get(roomId);
        if (!room) throw new Error('Room not found');

        // Generate SFU token
        const sfuToken = await this.sfu.generateToken(roomId, userId);

        room.participants.set(userId, {
            userId,
            role,
            joinedAt: new Date(),
            media: { video: false, audio: false, screenshare: false },
            handRaised: false,
        });

        return { roomId, sfuToken, classroom: room };
    }

    async generateCaptions(audioStream: MediaStream): Promise<string[]> {
        // Send audio to speech-to-text service
        const recognition = await this.asrService.transcribe(audioStream);
        return recognition.alternatives[0]?.transcript || [];
    }
}
```

---

## 5. Gamification & Engagement

### Gamification Engine

```typescript
// Gamification system
interface GamificationEvent {
    userId: string;
    eventType: string;        // 'lesson_complete' | 'quiz_pass' | 'streak_day' | ...
    metadata: Record<string, unknown>;
    timestamp: Date;
}

interface Achievement {
    id: string;
    name: string;
    description: string;
    icon: string;
    criteria: (events: GamificationEvent[]) => boolean;
    points: number;
    hidden: boolean;         // Secret achievement?
}

interface PlayerProgress {
    userId: string;
    level: number;
    xp: number;
    xpToNextLevel: number;
    streak: number;           // Consecutive days
    longestStreak: number;
    achievements: string[];
    leaderboardRank?: number;
}

class GamificationEngine {
    private readonly XP_RATES = {
        lesson_complete: 50,
        quiz_pass: 100,
        quiz_perfect: 200,
        assignment_submit: 75,
        discussion_post: 25,
        streak_day: 10,
        achievement_unlock: 500,
    };

    achievements: Achievement[] = [
        {
            id: 'first_lesson',
            name: 'First Steps',
            description: 'Complete your first lesson',
            icon: '🚀',
            criteria: (events) =>
                events.filter(e => e.eventType === 'lesson_complete').length >= 1,
            points: 100,
            hidden: false,
        },
        {
            id: 'streak_7',
            name: 'Week Warrior',
            description: 'Maintain a 7-day streak',
            icon: '🔥',
            criteria: (events) =>
                events.some(e => e.eventType === 'streak_7'),
            points: 500,
            hidden: false,
        },
        {
            id: 'quiz_master',
            name: 'Quiz Master',
            description: 'Get perfect score on 5 quizzes',
            icon: '🏆',
            criteria: (events) =>
                events.filter(e => e.eventType === 'quiz_perfect').length >= 5,
            points: 1000,
            hidden: false,
        },
    ];

    async processEvent(event: GamificationEvent): Promise<PlayerProgress> {
        const progress = await this.getProgress(event.userId);

        // Award XP
        const xpGain = this.XP_RATES[event.eventType] || 10;
        progress.xp += xpGain;

        // Check level up
        while (progress.xp >= progress.xpToNextLevel) {
            progress.xp -= progress.xpToNextLevel;
            progress.level++;
            progress.xpToNextLevel = this.calculateXPForLevel(progress.level + 1);
        }

        // Check achievements
        const allEvents = await this.getUserEvents(event.userId);
        for (const achievement of this.achievements) {
            if (!progress.achievements.includes(achievement.id)) {
                if (achievement.criteria(allEvents)) {
                    progress.achievements.push(achievement.id);
                    progress.xp += achievement.points;

                    // Emit achievement notification
                    await this.notifyAchievement(event.userId, achievement);
                }
            }
        }

        // Update streak
        await this.updateStreak(progress);

        await this.saveProgress(progress);
        return progress;
    }
}
```

---

## Quick Reference: EdTech by Node Type

| Node Type | EdTech Mapping |
|---|---|
| **Input** | Quiz answers, assignment submissions, discussion posts, video progress events |
| **Logic** | BKT algorithm, SM-2 scheduler, grade calculation, recommendation engine, adaptive routing |
| **Database** | Course content store, student progress DB, event store (xAPI), user profiles |
| **UI** | Course player, quiz interface, progress dashboard, spaced repetition review UI |
| **API** | LTI tool provider, SCORM player bridge, grade passback, WebRTC signaling |

---

*For deeper education concepts, see Bible levels `42-education-learning/`, `35-realtime-collaboration/` (virtual classroom), and `01-foundations/` (cognitive science).*
