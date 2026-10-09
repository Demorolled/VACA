import { Router } from 'express';
import { MsEdgeTTS } from 'msedge-tts';
import { OUTPUT_FORMAT } from 'msedge-tts';
import { ttsSpeaker } from '../services/ttsSpeakerService.js';
export const ttsRoutes = Router();
// ─── Available Voices ────────────────────────────────────────────────
const AVAILABLE_VOICES = [
    { id: 'en-US-JennyNeural', name: 'Jenny', gender: 'Female', style: 'Friendly, Considerate' },
    { id: 'en-US-AriaNeural', name: 'Aria', gender: 'Female', style: 'Positive, Confident' },
    { id: 'en-US-AndrewNeural', name: 'Andrew', gender: 'Male', style: 'Warm, Confident' },
    { id: 'en-US-BrianNeural', name: 'Brian', gender: 'Male', style: 'Approachable, Casual' },
    { id: 'en-US-ChristopherNeural', name: 'Christopher', gender: 'Male', style: 'Reliable, Authority' },
    { id: 'en-US-EricNeural', name: 'Eric', gender: 'Male', style: 'Rational' },
    { id: 'en-US-GuyNeural', name: 'Guy', gender: 'Male', style: 'Passionate' },
    { id: 'en-US-RogerNeural', name: 'Roger', gender: 'Male', style: 'Lively' },
    { id: 'en-US-AngelaNeural', name: 'Angela', gender: 'Female', style: 'Cheerful' },
    { id: 'en-US-SaraNeural', name: 'Sara', gender: 'Female', style: 'Warm, Friendly' },
    { id: 'en-GB-SoniaNeural', name: 'Sonia (UK)', gender: 'Female', style: 'British, Refined' },
    { id: 'en-GB-RyanNeural', name: 'Ryan (UK)', gender: 'Male', style: 'British, Professional' },
];
ttsRoutes.get('/voices', (_req, res) => {
    res.json({ success: true, voices: AVAILABLE_VOICES });
});
// ─── Symbol & Emoji spoken-word expansion ───────────────────────────────
// ─── Normalize text for natural speech ───────────────────────────────
// By default code blocks are silenced (they're displayed, not spoken).
// Pass codeToWords: true only when the user explicitly asked for the code.
function normalizeForSpeech(text, codeToWords = false) {
    let result = text;
    // 1. Markdown code fences (``` ... ```)
    if (codeToWords) {
        result = result.replace(/```[a-zA-Z0-9_-]*\s*/g, ' ');
        result = result.replace(/```/g, ' ');
    }
    else {
        // Default: never read code aloud — silence complete fences and any
        // unclosed fence opener along with the rest of the text (likely code)
        result = result.replace(/```[\s\S]*?```/g, ' ');
        result = result.replace(/```[a-zA-Z0-9_-]*[\s\S]*$/g, ' ');
    }
    // 2. Remove inline code backticks, keep inner text
    result = result.replace(/`([^`]+)`/g, ' $1 ');
    // 3. Strip markdown bold/italic
    result = result.replace(/\*\*([^*]+)\*\*/g, ' $1 ');
    result = result.replace(/\*([^*]+)\*/g, ' $1 ');
    result = result.replace(/__([^_]+)__/g, ' $1 ');
    result = result.replace(/_([^_]+)_/g, ' $1 ');
    // 4. Common code patterns → natural speech
    result = result.replace(/\s*=>\s*/g, ' becomes ');
    result = result.replace(/\s*===\s*/g, ' equals ');
    result = result.replace(/\s*==\s*/g, ' equals ');
    result = result.replace(/\s*!==\s*/g, ' does not equal ');
    result = result.replace(/\s*!=\s*/g, ' does not equal ');
    result = result.replace(/\s*>=\s*/g, ' greater than or equal ');
    result = result.replace(/\s*<=\s*/g, ' less than or equal ');
    result = result.replace(/\s*&&\s*/g, ' and ');
    result = result.replace(/\s*\|\|\s*/g, ' or ');
    // 5. Package paths — replace / with "slash" only within path patterns
    result = result.replace(/([a-zA-Z0-9_\-.]+)(\/)([a-zA-Z0-9_\-.]+)/g, (match) => match.replace(/\//g, ' slash '));
    // 6. File extensions — "file.ts" → "file dot ts"
    result = result.replace(/\.([a-zA-Z]{2,4})(?=\s|$)/g, ' dot $1 ');
    // 7. Strip standalone symbols that are annoying in speech
    result = result.replace(/(?<=^|[\s(])[*#@$%^&~`|\\_{}\[\]<>](?=[\s)]|$)/g, ' ');
    // 8. Replace known emojis
    for (const [emoji, replacement] of Object.entries(EMOJI_MAP)) {
        result = result.split(emoji).join(replacement);
    }
    // 9. Strip remaining unmapped emojis
    result = result.replace(/[\u{1F000}-\u{1FFFF}]|[\u{2700}-\u{27BF}]|[\u{2600}-\u{26FF}]|[\u{FE00}-\u{FE0F}]|[\u{200D}]/gu, '');
    // 10. Collapse whitespace and trim
    result = result.replace(/\s+/g, ' ').trim();
    return result;
}
const EMOJI_MAP = {
    '😀': ' grinning face ',
    '😂': ' face with tears of joy ',
    '🤣': ' rolling on the floor laughing ',
    '😊': ' smiling face ',
    '😍': ' smiling face with heart eyes ',
    '🥰': ' smiling face with hearts ',
    '🤔': ' thinking face ',
    '😏': ' smirking face ',
    '😢': ' crying face ',
    '😭': ' loudly crying face ',
    '😡': ' enraged face ',
    '🤖': ' robot face ',
    '👍': ' thumbs up ',
    '👎': ' thumbs down ',
    '👏': ' clapping hands ',
    '🙌': ' raising hands ',
    '🤝': ' handshake ',
    '🙏': ' folded hands ',
    '💪': ' flexed biceps ',
    '🎉': ' party popper ',
    '🎊': ' confetti ball ',
    '🚀': ' rocket ',
    '💡': ' light bulb ',
    '✨': ' sparkles ',
    '🔥': ' fire ',
    '⭐': ' star ',
    '❤️': ' red heart ',
    '💔': ' broken heart ',
    '✅': ' check mark ',
    '❌': ' cross mark ',
    '❓': ' question mark ',
    '❗': ' exclamation mark ',
    '⚠️': ' warning ',
    '🔧': ' wrench ',
    '🔒': ' locked lock ',
    '🔓': ' unlocked lock ',
    '💻': ' laptop ',
    '📱': ' mobile phone ',
    '☕': ' hot beverage ',
    '🍕': ' pizza ',
    '🍔': ' hamburger ',
    '🎯': ' bullseye ',
    '🎮': ' video game ',
    '🎵': ' musical note ',
    '🔊': ' speaker ',
    '🎨': ' artist palette ',
    '📝': ' memo ',
    '📚': ' books ',
    '💯': ' hundred points ',
    '👑': ' crown ',
    '🏆': ' trophy ',
    '🌈': ' rainbow ',
    '☀️': ' sun ',
    '🌙': ' moon ',
    '🚨': ' alert ',
    '♻️': ' recycling ',
    '™️': ' trademark ',
    '©️': ' copyright ',
    '®️': ' registered ',
};
function mapPitch(val) {
    return `${((val - 1.0) * 120).toFixed(0)}Hz`;
}
function mapRate(val) {
    return `${((val - 1.0) * 100).toFixed(0)}%`;
}
function mapVolume(val) {
    return `${((val - 1.0) * 50).toFixed(0)}%`;
}
// POST /api/tts/speech — trigger VACA's full spoken introduction
// Reads VACA_Speech.txt from the Desktop and speaks it section by section.
ttsRoutes.post('/speech', async (_req, res) => {
    try {
        const success = await ttsSpeaker.speakIntroduction();
        if (success) {
            res.json({ success: true, message: 'Introduction speech started.' });
        }
        else {
            res.status(503).json({ success: false, error: 'TTS not initialized or disabled' });
        }
    }
    catch (error) {
        console.error('TTS speech error:', error);
        res.status(500).json({ error: 'Failed to start introduction speech', details: String(error) });
    }
});
// POST /api/tts — speak arbitrary text
ttsRoutes.post('/', async (req, res) => {
    try {
        const { text, voice, pitch, rate, volume, codeToWords } = req.body;
        if (!text || typeof text !== 'string' || text.trim().length === 0) {
            return res.status(400).json({ error: 'text field is required' });
        }
        // Normalize text for natural speech — strip code, symbols, keep emoji context
        const spokenText = normalizeForSpeech(text, !!codeToWords);
        const tts = new MsEdgeTTS();
        await tts.setMetadata(voice || 'en-US-JennyNeural', OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
        const pitchStr = pitch != null ? mapPitch(Number(pitch)) : '+0Hz';
        const rateStr = rate != null ? mapRate(Number(rate)) : '+0%';
        const volumeStr = volume != null ? mapVolume(Number(volume)) : '+0%';
        const { audioStream } = tts.toStream(spokenText, { pitch: pitchStr, rate: rateStr, volume: volumeStr });
        const chunks = [];
        for await (const chunk of audioStream) {
            chunks.push(Buffer.from(chunk));
        }
        const audioBuffer = Buffer.concat(chunks);
        tts.close();
        res.set('Content-Type', 'audio/mpeg');
        res.set('Content-Length', audioBuffer.byteLength.toString());
        res.send(audioBuffer);
    }
    catch (error) {
        console.error('TTS error:', error);
        res.status(500).json({ error: 'TTS generation failed', details: String(error) });
    }
});
