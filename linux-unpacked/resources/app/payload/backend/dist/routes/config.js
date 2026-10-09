import { Router } from 'express';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const TTS_CONFIG_PATH = join(__dirname, '..', '..', 'tts-config.json');
const DEFAULT_TTS = {
    voice: 'en-US-JennyNeural',
    speed: 1,
    pitch: 1,
    volume: 1,
    bass: 0,
    mid: 0,
    high: 0,
    echo: 0,
};
function loadTTSConfig() {
    try {
        if (existsSync(TTS_CONFIG_PATH)) {
            return { ...DEFAULT_TTS, ...JSON.parse(readFileSync(TTS_CONFIG_PATH, 'utf-8')) };
        }
    }
    catch { }
    return { ...DEFAULT_TTS };
}
function saveTTSConfig(config) {
    writeFileSync(TTS_CONFIG_PATH, JSON.stringify(config, null, 2));
}
export const configRoutes = Router();
function loadLlmConfig() {
    const LLM_CONFIG_PATH = join(__dirname, '..', '..', 'llm-config.json');
    try {
        if (existsSync(LLM_CONFIG_PATH)) {
            return JSON.parse(readFileSync(LLM_CONFIG_PATH, 'utf-8'));
        }
    }
    catch { }
    return {
        primary: {
            provider: 'ollama',
            model: 'hf.co/mlabonne/gemma-3-12b-it-abliterated-GGUF:Q8_0',
            baseUrl: process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434/v1',
        },
    };
}
configRoutes.get('/llm', (_req, res) => {
    const config = loadLlmConfig();
    // Match the translator's precedence: dspark (preferred) → ollama → primary
    const primary = config.dspark || config.ollama || config.primary || {
        provider: 'ollama',
        model: 'hf.co/mlabonne/gemma-3-12b-it-abliterated-GGUF:Q8_0',
        baseUrl: process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434/v1',
    };
    res.json({
        primary: {
            provider: primary.provider || 'ollama',
            model: primary.model,
            baseUrl: primary.baseUrl,
        },
    });
});
// ─── TTS Config ────────────────────────────────────────────────────────────
configRoutes.get('/tts', (_req, res) => {
    res.json({ success: true, config: loadTTSConfig() });
});
configRoutes.post('/tts', (req, res) => {
    try {
        const partial = req.body.config || req.body;
        const current = loadTTSConfig();
        const updated = {
            voice: partial.voice ?? current.voice,
            speed: partial.speed ?? current.speed,
            pitch: partial.pitch ?? current.pitch,
            volume: partial.volume ?? current.volume,
            bass: partial.bass ?? current.bass,
            mid: partial.mid ?? current.mid,
            high: partial.high ?? current.high,
            echo: partial.echo ?? current.echo,
        };
        saveTTSConfig(updated);
        res.json({ success: true, config: updated });
    }
    catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});
