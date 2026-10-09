/**
 * Shared training-metric helpers for the Venorica RNN training scripts
 * (train-venorica.ts, extend-training.ts, train-100k.ts).
 *
 * Why perplexity, not raw loss:
 *   The model's reported `loss` is the SUM of per-char cross-entropy over a
 *   seqLength-window, so its absolute scale depends on the tokenizer
 *   vocabulary size. Comparing raw loss across runs where new patterns
 *   expanded the vocab produced absurd numbers (e.g. "-1463% loss reduction"
 *   when a 97 → 151 vocab expansion legitimately raised the loss scale).
 *   Perplexity = exp(loss / seqLength) is the vocab-independent per-character
 *   uncertainty metric, so improvement computed on it is honest across runs.
 */
/** Perplexity of a status snapshot, or null when unavailable. */
export function perplexityOf(status) {
    if (!status || !status.loss)
        return null;
    // Same seqLength default everywhere so displayed perplexities never disagree.
    return Math.exp(status.loss / (status.seqLength || 64));
}
/** Format a perplexity for display (fixed 2dp, or 'n/a'). */
export function fmtPpl(ppl) {
    return ppl === null ? 'n/a' : ppl.toFixed(2);
}
/**
 * Human-readable improvement line comparing two status snapshots.
 * - Same vocab:   "X% perplexity reduction (pre → post)"
 * - Vocab change: "n/a — tokenizer vocab changed A → B (perplexity a → b)"
 * - Missing data: "n/a (no pre/post loss available)"
 */
export function describeImprovement(pre, post) {
    const prePpl = perplexityOf(pre);
    const postPpl = perplexityOf(post);
    if (prePpl === null || postPpl === null) {
        return 'n/a (no pre/post loss available)';
    }
    if (pre?.vocabSize !== post?.vocabSize) {
        return `n/a — tokenizer vocab changed ${pre?.vocabSize ?? '?'} → ${post?.vocabSize ?? '?'} (perplexity ${fmtPpl(prePpl)} → ${fmtPpl(postPpl)})`;
    }
    const delta = ((prePpl - postPpl) / prePpl) * 100;
    return `${delta.toFixed(1)}% perplexity reduction (${fmtPpl(prePpl)} → ${fmtPpl(postPpl)})`;
}
