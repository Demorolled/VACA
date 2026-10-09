#!/usr/bin/env node
/**
 * monitor-ws.mjs — connect to VACA's Socket.IO endpoint and print app-action
 * events (status_update, intent, generation_progress, architect_progress,
 * tool_manifest) to stdout, one JSON per line. Spawned by monitor-vaca.py;
 * exits when stdin closes or after a fatal connect error.
 *
 * Usage: node scripts/monitor-ws.mjs [base-url]   (default http://127.0.0.1:3001)
 */
import { io } from 'socket.io-client';

const base = process.argv[2] || 'http://127.0.0.1:3001';
const WATCH = ['status_update', 'intent', 'generation_progress', 'architect_progress', 'tool_manifest'];

const s = io(base, { transports: ['websocket'], path: '/ws', reconnection: true, reconnectionDelay: 2000 });

s.on('connect', () => console.log(JSON.stringify({ ws: 'connected', id: s.id })));
s.on('connect_error', (e) => console.log(JSON.stringify({ ws: 'connect_error', error: String(e && e.message || e) })));
s.on('disconnect', (reason) => console.log(JSON.stringify({ ws: 'disconnected', reason })));

for (const name of WATCH) {
  s.on(name, (data) => console.log(JSON.stringify({ ws: name, data })));
}

process.stdin.on('data', () => { /* keep-alive: stdin open keeps the event loop alive */ });
