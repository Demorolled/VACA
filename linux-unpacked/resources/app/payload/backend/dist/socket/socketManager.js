import { Server } from 'socket.io';
let io = null;
/** Cache of the last broadcast tool manifest — sent to newly connecting clients */
let _lastManifest = null;
let currentStatus = {
    thinking: false,
    progress: 0,
    isGenerating: false,
    generationLayer: 0,
    projectName: 'Untitled Project',
    targetOS: 'linux',
    nodeCount: 0,
    connected: false,
    timestamp: new Date().toISOString(),
};
export function getIO() {
    return io;
}
export function getCurrentStatus() {
    return { ...currentStatus };
}
export function updateStatus(partial) {
    currentStatus = {
        ...currentStatus,
        ...partial,
        timestamp: new Date().toISOString(),
    };
    if (io) {
        io.emit('status_update', currentStatus);
    }
}
export function broadcastIntent(intent) {
    if (io) {
        io.emit('intent', intent);
    }
}
export function broadcastGenerationProgress(progress) {
    if (io) {
        io.emit('generation_progress', progress);
    }
}
export function broadcastArchitectProgress(progress) {
    if (io) {
        io.emit('architect_progress', progress);
    }
}
export function broadcastToolManifest(formattedText, manifest) {
    _lastManifest = { formattedText, manifest };
    if (io) {
        io.emit('tool_manifest', { formattedText, manifest });
        console.log(`[Remote] Broadcast tool manifest to all clients (${manifest.length} tools)`);
    }
}
export function initializeSocketServer(httpServer) {
    io = new Server(httpServer, {
        cors: {
            origin: '*',
            methods: ['GET', 'POST'],
        },
        path: '/ws',
    });
    io.on('connection', (socket) => {
        console.log(`[Remote] Client connected: ${socket.id}`);
        socket.emit('status_update', currentStatus);
        socket.emit('connected', { id: socket.id, message: 'Connected to Veronica', agentId: socket.id });
        // Send cached tool manifest if available (for clients that connect after the one-shot broadcast)
        if (_lastManifest) {
            socket.emit('tool_manifest', _lastManifest);
        }
        socket.on('command', async (command) => {
            if (command.type === 'get_status') {
                socket.emit('status_update', currentStatus);
                return;
            }
            if (command.type === 'trigger_generate') {
                updateStatus({ thinking: true, isGenerating: true });
            }
            console.log(`[Remote] Command from ${socket.id}:`, command.type);
        });
        socket.on('disconnect', () => {
            console.log(`[Remote] Client disconnected: ${socket.id}`);
        });
    });
    console.log('[Remote] WebSocket server initialized on path /ws');
    return io;
}
