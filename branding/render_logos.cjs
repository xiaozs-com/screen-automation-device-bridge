// Render the composed client SVG wordmarks to Octop's existing PNG filenames.
// Usage: node branding/render_logos.cjs /path/to/playwright-core
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(path.resolve(process.argv[2]));

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 420, height: 112 }, deviceScaleFactor: 1 });
    for (const variant of (process.argv[3] ? [process.argv[3]] : ['dark', 'white'])) {
      const file = path.join(__dirname, 'assets', `logo_horizontal_${variant}`);
      await page.goto(pathToFileURL(file + '.svg').href);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: file + '.png', omitBackground: true });
    }
  } finally {
    await browser.close();
  }
})();
