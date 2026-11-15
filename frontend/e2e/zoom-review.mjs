// Run against a running production test server on port 3100.
// CSS zoom tests magnification/reflow; it is not a physical browser UI zoom measurement.
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const dirname = path.dirname(fileURLToPath(import.meta.url));
(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1327, height: 900 }, reducedMotion: 'reduce' });
    const results = [];
    for (const route of ['/', '/method', '/sources', '/explore']) {
      await page.goto('http://127.0.0.1:3100' + route);
      await page.locator('main h1').first().waitFor();
      await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
      results.push({ route, horizontal_overflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        heading_visible: await page.locator('main h1').first().isVisible() });
    }
    fs.writeFileSync(path.resolve(dirname, '../../docs/browser-zoom.json'), JSON.stringify({
      scope: '200 percent CSS zoom in Chromium; physical browser UI zoom and assistive-technology testing remain manual checks', results,
    }, null, 2));
    if (results.some(r => r.horizontal_overflow || !r.heading_visible)) throw Error('Zoom layout failure');
    console.log('Four routes passed 200 percent CSS zoom layout check');
  } finally { await browser.close(); }
})();
