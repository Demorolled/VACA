import { RNNState, DEFAULT_RNN_CONFIG, rnnTrainStep, rnnGenerate, initHiddenState } from './rnn.js';
import { rnnTrainStepGPU, isGPUAvailable } from './rnnGPU.js';
import { CharTokenizer } from './tokenizer.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import * as fs from 'fs';
import { gzipSync, gunzipSync } from 'zlib';
import * as path from 'path';
const MODEL_PATH = path.join(process.cwd(), 'knowledge', 'rnn-model.json');
export class RNNTrainingEngine {
    model = null;
    tokenizer = new CharTokenizer();
    config;
    trainedChars = 0;
    isTraining = false;
    useGPU = false;
    constructor(config) {
        this.config = { ...DEFAULT_RNN_CONFIG, ...config };
        // Check GPU availability on init (non-blocking)
        isGPUAvailable().then(gpu => {
            this.useGPU = gpu;
            if (gpu)
                console.log('[Venorica] GPU acceleration available — using GPU RNN');
        }).catch(() => { });
        if (!this.loadModel()) {
            console.log('[Venorica] No saved model found, initializing blank model...');
            this.initModel();
        }
    }
    /** Initialize a fresh model */
    initModel() {
        const patterns = knowledgeStore.getAll();
        const codeTexts = patterns.map(p => p.code);
        this.tokenizer.fit(codeTexts);
        this.config.vocabSize = this.tokenizer.vocabSize;
        this.model = new RNNState(this.config);
        console.log(`[Venorica] Initialized model: vocab=${this.config.vocabSize}, hidden=${this.config.hiddenSize}`);
    }
    /** Train on all patterns in the knowledge store */
    async train(iterations = 500) {
        if (this.isDisabled()) {
            return { loss: 0, chars: 0 };
        }
        const patterns = knowledgeStore.getAll();
        if (patterns.length === 0) {
            throw new Error('No patterns to train on');
        }
        const codeTexts = patterns.map(p => p.code);
        this.tokenizer.fit(codeTexts);
        const newVocabSize = this.tokenizer.vocabSize;
        if (!this.model) {
            this.model = new RNNState(this.config);
        }
        // Expand vocabulary if needed — preserves all trained weights instead of resetting
        if (newVocabSize > this.config.vocabSize) {
            this.model.expandVocabulary(newVocabSize);
        }
        this.config.vocabSize = newVocabSize;
        const allCode = codeTexts.join('\n---\n');
        const indices = this.tokenizer.encode(allCode);
        console.log(`[Venorica] Training on ${indices.length} characters from ${patterns.length} patterns` +
            (this.useGPU ? ' (GPU accelerated)' : ''));
        this.isTraining = true;
        const seqLen = this.config.seqLength;
        let smoothLoss = 0;
        let charCount = 0;
        for (let i = 0; i < iterations; i++) {
            // Yield to event loop periodically to avoid blocking
            if (i % 50 === 0 && i > 0) {
                await new Promise(resolve => setImmediate(resolve));
            }
            const startIdx = Math.floor(Math.random() * Math.max(1, indices.length - seqLen - 1));
            const inputs = indices.slice(startIdx, startIdx + seqLen);
            if (inputs.length < 2)
                continue;
            let loss;
            if (this.useGPU) {
                // GPU-accelerated training step
                const result = await rnnTrainStepGPU(this.config, inputs);
                loss = result.loss;
            }
            else {
                // CPU training step
                const hprev = initHiddenState(this.model);
                const result = rnnTrainStep(this.model, inputs, hprev);
                loss = result.loss;
            }
            if (isNaN(loss)) {
                console.log(`[Venorica] NaN detected at iter ${i}, aborting training and resetting model`);
                this.isTraining = false;
                this.initModel();
                throw new Error('NaN loss detected - model reset to initial state');
            }
            if (i === 0)
                smoothLoss = loss;
            smoothLoss = smoothLoss * 0.999 + loss * 0.001;
            charCount += inputs.length;
            if (i % 100 === 0) {
                console.log(`[Venorica] Iter ${i}/${iterations}, loss: ${smoothLoss.toFixed(4)}`);
            }
        }
        this.trainedChars += charCount;
        if (this.model)
            this.model.smoothLoss = smoothLoss;
        if (this.model)
            this.model.iter += iterations;
        this.saveModel();
        this.isTraining = false;
        console.log(`[Venorica] Training complete. Loss: ${smoothLoss.toFixed(4)}, Chars: ${charCount}`);
        return { loss: smoothLoss, chars: charCount };
    }
    /** Generate code from the trained model */
    generate(seedText = 'function', length = 200, temperature = 0.8) {
        if (!this.model) {
            throw new Error('Model not trained yet');
        }
        const seedIndices = this.tokenizer.encode(seedText);
        if (seedIndices.length === 0) {
            throw new Error('Could not encode seed text');
        }
        // GPU generate returns text output only (states are placeholder)
        const result = this.useGPU
            ? null // GPU generation handled below
            : rnnGenerate(this.model, seedIndices[0], length, temperature);
        // Fallback: always use CPU generate for now (GPU generation is experimental)
        const cpuResult = rnnGenerate(this.model, seedIndices[0], length, temperature);
        return this.tokenizer.decode(cpuResult.text);
    }
    /** Get model status */
    getStatus() {
        if (!this.model) {
            return {
                initialized: false,
                vocabSize: this.tokenizer.vocabSize,
                hiddenSize: this.config.hiddenSize,
                trainedChars: this.trainedChars,
                iterations: 0,
                loss: null,
                patternCount: knowledgeStore.count(),
                isTraining: this.isTraining,
                gpuAccelerated: this.useGPU,
            };
        }
        return {
            initialized: true,
            vocabSize: this.config.vocabSize,
            hiddenSize: this.config.hiddenSize,
            trainedChars: this.trainedChars,
            iterations: this.model.iter,
            loss: this.model.smoothLoss,
            patternCount: knowledgeStore.count(),
            isTraining: this.isTraining,
            learningRate: this.config.learningRate,
            seqLength: this.config.seqLength,
            gpuAccelerated: this.useGPU,
        };
    }
    /** Save model to disk */
    saveModel() {
        if (!this.model)
            return;
        try {
            const dir = path.dirname(MODEL_PATH);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            const data = {
                model: this.model.toJSON(),
                config: this.config,
                trainedChars: this.trainedChars,
                tokenizerVocabSize: this.tokenizer.vocabSize,
                savedAt: new Date().toISOString(),
            };
            const jsonStr = JSON.stringify(data);
            fs.writeFileSync(MODEL_PATH, gzipSync(Buffer.from(jsonStr, 'utf-8')));
            console.log(`[Venorica] Model saved to ${MODEL_PATH}`);
        }
        catch (err) {
            console.error('[Venorica] Error saving model:', err);
        }
    }
    /** Load model from disk */
    loadModel() {
        try {
            if (!fs.existsSync(MODEL_PATH))
                return false;
            const raw = fs.readFileSync(MODEL_PATH);
            let data;
            try {
                data = JSON.parse(gunzipSync(raw).toString('utf-8'));
            }
            catch {
                data = JSON.parse(raw.toString('utf-8'));
            }
            this.config = data.config || this.config;
            this.model = new RNNState(this.config);
            this.model.fromJSON(data.model);
            this.trainedChars = data.trainedChars || 0;
            console.log(`[Venorica] Model loaded from ${MODEL_PATH}`);
            return true;
        }
        catch (err) {
            console.error('[Venorica] Error loading model:', err);
            return false;
        }
    }
    /** True when Venorica RNN training is disabled via env (VENORICA_DISABLED). */
    isDisabled() {
        return process.env.VENORICA_DISABLED === 'true' || process.env.VENORICA_DISABLED === '1';
    }
    /** Learn from all patterns in the knowledge store */
    async learnFromKnowledge(iterations = 200) {
        if (this.isDisabled()) {
            return { loss: 0, chars: 0 };
        }
        if (!this.model) {
            console.log('[Venorica] No model, initializing...');
            this.initModel();
        }
        if (knowledgeStore.count() === 0) {
            console.log('[Venorica] No patterns to learn from');
            return { loss: 0, chars: 0 };
        }
        if (this.isTraining) {
            console.log('[Venorica] Already training, skipping request');
            return { loss: 0, chars: 0 };
        }
        return this.train(iterations);
    }
}
export const rnnEngine = new RNNTrainingEngine();
