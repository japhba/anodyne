/* Browser checks for the comparison controls. Run npm ci, npx playwright install
 * chromium, then npm run test:browser. ANODYNE_BASE_URL can target an existing
 * server; otherwise this script serves the repository on localhost:8766.
 */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.ANODYNE_PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'build', 'browser-proofs');
const base = process.env.ANODYNE_BASE_URL || 'http://127.0.0.1:8766';
let server;

async function serve() {
  if (process.env.ANODYNE_BASE_URL) return;
  server = spawn('python3', ['-m', 'http.server', '8766', '--bind', '127.0.0.1'], { cwd: root, stdio: 'ignore' });
  for (let i = 0; i < 40; i++) {
    try { if ((await fetch(base)).ok) return; } catch (_) {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('The local preview server did not become ready');
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await serve();
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('#sample').fill('Junction · Ĵ · total · ţ ť ŧ');
    await page.evaluate(() => document.fonts.ready);
    const defaults = await page.locator('#sample').screenshot();
    for (const tag of ['cv03', 'cv04']) {
      const button = page.locator('#t-' + tag);
      assert.equal(await button.getAttribute('aria-pressed'), 'false');
      await button.click();
      assert.match(await page.locator('#sample').evaluate(node => node.style.fontFeatureSettings), new RegExp(tag));
      assert.equal(defaults.equals(await page.locator('#sample').screenshot()), false,
        tag + ' must change the rendered glyphs');
      await button.click();
    }
    await page.locator('#stage').screenshot({ path: path.join(output, 'text-defaults.png') });
    const selected = () => page.locator('#mf-comparisons .mf-compare').evaluateAll(nodes => nodes.map(n => n.dataset.font));
    const visibleChoices = () => page.locator('#mf-pick-list .mf-pick:visible').count();
    assert.deepEqual(await selected(), ['anodyne', 'lisnoti', 'notosansmath']);
    assert.equal(await page.locator('.mf-catalog .mf-font').count(), 35);
    assert.equal(await visibleChoices(), 35);
    assert.equal(await page.locator('#mf-catalog').getAttribute('open'), null);

    await page.locator('#mf-search').fill('xits');
    assert.equal(await visibleChoices(), 1);
    await page.locator('#mf-pick-list input[value="xits"]').check();
    assert.equal((await selected()).length, 4);
    await page.locator('#mf-search').fill('');
    assert.equal(await page.locator('#mf-pick-list input:not(:checked):disabled').count(), 31);
    await page.getByRole('button', { name: 'Remove Lisnoti from comparison', exact: true }).click();
    assert.equal(await page.locator('#mf-pick-list input:disabled').count(), 0);
    await page.locator('#mf-group').selectOption('serif');
    assert.equal(await visibleChoices(), 23);
    assert.match(await page.locator('#mf-results').textContent(), /outside these filters/);

    await page.locator('#mf-feature').selectOption('upright-integrals');
    assert.ok(await visibleChoices() > 0);
    const filterEvidence = await page.locator('#mf-catalog .mf-font:not([hidden])').evaluateAll(nodes => nodes.every(n => n.dataset.capabilities.split(' ').includes('upright-integrals') && n.dataset.group === 'serif'));
    assert.ok(filterEvidence);
    await page.locator('#mf-search').fill('no-such-font-name');
    assert.equal(await visibleChoices(), 0);
    assert.equal(await page.locator('#mf-empty').isVisible(), true);

    await page.getByRole('button', { name: 'Reset comparison', exact: true }).click();
    assert.deepEqual(await selected(), ['anodyne', 'lisnoti', 'notosansmath']);
    const sizes = await page.locator('#mf-comparisons .mf-shelf img').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().width / Number(n.getAttribute('width'))));
    assert.ok(sizes.every(size => Math.abs(size - 1) < .001));
    await page.locator('#mf-zoom').evaluate(input => { input.value = '150'; input.dispatchEvent(new Event('input', { bubbles: true })); });
    const enlarged = await page.locator('#mf-comparisons .mf-shelf img').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().width / Number(n.getAttribute('width'))));
    assert.ok(enlarged.every(size => Math.abs(size - 1.5) < .001));
    await page.getByRole('button', { name: 'Clear selection', exact: true }).click();
    assert.deepEqual(await selected(), []);
    assert.equal(await page.locator('#mf-no-selection').isVisible(), true);
    await page.getByRole('button', { name: 'Reset comparison', exact: true }).click();
    await page.locator('#mf-focus').screenshot({ path: path.join(output, 'comparison-desktop.png') });

    await page.locator('#mf-comparisons a[href="#mf-anodyne"]').click();
    assert.notEqual(await page.locator('#mf-catalog').getAttribute('open'), null);
    assert.equal(await page.locator('#mf-anodyne').isVisible(), true);
    const duplicates = await page.locator('[id]').evaluateAll(nodes => {
      const ids = nodes.map(n => n.id); return ids.filter((id, i) => ids.indexOf(id) !== i);
    });
    assert.deepEqual(duplicates, []);
    assert.deepEqual(errors, []);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Reset comparison', exact: true }).click();
    await page.locator('#mf-tools').scrollIntoViewIfNeeded();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert.equal(overflow, false, 'The comparison page must fit a mobile viewport');
    await page.locator('#mf-comparisons .mf-shelf').first().focus();
    await page.keyboard.press('ArrowRight');
    await page.locator('#mf-tools').screenshot({ path: path.join(output, 'comparison-mobile-controls.png') });
    await page.locator('#mf-focus').screenshot({ path: path.join(output, 'comparison-mobile.png') });

    const plain = await browser.newContext({ javaScriptEnabled: false });
    const fallback = await plain.newPage();
    await fallback.goto(base);
    assert.equal(await fallback.locator('.mf-catalog .mf-font:visible').count(), 35);
    assert.equal(await fallback.locator('#mf-tools').isVisible(), false);
    await plain.close();
    console.log('Comparison browser checks passed: desktop, mobile, filters, selection limit, shared scaling, no-JS fallback.');
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { if (server) server.kill(); });
