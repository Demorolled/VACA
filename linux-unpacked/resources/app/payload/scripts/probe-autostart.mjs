import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForSelector('.terminal-input', { timeout: 30000 });

  // Fresh state: ensure auto-preview on and no stored canvas state that would
  // make the smart preview show 'live' instead of the mockup.
  await page.evaluate(() => {
    localStorage.setItem('vaia-auto-preview', 'true');
    try { localStorage.removeItem('current-project-id'); } catch {}
  });

  await page.fill('.terminal-input', 'show me a preview of a pomodoro timer app');
  await page.press('.terminal-input', 'Enter');

  // Wait for the mockup window + Build This Now button
  await page.waitForSelector('.mpp-build-btn', { timeout: 30000 });
  console.log('mockup ready; clicking ⚡ Build This Now');
  await page.click('.mpp-build-btn');

  await page.waitForSelector('.bp-dialog', { timeout: 15000 });
  const goal = await page.inputValue('.bp-goal-input').catch(() => '(no input)');
  console.log('dialog open; goal =', JSON.stringify(goal));

  // Watch the dialog's status text for 40s
  for (let i = 0; i < 8; i++) {
    await page.waitForTimeout(5000);
    const status = await page.$eval('.bp-dialog', (d) => d.textContent?.slice(0, 200).replace(/\s+/g, ' ')).catch(() => '(gone)');
    console.log(`t+${(i + 1) * 5}s dialog:`, status);
    const errBox = await page.$eval('.bp-dialog', (d) => d.textContent || '').then((t) => /Build failed|Could not|error/i.test(t) && t.slice(0, 300).replace(/\s+/g, ' ')).catch(() => '');
    if (errBox && errBox !== 'false') console.log('  ⚠️ possible error text:', errBox);
  }
} catch (err) {
  console.error('PROBE ERROR:', err.message);
} finally {
  await browser.close();
}
