#!/usr/bin/env node
// Watch the live generation_progress stream on the same /ws channel the frontend uses.
// Logs every event with an ISO timestamp so we can prove the stream is live during a write.
import { io } from 'socket.io-client';

const socket = io('http://127.0.0.1:3001', {
  path: '/ws',
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionDelay: 2000,
});

const log = (line) => console.log(`[${new Date().toISOString()}] ${line}`);

socket.on('connect', () => log(`CONNECTED ${socket.id}`));
socket.on('disconnect', () => log('DISCONNECTED'));
socket.on('connect_error', (e) => log(`CONNECT_ERROR ${e.message}`));
socket.on('generation_progress', (d) => {
  const nodes = (d.generatingNodes || []).join(',');
  log(`generation_progress phase=${d.phase} percent=${d.percent} msg="${d.message || ''}" batch=${d.batch ?? '-'}/${d.totalBatches ?? '-'} nodes=${nodes}`);
});
socket.on('architect_progress', (d) => {
  log(`architect_progress phase=${d.phase} percent=${d.percent} msg="${d.message || ''}"`);
});

log('listener started, waiting for events (max 20 min)');
setTimeout(() => { log('listener timeout after 20min'); process.exit(0); }, 20 * 60 * 1000);
