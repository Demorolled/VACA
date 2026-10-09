import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as zlib from 'zlib';
import { jarManifestInfo } from './nonTsCompileGate.js';
/**
 * Build a minimal single-entry jar by hand. `method` 0 stores the manifest
 * (kotlinc stores it uncompressed) and 8 deflates it, so both branches of the
 * reader are exercised. The reader never verifies the CRC, so it is left zero.
 */
function makeJar(manifest, method) {
    const name = 'META-INF/MANIFEST.MF';
    const nameBuf = Buffer.from(name, 'utf8');
    const data = Buffer.from(manifest === null ? '' : manifest, 'utf8');
    const stored = method === 0 ? data : zlib.deflateRawSync(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(method, 8);
    local.writeUInt32LE(stored.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    const cd = Buffer.alloc(46);
    cd.writeUInt32LE(0x02014b50, 0);
    cd.writeUInt16LE(20, 4);
    cd.writeUInt16LE(20, 6);
    cd.writeUInt16LE(method, 10);
    cd.writeUInt32LE(stored.length, 20);
    cd.writeUInt32LE(data.length, 24);
    cd.writeUInt16LE(nameBuf.length, 28);
    cd.writeUInt32LE(0, 42); // local header offset
    const cdStart = 30 + nameBuf.length + stored.length;
    const cdSize = 46 + nameBuf.length;
    const eocd = Buffer.alloc(22);
    eocd.writeUInt32LE(0x06054b50, 0);
    eocd.writeUInt16LE(1, 8);
    eocd.writeUInt16LE(1, 10);
    eocd.writeUInt32LE(cdSize, 12);
    eocd.writeUInt32LE(cdStart, 16);
    return Buffer.concat([local, nameBuf, stored, cd, nameBuf, eocd]).toString('base64');
}
let dir;
beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-jar-test-'));
});
afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
});
function writeJar(manifest, method) {
    const p = path.join(dir, 'out.jar');
    fs.writeFileSync(p, Buffer.from(makeJar(manifest, method), 'base64'));
    return p;
}
describe('jarManifestInfo', () => {
    it('reads the Main-Class from a stored manifest', () => {
        const p = writeJar('Manifest-Version: 1.0\r\nMain-Class: MKt\r\n\r\n', 0);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: 'MKt' });
    });
    it('reads the Main-Class from a deflated manifest', () => {
        const p = writeJar('Manifest-Version: 1.0\r\nMain-Class: com.example.MainKt\r\n\r\n', 8);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: 'com.example.MainKt' });
    });
    it('reports a manifest with no Main-Class as read but null', () => {
        const p = writeJar('Manifest-Version: 1.0\r\n\r\n', 0);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: null });
    });
    it('reports an unparseable file as unread, never as "no entry point"', () => {
        const p = path.join(dir, 'broken.jar');
        fs.writeFileSync(p, Buffer.from('this is not a zip file'));
        expect(jarManifestInfo(p)).toEqual({ read: false, mainClass: null });
    });
    it('reports a missing file as unread', () => {
        expect(jarManifestInfo(path.join(dir, 'does-not-exist.jar'))).toEqual({ read: false, mainClass: null });
    });
});
