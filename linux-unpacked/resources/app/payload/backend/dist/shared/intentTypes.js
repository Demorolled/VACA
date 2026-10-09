export function createIntent(type, payload, source = 'terminal') {
    return {
        type,
        payload,
        source,
        timestamp: new Date().toISOString(),
        id: `intent_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    };
}
