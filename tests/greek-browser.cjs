/* Actual Greek adapter drawings and variable axes in native MathML. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const contract = require('../assets/greek-math-styles.json');

const root = path.resolve(__dirname, '..');
const base = process.env.ANODYNE_BASE_URL || 'http://127.0.0.1:8772';
const output = path.join(root, 'build/browser-proofs');
let server;

async function main() {
  fs.mkdirSync(output, {recursive: true});
  if (!process.env.ANODYNE_BASE_URL) {
    server = spawn('python3', ['-m', 'http.server', '8772', '--bind', '127.0.0.1'], {cwd: root, stdio: 'ignore'});
    for (let i = 0; i < 40; i++) {
      try { if ((await fetch(base)).ok) break; } catch (_) {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 1000}});
    const errors = [];
    const failedAssets = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('response', response => {
      if (response.status() >= 400 && /\/(fonts|assets)\//.test(response.url())) failedAssets.push(response.url());
    });
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => window.AnodyneTeX && !document.getElementById('math-render-button').disabled);
    const pane = page.locator('#math-render');
    await page.locator('#math-preset').selectOption('greek');
    await page.waitForFunction(() => document.querySelector('#math-render [data-anodyne-greek-style="monospace"]'));
    assert.deepEqual(await pane.locator('[data-anodyne-greek-style]').evaluateAll(nodes =>
      Array.from(new Set(nodes.map(node => node.dataset.anodyneGreekStyle))).sort()),
      ['bold-fraktur', 'bold-script', 'double-struck', 'fraktur', 'monospace', 'script']);
    const setAxis = async (axis, value) => page.locator('#math-' + axis).evaluate((input, value) => {
      input.value = String(value); input.dispatchEvent(new Event('input'));
    }, value);
    const commands = {script: '\\mathcal', 'bold-script': '\\mathbfscr', fraktur: '\\mathfrak',
      'bold-fraktur': '\\mathbffrak', 'double-struck': '\\mathbb', monospace: '\\mathtt'};
    for (const [style, command] of Object.entries(commands)) {
      await page.locator('#math-tex').fill(`${command}{ΑΓΩαβςϑ∂∇άΐἄΆΫ}+\\hat{${command}{α}}`);
      await page.locator('#math-render-button').click();
      await page.waitForFunction(style => document.querySelector('#math-render [data-anodyne-greek-style="' + style + '"]'), style);
      assert.match((await pane.textContent()).replace(/\s+/gu, ''), /ΑΓΩαβςϑ∂∇άΐἄΆΫ/);
      for (const italic of [false, true]) {
        // mathvariant="normal" resets mi to upright in the browser's MathML
        // rules. Set the requested face on the actual token to exercise both
        // files, while keeping its Greek Unicode cmap interpretation frozen.
        await pane.locator('[data-anodyne-greek-style]').evaluateAll((nodes, italic) => {
          for (const node of nodes) node.style.fontStyle = italic ? 'italic' : 'normal';
        }, italic);
        assert.equal(await pane.locator('[data-anodyne-greek-style]').first().evaluate(node => getComputedStyle(node).fontStyle),
                     italic ? 'italic' : 'normal', 'The requested face style must reach the native MathML token');
        const loaded = await page.evaluate(async ({family, italic}) => {
          const faces = await document.fonts.load(`${italic ? 'italic ' : ''}32px "${family}"`);
          await document.fonts.ready;
          return faces.map(face => ({family: face.family, style: face.style, status: face.status}));
        }, {family: contract.styles[style].family, italic});
        assert.ok(loaded.some(face => face.family.includes(contract.styles[style].family)
          && face.style === (italic ? 'italic' : 'normal') && face.status === 'loaded'), `Missing ${style} adapter face`);
        await setAxis('wght', 400); await setAxis('wdth', 100); await setAxis('grad', 0);
        const label = style + (italic ? '-italic' : '');
        const regular = await pane.screenshot({path: path.join(output, 'greek-' + label + '.png')});
        await pane.locator('[data-anodyne-greek-style]').evaluateAll(nodes => {
          for (const node of nodes) node.style.fontFamily = '"Anodyne Math"';
        });
        assert.equal(regular.equals(await pane.screenshot()), false, `${label} must select different actual Greek drawings`);
        await pane.evaluate(node => window.AnodyneTeX.applyGreekMathStyles(node));
        for (const [axis, value] of [['wght', 800], ['wdth', 75], ['grad', 150]]) {
          await setAxis(axis, value);
          const changed = await pane.screenshot({path: path.join(output, 'greek-' + label + '-' + axis + '.png')});
          assert.equal(regular.equals(changed), false, `${label}: ${axis} must change actual Greek pixels`);
          await setAxis(axis, axis === 'wght' ? 400 : axis === 'wdth' ? 100 : 0);
        }
      }
    }
    await page.locator('#math-tex').fill(String.raw`\mathcal{αΓ}+\mathbfscr{αΓ}`);
    await page.locator('#math-render-button').click();
    await page.waitForFunction(() => document.querySelector('#math-render [data-anodyne-greek-style="bold-script"]'));
    await page.locator('[data-math-feature="ss01"]').click();
    await page.evaluate(async () => { await document.fonts.load('32px "Anodyne Greek Chancery"'); await document.fonts.ready; });
    const families = await pane.locator('[data-anodyne-greek-style]').evaluateAll(nodes => nodes.map(node => node.style.fontFamily));
    assert.ok(families.some(family => family.includes('Anodyne Greek Chancery')));
    assert.ok(families.some(family => family.includes('Anodyne Greek Bold Script')));
    await pane.screenshot({path: path.join(output, 'greek-chancery-selection.png')});
    assert.deepEqual(errors, []);
    assert.deepEqual(failedAssets, []);
    console.log('Greek native MathML passed: actual drawings in six alphabets × Roman/Italic, all variable axes, accented Greek, mathematical accents and chancery selection.');
  } finally { await browser.close(); }
}

main().catch(error => {console.error(error); process.exitCode = 1;}).finally(() => {if (server) server.kill();});
