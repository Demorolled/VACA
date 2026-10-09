import OpenAI from 'openai';
import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
const __dirname = dirname(fileURLToPath(import.meta.url));
const LLM_CONFIG_PATH = join(__dirname, '..', '..', 'llm-config.json');
const DEFAULT_VISION_MODEL = 'vaca-vision-r3';
const DEFAULT_VISION_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434/v1';
const DEFAULT_VISION_API_KEY = 'ollama';
/**
 * Resolve the active vision model from llm-config.json.
 * Precedence: `vision` section (dedicated vision critic) → `ollama` → `primary`.
 */
export function getVisionConfig() {
    try {
        if (existsSync(LLM_CONFIG_PATH)) {
            const config = JSON.parse(readFileSync(LLM_CONFIG_PATH, 'utf-8'));
            const src = config.vision || config.ollama || config.primary || {};
            return {
                model: src.model || DEFAULT_VISION_MODEL,
                baseUrl: src.baseUrl || DEFAULT_VISION_BASE_URL,
                apiKey: src.apiKey || DEFAULT_VISION_API_KEY,
            };
        }
    }
    catch {
        /* fall through to defaults */
    }
    return {
        model: DEFAULT_VISION_MODEL,
        baseUrl: DEFAULT_VISION_BASE_URL,
        apiKey: DEFAULT_VISION_API_KEY,
    };
}
export async function describeImage(imageBase64, prompt) {
    try {
        const { model, baseUrl, apiKey } = getVisionConfig();
        const client = new OpenAI({
            baseURL: baseUrl,
            apiKey,
        });
        const dataUrl = `data:image/png;base64,${imageBase64}`;
        const response = await client.chat.completions.create({
            model,
            messages: [
                {
                    role: 'user',
                    content: [
                        { type: 'text', text: prompt },
                        { type: 'image_url', image_url: { url: dataUrl, detail: 'low' } },
                    ],
                },
            ],
            max_tokens: 512,
        });
        const description = response.choices?.[0]?.message?.content || '';
        if (description) {
            return { success: true, description, model_used: model };
        }
        return { success: false, error: 'No description returned from model' };
    }
    catch (err) {
        return { success: false, error: `Vision model failed: ${err.message}` };
    }
}
