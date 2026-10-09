/**
 * Safe path helpers for the dropped-site preview feature.
 *
 * Dropped folders arrive as relative paths from the browser FileSystem API
 * (e.g. "tools/index.html"). Before writing them to a temp preview dir we
 * normalize + validate every path so no `..` / absolute / drive segments can
 * escape the preview root.
 */
import path from 'path';
/**
 * Normalize a browser-supplied relative path into safe forward-slash form.
 * Returns null when the path is empty or contains any escaping segment.
 */
export function sanitizeSiteRelPath(raw) {
    if (typeof raw !== 'string')
        return null;
    // Normalize backslashes (Windows-style paths from the FileSystem API),
    // strip any leading slashes and drive letters.
    let p = raw.replace(/\\/g, '/').replace(/^[a-zA-Z]:/, '');
    p = p.replace(/^\/+/, '').replace(/\/+$/, '');
    if (!p || p === '.')
        return null;
    const segments = p.split('/');
    for (const seg of segments) {
        if (seg === '' || seg === '.' || seg === '..')
            return null;
        // Reject any segment that could hide traversal after decode.
        if (seg.includes('\\') || seg.includes('\0'))
            return null;
    }
    return segments.join('/');
}
/**
 * Map a file extension to a MIME type for static serving.
 */
export function mimeForPath(filePath) {
    const ext = filePath.split('.').pop()?.toLowerCase() || '';
    const MIME = {
        html: 'text/html; charset=utf-8',
        htm: 'text/html; charset=utf-8',
        js: 'text/javascript; charset=utf-8',
        mjs: 'text/javascript; charset=utf-8',
        css: 'text/css; charset=utf-8',
        json: 'application/json; charset=utf-8',
        svg: 'image/svg+xml',
        png: 'image/png',
        jpg: 'image/jpeg',
        jpeg: 'image/jpeg',
        gif: 'image/gif',
        webp: 'image/webp',
        ico: 'image/x-icon',
        woff: 'font/woff',
        woff2: 'font/woff2',
        ttf: 'font/ttf',
        otf: 'font/otf',
        txt: 'text/plain; charset=utf-8',
        md: 'text/markdown; charset=utf-8',
        xml: 'application/xml; charset=utf-8',
        map: 'application/json; charset=utf-8',
        wasm: 'application/wasm',
    };
    return MIME[ext] || 'application/octet-stream';
}
/**
 * Given a preview root dir and a requested URL path, resolve to a safe
 * absolute file path, or null when the request escapes the root.
 */
export function resolveSitePreviewPath(rootDir, urlPath) {
    const rel = sanitizeSiteRelPath(urlPath);
    if (!rel)
        return null;
    const resolved = path.resolve(rootDir, rel);
    const root = path.resolve(rootDir);
    if (resolved !== root && !resolved.startsWith(root + path.sep))
        return null;
    return resolved;
}
