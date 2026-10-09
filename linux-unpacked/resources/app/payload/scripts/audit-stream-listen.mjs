#!/usr/bin/env node
// Claims-audit helper: connect to the same socket.io /ws channel the frontend
// uses, record every `generation_progress` event to a JSONL file (with
// timestamps), and exit once a `done` phase arrives (or after a timeout).
//
// Usage: node scripts/audit-stream-listen.mjs <outfile> [timeoutSeconds]
import { io } from 'socket.io-client';
import fs from 'fs';

const outfile = process.argv[2] || '/tmp/audit-stream.jsonl';
const timeoutSeconds = parseInt(process.argv[3] || '240', 10);
const started = Date.now();
const lines = [];

const log = (line) => {
  lines.push(line);
  try { fs.appendFileSync(outfile, line + '\n'); } catch {}
};

const socket = io('http://127.0.0.1:3001', {
  path: '/ws',
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionDelay: 1000,
});

socket.on('connect', () => log(JSON.stringify({ at: Date.now(), type: 'connect', sid: socket.id })));
socket.on('connect_error', (e) => log(JSON.stringify({ at: Date.now(), type: 'connect_error', msg: String(e.message).slice(0, 120) })));

socket.on('generation_progress', (d) => {
  log(JSON.stringify({ at: Date.now(), type: 'generation_progress', phase: d.phase, percent: d.percent, message: d.message || '', batch: d.batch, totalBatches: d.totalBatches, nodes: d.generatingNodes || [] }));
  if (d.phase === 'done') {
    // Give the write-code HTTP response a moment to flush, then exit cleanly.
    setTimeout(() => process.exit(0), 1500);
  }
});

socket.on('architect_progress', (d) => {
  log(JSON.stringify({ at: Date.now(), type: 'architect_progress', phase: d.phase, percent: d.percent, message: d.message || '' }));
});

setTimeout(() => {
  log(JSON.stringify({ at: Date.now(), type: 'timeout' }));
  process.exit(0);
}, timeoutSeconds * 1000);
