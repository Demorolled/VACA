import { Router } from 'express';
import { analyzeEmotion, analyzeEmotionHistory, getEmotionPromptModifier, getDetailedEmotionContext, EMOTIONS } from '../ai/emotionEngine.js';
export const emotionRoutes = Router();
/**
 * POST /api/emotion/analyze
 * Analyze a single text string for emotion probabilities
 */
emotionRoutes.post('/analyze', (req, res) => {
    try {
        const { text } = req.body;
        if (!text || typeof text !== 'string') {
            return res.status(400).json({ error: 'Text is required' });
        }
        const result = analyzeEmotion(text);
        res.json({
            success: true,
            ...result,
        });
    }
    catch (error) {
        res.status(500).json({
            error: error instanceof Error ? error.message : 'Emotion analysis failed',
        });
    }
});
/**
 * POST /api/emotion/batch
 * Analyze a batch of messages for emotion tracking over time
 */
emotionRoutes.post('/batch', (req, res) => {
    try {
        const { messages } = req.body;
        if (!Array.isArray(messages) || messages.length === 0) {
            return res.status(400).json({ error: 'Messages array is required' });
        }
        const result = analyzeEmotionHistory(messages);
        res.json({
            success: true,
            ...result,
        });
    }
    catch (error) {
        res.status(500).json({
            error: error instanceof Error ? error.message : 'Batch emotion analysis failed',
        });
    }
});
/**
 * POST /api/emotion/prompt
 * Analyze text and return a system prompt modifier for the LLM
 * This is designed to be called BEFORE making a reasoning request
 * so the LLM can adapt its tone to the user's emotional state.
 */
emotionRoutes.post('/prompt', (req, res) => {
    try {
        const { text, detailed } = req.body;
        if (!text || typeof text !== 'string') {
            return res.status(400).json({ error: 'Text is required' });
        }
        const emotion = analyzeEmotion(text);
        const modifier = detailed
            ? getDetailedEmotionContext(emotion)
            : getEmotionPromptModifier(emotion);
        res.json({
            success: true,
            emotionModifier: modifier,
            dominant: emotion.dominant,
            confidence: emotion.confidence,
            valence: emotion.valence,
            arousal: emotion.arousal,
            dominance: emotion.dominance,
            probabilities: emotion.probabilities,
        });
    }
    catch (error) {
        res.status(500).json({
            error: error instanceof Error ? error.message : 'Emotion prompt generation failed',
        });
    }
});
/**
 * GET /api/emotion/schema
 * Return the emotion taxonomy and VAD baselines
 */
emotionRoutes.get('/schema', (_req, res) => {
    res.json({
        success: true,
        emotions: EMOTIONS,
        description: 'Plutchik-inspired wheel of emotions with Valence-Arousal-Dominance dimensions',
        vadBaselines: {
            joy: { valence: 0.85, arousal: 0.65, dominance: 0.65 },
            sadness: { valence: -0.7, arousal: 0.35, dominance: 0.25 },
            anger: { valence: -0.6, arousal: 0.85, dominance: 0.75 },
            fear: { valence: -0.55, arousal: 0.80, dominance: 0.20 },
            surprise: { valence: 0.30, arousal: 0.75, dominance: 0.50 },
            disgust: { valence: -0.60, arousal: 0.60, dominance: 0.45 },
            trust: { valence: 0.60, arousal: 0.30, dominance: 0.60 },
            anticipation: { valence: 0.40, arousal: 0.60, dominance: 0.50 },
            neutral: { valence: 0.00, arousal: 0.00, dominance: 0.50 },
        },
        lexiconSize: 96, // number of unique words in the emotion lexicon
        phrasesSize: 32, // number of multi-word phrases
    });
});
