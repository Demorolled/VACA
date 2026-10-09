/**
 * A minimal character-level Venorica implemented from scratch in pure TypeScript.
 * No external ML libraries - just math.
 * Architecture: Embedding -> Venorica (tanh) -> Dense -> Softmax
 */
export const DEFAULT_RNN_CONFIG = {
    vocabSize: 100,
    hiddenSize: 128,
    learningRate: 0.01,
    seqLength: 64,
};
/**
 * Vector/Matrix utilities
 */
function matVecMul(mat, vec) {
    const result = new Array(mat.length).fill(0);
    for (let i = 0; i < mat.length; i++) {
        for (let j = 0; j < vec.length; j++) {
            result[i] += mat[i][j] * vec[j];
        }
    }
    return result;
}
function vecAdd(a, b) {
    return a.map((v, i) => v + (b[i] || 0));
}
function vecScale(vec, scale) {
    return vec.map(v => isFinite(v) ? v * scale : 0);
}
function vecCopy(vec) {
    return [...vec];
}
/** Tanh activation and its derivative */
function tanh(x) {
    if (x > 20)
        return 1;
    if (x < -20)
        return -1;
    const e2x = Math.exp(2 * x);
    const result = (e2x - 1) / (e2x + 1);
    return isNaN(result) ? (x > 0 ? 1 : -1) : result;
}
function tanhDeriv(y) {
    return 1 - y * y;
}
/**
 * Softmax function for output probabilities
 */
function softmax(x) {
    const maxVal = Math.max(...x);
    // Subtract max for numerical stability, clip inputs to prevent exp overflow
    const exps = x.map(v => {
        const diff = v - maxVal;
        if (diff > 50)
            return Infinity;
        if (diff < -50)
            return 0;
        return Math.exp(diff);
    });
    const sum = exps.reduce((a, b) => a + b, 0);
    if (sum === Infinity || sum === 0 || isNaN(sum)) {
        // Fallback: uniform distribution
        return x.map(() => 1 / x.length);
    }
    return exps.map(v => v / sum);
}
/** Cross-entropy loss */
function crossEntropy(pred, targetIdx) {
    return -Math.log(Math.max(pred[targetIdx], 1e-10));
}
/** Random number with Gaussian distribution (Box-Muller) */
function randn() {
    let u = 0, v = 0;
    while (u === 0)
        u = Math.random();
    while (v === 0)
        v = Math.random();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}
/**
 * Venorica State - holds all parameters for the model
 */
export class RNNState {
    // Weight matrices
    Wxh; // input -> hidden
    Whh; // hidden -> hidden
    Why; // hidden -> output
    // Bias vectors
    bh; // hidden bias
    by; // output bias
    // Gradients
    dWxh;
    dWhh;
    dWhy;
    dbh;
    dby;
    // Optimizer state (AdaGrad)
    mWxh;
    mWhh;
    mWhy;
    mbh;
    mby;
    // Config
    config;
    // Training stats
    iter = 0;
    smoothLoss = 0;
    constructor(config) {
        this.config = { ...config };
        const { vocabSize, hiddenSize } = config;
        // Initialize weights with small random values
        this.Wxh = this.initMat(hiddenSize, vocabSize, 0.01);
        this.Whh = this.initMat(hiddenSize, hiddenSize, 0.01);
        this.Why = this.initMat(vocabSize, hiddenSize, 0.01);
        this.bh = new Array(hiddenSize).fill(0);
        this.by = new Array(vocabSize).fill(0);
        // Initialize gradients
        this.dWxh = this.initMat(hiddenSize, vocabSize, 0);
        this.dWhh = this.initMat(hiddenSize, hiddenSize, 0);
        this.dWhy = this.initMat(vocabSize, hiddenSize, 0);
        this.dbh = new Array(hiddenSize).fill(0);
        this.dby = new Array(vocabSize).fill(0);
        // Initialize AdaGrad memory
        this.mWxh = this.initMat(hiddenSize, vocabSize, 0);
        this.mWhh = this.initMat(hiddenSize, hiddenSize, 0);
        this.mWhy = this.initMat(vocabSize, hiddenSize, 0);
        this.mbh = new Array(hiddenSize).fill(0);
        this.mby = new Array(vocabSize).fill(0);
    }
    initMat(rows, cols, scale) {
        return Array.from({ length: rows }, () => Array.from({ length: cols }, () => randn() * scale));
    }
    /**
     * Expand vocabulary to accommodate new tokens without resetting weights.
     * Grows the weight matrices by adding new columns/rows initialized with small random values.
     * Existing weights are preserved so all training progress is retained.
     */
    expandVocabulary(newVocabSize) {
        const oldVocabSize = this.config.vocabSize;
        if (newVocabSize <= oldVocabSize)
            return;
        const { hiddenSize } = this.config;
        // Wxh: hiddenSize x vocabSize — add new columns (new input→hidden weights)
        for (let i = 0; i < hiddenSize; i++) {
            for (let j = oldVocabSize; j < newVocabSize; j++) {
                this.Wxh[i][j] = randn() * 0.01;
                this.dWxh[i][j] = 0;
                this.mWxh[i][j] = 0;
            }
        }
        // Why: vocabSize x hiddenSize — add new rows (new hidden→output weights)
        for (let i = oldVocabSize; i < newVocabSize; i++) {
            this.Why[i] = new Array(hiddenSize);
            this.dWhy[i] = new Array(hiddenSize);
            this.mWhy[i] = new Array(hiddenSize);
            for (let j = 0; j < hiddenSize; j++) {
                this.Why[i][j] = randn() * 0.01;
                this.dWhy[i][j] = 0;
                this.mWhy[i][j] = 0;
            }
        }
        // by: vocabSize — add new bias elements
        for (let i = oldVocabSize; i < newVocabSize; i++) {
            this.by[i] = 0;
            this.dby[i] = 0;
            this.mby[i] = 0;
        }
        this.config.vocabSize = newVocabSize;
        console.log(`[Venorica] Expanded vocab: ${oldVocabSize} -> ${newVocabSize} (weights preserved)`);
    }
    /** Get serializable snapshot for saving */
    toJSON() {
        return {
            config: this.config,
            Wxh: this.Wxh,
            Whh: this.Whh,
            Why: this.Why,
            bh: this.bh,
            by: this.by,
            iter: this.iter,
            smoothLoss: this.smoothLoss,
        };
    }
    /** Load from snapshot */
    fromJSON(data) {
        this.config = data.config;
        this.Wxh = data.Wxh;
        this.Whh = data.Whh;
        this.Why = data.Why;
        this.bh = data.bh;
        this.by = data.by;
        this.iter = data.iter || 0;
        this.smoothLoss = data.smoothLoss || 0;
        // Recreate gradient and optimizer buffers
        const { vocabSize, hiddenSize } = this.config;
        this.dWxh = this.initMat(hiddenSize, vocabSize, 0);
        this.dWhh = this.initMat(hiddenSize, hiddenSize, 0);
        this.dWhy = this.initMat(vocabSize, hiddenSize, 0);
        this.dbh = new Array(hiddenSize).fill(0);
        this.dby = new Array(vocabSize).fill(0);
        this.mWxh = this.initMat(hiddenSize, vocabSize, 0);
        this.mWhh = this.initMat(hiddenSize, hiddenSize, 0);
        this.mWhy = this.initMat(vocabSize, hiddenSize, 0);
        this.mbh = new Array(hiddenSize).fill(0);
        this.mby = new Array(vocabSize).fill(0);
    }
}
/**
 * Stores the computation graph for a single time step
 */
class RNNGate {
    hs = []; // hidden state output
    xs = []; // input one-hot
    raw = []; // pre-tanh hidden state
    ps = []; // output probabilities
}
/**
 * Forward pass of the Venorica for a sequence of inputs
 */
export function rnnForward(model, inputs, hprev) {
    const { vocabSize, hiddenSize } = model.config;
    const gates = [];
    let loss = 0;
    let h = vecCopy(hprev);
    for (let t = 0; t < inputs.length; t++) {
        const gate = new RNNGate();
        // One-hot encode input
        gate.xs = new Array(vocabSize).fill(0);
        gate.xs[inputs[t]] = 1.0;
        // Hidden state: h = tanh(Wxh * x + Whh * h_prev + bh)
        const wxh = matVecMul(model.Wxh, gate.xs);
        const whh = matVecMul(model.Whh, h);
        gate.raw = vecAdd(vecAdd(wxh, whh), model.bh);
        gate.hs = gate.raw.map(v => tanh(v));
        // Output: y = Why * h + by
        const y = vecAdd(matVecMul(model.Why, gate.hs), model.by);
        // Softmax probabilities
        gate.ps = softmax(y);
        // Cross-entropy loss (predict next char)
        if (t + 1 < inputs.length) {
            loss += crossEntropy(gate.ps, inputs[t + 1]);
        }
        gates.push(gate);
        h = gate.hs;
    }
    return { gates, loss, h };
}
/**
 * Backpropagation through time
 */
export function rnnBackward(model, inputs, gates, hprev) {
    const { vocabSize, hiddenSize } = model.config;
    // Zero gradients
    model.dWxh = model.initMat(hiddenSize, vocabSize, 0);
    model.dWhh = model.initMat(hiddenSize, hiddenSize, 0);
    model.dWhy = model.initMat(vocabSize, hiddenSize, 0);
    model.dbh = new Array(hiddenSize).fill(0);
    model.dby = new Array(vocabSize).fill(0);
    let dhNext = new Array(hiddenSize).fill(0);
    for (let t = gates.length - 1; t >= 0; t--) {
        const gate = gates[t];
        const targetIdx = t + 1 < inputs.length ? inputs[t + 1] : inputs[inputs.length - 1];
        // Gradient of output: dL/dy = p - target
        const dy = [...gate.ps];
        dy[targetIdx] -= 1.0;
        // dWhy = dy * h^T
        for (let i = 0; i < vocabSize; i++) {
            for (let j = 0; j < hiddenSize; j++) {
                model.dWhy[i][j] += dy[i] * gate.hs[j];
            }
        }
        // dby = dy
        for (let i = 0; i < vocabSize; i++) {
            model.dby[i] += dy[i];
        }
        // dh = Why^T * dy + dhNext
        let dh = new Array(hiddenSize).fill(0);
        for (let i = 0; i < hiddenSize; i++) {
            for (let j = 0; j < vocabSize; j++) {
                dh[i] += model.Why[j][i] * dy[j];
            }
            dh[i] += dhNext[i];
        }
        // Backprop through tanh: dtanh = dh * (1 - h^2)
        const dtanh = dh.map((d, i) => d * tanhDeriv(gate.hs[i]));
        // dWxh = dtanh * x^T
        for (let i = 0; i < hiddenSize; i++) {
            for (let j = 0; j < vocabSize; j++) {
                model.dWxh[i][j] += dtanh[i] * gate.xs[j];
            }
        }
        // dWhh = dtanh * h_{t-1}^T
        const hPrev = t > 0 ? gates[t - 1].hs : hprev;
        for (let i = 0; i < hiddenSize; i++) {
            for (let j = 0; j < hiddenSize; j++) {
                model.dWhh[i][j] += dtanh[i] * hPrev[j];
            }
        }
        // dbh = dtanh
        for (let i = 0; i < hiddenSize; i++) {
            model.dbh[i] += dtanh[i];
        }
        // dhNext = Whh^T * dtanh
        dhNext = new Array(hiddenSize).fill(0);
        for (let i = 0; i < hiddenSize; i++) {
            for (let j = 0; j < hiddenSize; j++) {
                dhNext[i] += model.Whh[j][i] * dtanh[j];
            }
        }
    }
}
/**
 * Update weights using AdaGrad
 */
export function rnnUpdate(model) {
    const lr = model.config.learningRate;
    const eps = 1e-8;
    function updateWeight(mat, grad, mem) {
        for (let i = 0; i < mat.length; i++) {
            for (let j = 0; j < mat[0].length; j++) {
                mem[i][j] += grad[i][j] * grad[i][j];
                mat[i][j] -= lr * grad[i][j] / (Math.sqrt(mem[i][j]) + eps);
            }
        }
    }
    function updateBias(vec, grad, mem) {
        for (let i = 0; i < vec.length; i++) {
            mem[i] += grad[i] * grad[i];
            vec[i] -= lr * grad[i] / (Math.sqrt(mem[i]) + eps);
        }
    }
    updateWeight(model.Wxh, model.dWxh, model.mWxh);
    updateWeight(model.Whh, model.dWhh, model.mWhh);
    updateWeight(model.Why, model.dWhy, model.mWhy);
    updateBias(model.bh, model.dbh, model.mbh);
    updateBias(model.by, model.dby, model.mby);
}
/**
 * Train the Venorica on a single batch of data
 */
export function rnnTrainStep(model, inputs, hprev) {
    // Forward pass
    const { gates, loss, h } = rnnForward(model, inputs, hprev);
    // Backward pass
    rnnBackward(model, inputs, gates, hprev);
    // Clip gradients to prevent explosion
    clipGradients(model, 5.0);
    // Update weights
    rnnUpdate(model);
    return { loss, h };
}
function clipGradients(model, maxNorm) {
    let totalNorm = 0;
    function addGradNorm(mat) {
        for (const row of mat) {
            for (const g of row) {
                if (isFinite(g))
                    totalNorm += g * g;
            }
        }
    }
    // Also include bias gradients in norm computation
    for (const g of model.dbh)
        if (isFinite(g))
            totalNorm += g * g;
    for (const g of model.dby)
        if (isFinite(g))
            totalNorm += g * g;
    addGradNorm(model.dWxh);
    addGradNorm(model.dWhh);
    addGradNorm(model.dWhy);
    totalNorm = Math.sqrt(totalNorm);
    // Check for NaN/Inf in totalNorm
    if (!isFinite(totalNorm) || totalNorm === 0) {
        // Reset all gradients to prevent NaN propagation
        const { vocabSize, hiddenSize } = model.config;
        model.dWxh = model.initMat(hiddenSize, vocabSize, 0);
        model.dWhh = model.initMat(hiddenSize, hiddenSize, 0);
        model.dWhy = model.initMat(vocabSize, hiddenSize, 0);
        model.dbh = new Array(hiddenSize).fill(0);
        model.dby = new Array(vocabSize).fill(0);
        return;
    }
    if (totalNorm > maxNorm) {
        const scale = maxNorm / totalNorm;
        function scaleGrad(mat) {
            for (let i = 0; i < mat.length; i++) {
                for (let j = 0; j < mat[0].length; j++) {
                    if (isFinite(mat[i][j]))
                        mat[i][j] *= scale;
                }
            }
        }
        scaleGrad(model.dWxh);
        scaleGrad(model.dWhh);
        scaleGrad(model.dWhy);
        model.dbh = vecScale(model.dbh, scale);
        model.dby = vecScale(model.dby, scale);
    }
}
/**
 * Generate text from the RNN
 */
export function rnnGenerate(model, seedChar, length, temperature = 0.8) {
    const { vocabSize, hiddenSize } = model.config;
    let h = new Array(hiddenSize).fill(0);
    let x = new Array(vocabSize).fill(0);
    x[seedChar] = 1.0;
    const output = [seedChar];
    const states = [h];
    for (let t = 0; t < length - 1; t++) {
        // Forward pass one step
        const wxh = matVecMul(model.Wxh, x);
        const whh = matVecMul(model.Whh, h);
        const raw = vecAdd(vecAdd(wxh, whh), model.bh);
        h = raw.map(v => tanh(v));
        const y = vecAdd(matVecMul(model.Why, h), model.by);
        // Apply temperature
        const adjustedY = y.map(v => v / temperature);
        const ps = softmax(adjustedY);
        // Sample from the distribution
        const idx = sampleFromDistribution(ps);
        output.push(idx);
        states.push(h);
        // Set next input
        x = new Array(vocabSize).fill(0);
        x[idx] = 1.0;
    }
    return { text: output, states };
}
function sampleFromDistribution(probs) {
    const r = Math.random();
    let cumulative = 0;
    for (let i = 0; i < probs.length; i++) {
        cumulative += probs[i];
        if (r < cumulative)
            return i;
    }
    return probs.length - 1;
}
/**
 * Initialize hidden state (zeros)
 */
export function initHiddenState(model) {
    return new Array(model.config.hiddenSize).fill(0);
}
/**
 * Save model to JSON string
 */
export function saveModel(model) {
    return JSON.stringify(model.toJSON());
}
/**
 * Load model from JSON string
 */
export function loadModel(json, config) {
    const data = JSON.parse(json);
    const cfg = config || data.config || DEFAULT_RNN_CONFIG;
    const model = new RNNState(cfg);
    model.fromJSON(data);
    return model;
}
