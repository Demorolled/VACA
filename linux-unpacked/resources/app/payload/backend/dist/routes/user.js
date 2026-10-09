import { Router } from 'express';
import { mkdir, writeFile, readFile, readdir } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
const router = Router();
const USERS_DIR = path.resolve(import.meta.dirname, '..', '..', 'users');
async function ensureUserDir(name) {
    const dir = path.join(USERS_DIR, name);
    await mkdir(dir, { recursive: true });
    await mkdir(path.join(dir, 'projects'), { recursive: true });
    await mkdir(path.join(dir, 'roadmaps'), { recursive: true });
    await mkdir(path.join(dir, 'code-exports'), { recursive: true });
    return dir;
}
router.post('/init', async (req, res) => {
    try {
        const { name } = req.body;
        if (!name || typeof name !== 'string') {
            return res.status(400).json({ error: 'Name is required' });
        }
        const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
        const dir = await ensureUserDir(safeName);
        res.json({ success: true, userDir: dir });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
router.get('/files/:name/:type/:filename', async (req, res) => {
    try {
        const { name, type, filename } = req.params;
        const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
        const filePath = path.join(USERS_DIR, safeName, type, filename);
        if (!existsSync(filePath))
            return res.status(404).json({ error: 'File not found' });
        const data = await readFile(filePath, 'utf-8');
        res.json({ success: true, data });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
router.post('/files/:name/:type/:filename', async (req, res) => {
    try {
        const { name, type, filename } = req.params;
        const { data } = req.body;
        const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
        const dir = path.join(USERS_DIR, safeName, type);
        await mkdir(dir, { recursive: true });
        await writeFile(path.join(dir, filename), data, 'utf-8');
        res.json({ success: true });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
router.get('/files/:name/:type', async (req, res) => {
    try {
        const { name, type } = req.params;
        const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
        const dir = path.join(USERS_DIR, safeName, type);
        if (!existsSync(dir))
            return res.json({ files: [] });
        const entries = await readdir(dir);
        res.json({ files: entries });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/user/profile
 * Save or sync user profile data (preferences, style tags, history).
 * Body should contain the full UserProfile object from the frontend.
 */
router.post('/profile', async (req, res) => {
    try {
        const { username, preferences, styleTags, history, emotionalHistory } = req.body;
        if (!username) {
            return res.status(400).json({ error: 'username is required' });
        }
        const safeName = username.replace(/[^a-zA-Z0-9_-]/g, '_');
        const dir = path.join(USERS_DIR, safeName);
        await mkdir(dir, { recursive: true });
        // Load existing profile or create new one
        const profilePath = path.join(dir, 'profile.json');
        let profile = {};
        try {
            const existing = await readFile(profilePath, 'utf-8');
            profile = JSON.parse(existing);
        }
        catch { /* will create new */ }
        // Merge incoming data into existing profile (incoming takes precedence)
        if (preferences)
            profile.preferences = preferences;
        if (styleTags)
            profile.styleTags = styleTags;
        if (history) {
            profile.history = profile.history || { projects: [], feedbackEntries: [] };
            if (history.projects)
                profile.history.projects = history.projects;
            if (history.feedbackEntries)
                profile.history.feedbackEntries = history.feedbackEntries;
        }
        if (emotionalHistory)
            profile.emotionalHistory = emotionalHistory;
        profile.updatedAt = new Date().toISOString();
        if (!profile.createdAt)
            profile.createdAt = new Date().toISOString();
        if (!profile.username)
            profile.username = safeName;
        await writeFile(profilePath, JSON.stringify(profile, null, 2), 'utf-8');
        res.json({ success: true, username: safeName });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/user/profile/:name
 * Load a user's profile data.
 */
router.get('/profile/:name', async (req, res) => {
    try {
        const { name } = req.params;
        const safeName = name.replace(/[^a-zA-Z0-9_-]/g, '_');
        const profilePath = path.join(USERS_DIR, safeName, 'profile.json');
        if (!existsSync(profilePath)) {
            return res.json({ success: true, profile: null });
        }
        const data = await readFile(profilePath, 'utf-8');
        const profile = JSON.parse(data);
        res.json({ success: true, profile });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export { router as userRoutes };
