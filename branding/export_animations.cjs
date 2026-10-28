// Decode existing Pet animation frames in Chrome, then transcode to WebM.
// FFmpeg's WebP decoder does not consistently support animated WebP.
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium } = require(path.resolve(process.argv[2]));
const { pathToFileURL } = require('node:url');
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.join(__dirname, 'assets', 'logo_horizontal_dark.svg')).href);
    for (const name of ['peek', 'type']) {
      const base = path.join(__dirname, 'assets', `octop-mascot-${name}`);
      const data = (await fs.readFile(base + '.webp')).toString('base64');
      const frames = await page.evaluate(async data => {
        const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
        const decoder = new ImageDecoder({ data: bytes, type: 'image/webp' });
        await decoder.tracks.ready;
        const output = [];
        for (let i = 0; i < decoder.tracks.selectedTrack.frameCount; i++) {
          const { image } = await decoder.decode({ frameIndex: i });
          const canvas = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
          canvas.width = image.displayWidth; canvas.height = image.displayHeight;
          canvas.getContext('2d').drawImage(image, 0, 0);
          output.push({ png: canvas.toDataURL().split(',')[1], duration: image.duration / 1000000 });
          image.close();
        }
        decoder.close();
        return output;
      }, data);
      const folder = path.join(__dirname, '..', 'temp', `animation-${name}`);
      await fs.mkdir(folder, { recursive: true });
      const lines = [];
      for (let i = 0; i < frames.length; i++) {
        await fs.writeFile(path.join(folder, `${i}.png`), Buffer.from(frames[i].png, 'base64'));
        lines.push(`file '${i}.png'`, `duration ${frames[i].duration}`);
      }
      lines.push(`file '${frames.length - 1}.png'`);
      await fs.writeFile(path.join(folder, 'frames.txt'), lines.join('\n'));
      const result = spawnSync(process.env.FFMPEG_PATH || 'ffmpeg', [
        '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0',
        '-i', path.join(folder, 'frames.txt'), '-an', '-c:v', 'libvpx-vp9',
        '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0', base + '.webm',
      ], { encoding: 'utf8', windowsHide: true });
      if (result.status !== 0) throw new Error(result.stderr || 'FFmpeg failed');
      console.log(`${name}: ${frames.length} frames converted`);
    }
  } finally { await browser.close(); }
})();
