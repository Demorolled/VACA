/**
 * GPU-accelerated RNN using TensorFlow.js layers API.
 * Same external API as rnn.ts but training runs on GPU via
 * @tensorflow/tfjs-node-gpu (CUDA) or @tensorflow/tfjs (CPU/WASM).
 *
 * Falls back to the CPU rnn.ts if TensorFlow.js is not installed.
 */
import { DEFAULT_RNN_CONFIG } from './rnn.js';
export { DEFAULT_RNN_CONFIG };
// tf is loaded lazily — the import is dynamic and guarded by try/catch.
// TypeScript errors for the module are suppressed because this is an
// optional runtime dependency. tf-related values are typed as `any`.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let tf = null;
let tfReady = false;
async function initTF() {
    if (tfReady)
        return true;
    try {
        // @ts-ignore — optional dependency, installed at runtime
        tf = await import('@tensorflow/tfjs');
        await tf.ready();
        tfReady = true;
        console.log(`[rnnGPU] TensorFlow.js active (backend: ${tf.getBackend()})`);
        return true;
    }
    catch {
        console.warn('[rnnGPU] TensorFlow.js not available — using CPU RNN fallback');
        return false;
    }
}
let gpuModel = null;
/**
 * Create or rebuild the GPU model when vocab size changes.
 */
async function ensureModel(config) {
    if (gpuModel && gpuModel.vocabSize === config.vocabSize && gpuModel.hiddenSize === config.hiddenSize) {
        return gpuModel;
    }
    // Dispose previous model
    if (gpuModel) {
        gpuModel.model.dispose();
        gpuModel = null;
    }
    const model = tf.sequential();
    model.add(tf.layers.embedding({ inputDim: config.vocabSize, outputDim: config.hiddenSize }));
    model.add(tf.layers.simpleRNN({ units: config.hiddenSize, activation: 'tanh', returnSequences: false }));
    model.add(tf.layers.dense({ units: config.vocabSize, activation: 'softmax' }));
    model.compile({
        optimizer: tf.train.adagrad(config.learningRate),
        loss: 'sparseCategoricalCrossentropy',
    });
    // Dummy warmup pass to initialize weights on GPU
    const dummy = tf.zeros([1, 1], 'int32');
    model.predict(dummy);
    dummy.dispose();
    gpuModel = { model, vocabSize: config.vocabSize, hiddenSize: config.hiddenSize, iter: 0, smoothLoss: 0, learningRate: config.learningRate };
    console.log(`[rnnGPU] Model created: vocab=${config.vocabSize} hidden=${config.hiddenSize}`);
    return gpuModel;
}
/**
 * Train the GPU model on a sequence of character indices.
 * Returns average loss.
 */
export async function rnnTrainStepGPU(config, inputs) {
    if (!await initTF()) {
        return { loss: 0 };
    }
    const m = await ensureModel(config);
    const seqLen = Math.min(inputs.length, config.seqLength);
    if (seqLen < 2)
        return { loss: 0 };
    // Input: [0..seqLen-2], target: [1..seqLen-1]
    const inArr = inputs.slice(0, seqLen - 1);
    const tgtArr = inputs.slice(1, seqLen);
    const xs = tf.tensor2d(inArr, [1, inArr.length], 'int32');
    const ys = tf.tensor1d(tgtArr, 'int32');
    const hist = await m.model.fit(xs, ys, {
        epochs: 1,
        batchSize: inArr.length,
        verbose: 0,
    });
    const lossVal = hist.history.loss[0];
    m.smoothLoss = m.smoothLoss === 0 ? lossVal : m.smoothLoss * 0.999 + lossVal * 0.001;
    m.iter++;
    xs.dispose();
    ys.dispose();
    return { loss: lossVal };
}
/**
 * Generate text from the GPU model step by step.
 * Feeds the growing context through the full model each step.
 */
export async function rnnGenerateGPU(config, seedChar, length, temperature = 0.8) {
    if (!await initTF()) {
        const cpu = await import('./rnn.js');
        const dummyState = new cpu.RNNState(config);
        return cpu.rnnGenerate(dummyState, seedChar, length, temperature);
    }
    const m = await ensureModel(config);
    const output = [seedChar];
    const states = [new Array(config.hiddenSize).fill(0)];
    for (let step = 0; step < length - 1; step++) {
        const ctx = output.slice(Math.max(0, output.length - 50));
        const input = tf.tensor2d([ctx], [1, ctx.length], 'int32');
        const pred = m.model.predict(input);
        const logits = pred.div(tf.scalar(temperature));
        const probs = tf.softmax(logits);
        const probsArr = Array.from(await probs.data());
        const r = Math.random();
        let cumulative = 0;
        let chosenIdx = config.vocabSize - 1;
        for (let i = 0; i < probsArr.length; i++) {
            cumulative += probsArr[i];
            if (r < cumulative) {
                chosenIdx = i;
                break;
            }
        }
        output.push(chosenIdx);
        states.push(new Array(config.hiddenSize).fill(0));
        input.dispose();
        pred.dispose();
        logits.dispose();
        probs.dispose();
    }
    return { text: output, states };
}
/**
 * Check if GPU acceleration is available.
 */
export async function isGPUAvailable() {
    if (!await initTF())
        return false;
    return true;
}
export default { rnnTrainStepGPU, rnnGenerateGPU, isGPUAvailable };
