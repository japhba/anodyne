/* Native MathML/TeX editor checks. npm run test:math-browser */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.ANODYNE_BASE_URL || 'http://127.0.0.1:8771';
const output = path.join(root, 'build/browser-proofs');
let server;

async function main() {
  fs.mkdirSync(output, {recursive: true});
  if (!process.env.ANODYNE_BASE_URL) {
    server = spawn('python3', ['-m', 'http.server', '8771', '--bind', '127.0.0.1'], {cwd: root, stdio: 'ignore'});
    for (let i = 0; i < 40; i++) {
      try { if ((await fetch(base)).ok) break; } catch (_) {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 1050}});
    const errors = [];
    const external = [];
    const failedAssets = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('request', request => { if (!request.url().startsWith(base) && !request.url().startsWith('data:')) external.push(request.url()); });
    page.on('response', response => {
      if (response.status() >= 400 && /\/(fonts|assets)\//.test(response.url())) failedAssets.push(response.url());
    });
    // Optional pre-release fixture: exercise the UI before the complete axis
    // masters finish building, using independently compiled feature test faces.
    if (process.env.ANODYNE_DIAGNOSTIC_FONTS) {
      await page.route('**/fonts/mathwebfonts/anodyne-math.css', route => route.fulfill({
        contentType: 'text/css',
        body: '@font-face{font-family:"Anodyne Math";src:url("/build/math-feature-test.woff2")}@font-face{font-family:"Anodyne Math Upright";src:url("/build/math-upright-test.woff2")}@font-face{font-family:"Anodyne Math Chancery";src:url("/build/math-chancery-test.woff2")}',
      }));
    }
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.waitForFunction(() => window.AnodyneTeX && !document.getElementById('math-render-button').disabled);
    assert.equal(await page.evaluate(() => window.AnodyneTeX.version), '4.1.3');
    await page.evaluate(async () => {
      await document.fonts.load('27px "Anodyne Math"');
      await document.fonts.load('27px "Anodyne Math Upright"');
      await document.fonts.load('27px "Anodyne Math Chancery"');
      await document.fonts.ready;
    });
    for (const tag of ['ss02', 'ss03', 'ss04', 'ss05', 'cv01', 'cv02', 'ss01']) {
      const example = page.locator(`[data-math-example="${tag}"]`);
      const before = await example.screenshot();
      await page.locator(`[data-math-feature="${tag}"]`).click();
      await page.evaluate(() => document.fonts.ready);
      const after = await example.screenshot({path: path.join(output, `math-feature-${tag}.png`)});
      assert.equal(before.equals(after), false, `${tag} must change actual formula pixels`);
      if (tag === 'ss02') {
        assert.match(await example.locator('mo').first().evaluate(node => getComputedStyle(node).fontFamily), /Anodyne Math Upright/);
      }
      await page.locator(`[data-math-feature="${tag}"]`).click();
    }
    await page.locator('#math-tex').fill(String.raw`\frac{1}{1+x^2}+\sqrt[3]{y}=\hbar\omega`);
    await page.locator('#math-render-button').click();
    await page.waitForFunction(() => document.querySelector('#math-render mfrac') && document.querySelector('#math-render mroot'));
    assert.equal(await page.locator('#math-render math').count(), 1);
    assert.match(await page.locator('#math-render').textContent(), /ℏ/);
    assert.equal(await page.locator('#math-render mjx-container, #math-render svg').count(), 0, 'The browser must render native MathML');
    const lastGood = await page.locator('#math-render').innerHTML();
    await page.locator('#math-tex').fill(String.raw`\frac{1}{`);
    await page.locator('#math-render-button').click();
    await page.waitForFunction(() => document.getElementById('math-editor-status').dataset.error === 'true');
    assert.match(await page.locator('#math-editor-status').textContent(), /last valid formula/);
    assert.equal(await page.locator('#math-render').innerHTML(), lastGood);
    for (const unsafe of [String.raw`\href{javascript:alert(1)}{x}`, String.raw`\require{html}`, String.raw`\htmlClass{x}{y}`]) {
      await page.locator('#math-tex').fill(unsafe);
      await page.locator('#math-render-button').click();
      await page.waitForFunction(() => document.getElementById('math-editor-status').dataset.error === 'true');
      assert.equal(await page.locator('#math-render').innerHTML(), lastGood);
    }
    for (const preset of ['sets', 'quantum', 'delimiters', 'calculus']) {
      await page.locator('#math-preset').selectOption(preset);
      await page.waitForFunction(() => document.getElementById('math-editor-status').dataset.error === 'false');
      assert.equal(await page.locator('#math-render math').count(), 1);
      if (preset === 'sets') {
        const text = await page.locator('#math-render').textContent();
        assert.ok(text.includes('𝒜') && text.includes('ℬ') && text.includes('𝒞'), 'TeX mathcal must become real Unicode script letters');
        const before = await page.locator('#math-render').screenshot();
        await page.locator('[data-math-feature="ss01"]').click();
        await page.evaluate(() => document.fonts.ready);
        const after = await page.locator('#math-render').screenshot({path: path.join(output, 'math-tex-chancery.png')});
        assert.equal(before.equals(after), false, 'Chancery must change actual mathcal glyphs produced from TeX');
        await page.locator('[data-math-feature="ss01"]').click();
      }
    }
    await page.locator('#math-tex').fill(String.raw`\mathcal{A}+\mathcal{a}`);
    await page.locator('#math-render-button').click();
    await page.waitForFunction(() => document.getElementById('math-render').textContent.includes('𝒜') && document.getElementById('math-render').textContent.includes('𝒶'));
    await page.locator('[data-math-feature="ss01"]').click();
    const scriptFamilies = await page.locator('#math-render mi').evaluateAll(nodes => nodes.map(node => node.style.fontFamily));
    assert.match(scriptFamilies[0], /Anodyne Math Chancery/);
    assert.equal(scriptFamilies[1], '', 'The capital-only adapter must not replace lowercase script letters');
    await page.locator('[data-math-feature="ss01"]').click();
    await page.locator('#math-tex').fill(String.raw`\mathcal{ABC}+\mathbb{AHC}+\mathfrak{g}+\mathbf{A}+\mathit{h}+\mathrm{ABC}`);
    await page.locator('#math-render-button').click();
    await page.waitForFunction(() => document.getElementById('math-render').textContent.includes('𝔸'));
    const alphabets = await page.locator('#math-render').textContent();
    for (const literal of ['𝒜ℬ𝒞', '𝔸ℍℂ', '𝔤', '𝐀', 'ℎ', 'ABC']) assert.ok(alphabets.includes(literal), `Missing actual math alphabet ${literal}`);
    assert.equal(await page.locator('#math-render [mathvariant]:not([mathvariant="normal"])').count(), 0);
    await page.locator('#math-render').screenshot({path: path.join(output, 'math-tex-alphabets.png')});
    const variantEvidence = await page.evaluate(() => {
      const root = new DOMParser().parseFromString('<math xmlns="http://www.w3.org/1998/Math/MathML"><mstyle mathvariant="bold"><mi>αϑ</mi><mi mathvariant="normal">A</mi></mstyle><mi mathvariant="bold-script">A</mi><mi mathvariant="bold-fraktur">A</mi><mi mathvariant="bold-italic">A</mi><mi mathvariant="sans-serif">A</mi><mi mathvariant="bold-sans-serif">A</mi><mi mathvariant="sans-serif-italic">A</mi><mi mathvariant="sans-serif-bold-italic">A</mi><mn mathvariant="monospace">01</mn></math>', 'application/xml').documentElement;
      window.AnodyneTeX.normalizeMathVariants(root);
      return Array.from(root.querySelectorAll('mi, mn'), token => token.textContent);
    });
    assert.deepEqual(variantEvidence, ['𝛂𝛝', 'A', '𝓐', '𝕬', '𝑨', '𝖠', '𝗔', '𝘈', '𝘼', '𝟶𝟷']);
    await page.evaluate(() => {
      const styles = ['bold', 'italic', 'bold-italic', 'script', 'bold-script', 'fraktur', 'bold-fraktur', 'double-struck', 'sans-serif', 'bold-sans-serif', 'sans-serif-italic', 'sans-serif-bold-italic', 'monospace'];
      const rows = styles.map(style => `<mtr><mtd columnalign="left"><mtext>${style}</mtext></mtd><mtd><mi mathvariant="${style}">ABCabc</mi></mtd><mtd><mi mathvariant="${style}">αϑ</mi></mtd><mtd><mn mathvariant="${style}">012</mn></mtd></mtr>`).join('');
      const math = new DOMParser().parseFromString(`<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mtable rowspacing=".3em" columnspacing="1em">${rows}</mtable></math>`, 'application/xml').documentElement;
      window.AnodyneTeX.normalizeMathVariants(math);
      document.getElementById('math-render').replaceChildren(document.importNode(math, true));
    });
    await page.locator('#math-render').screenshot({path: path.join(output, 'math-alphabet-styles.png')});
    await page.locator('#math-preset').selectOption('sets');
    await page.locator('#math-preset').selectOption('calculus');
    await page.waitForFunction(() => document.querySelector('#math-render mo') && document.getElementById('math-render').textContent.includes('∫'));
    await page.locator('[data-math-feature="ss02"]').click();
    assert.match(await page.locator('#math-render mo').filter({hasText: '∫'}).evaluateAll(nodes => nodes.map(node => node.style.fontFamily).join(',')), /Anodyne Math Upright/);
    const setAxis = async (axis, value) => page.locator('#math-' + axis).evaluate((input, value) => {
      input.value = String(value); input.dispatchEvent(new Event('input'));
    }, value);
    // A style declaration can be accepted while the wrong face is rendered.
    // Compare actual formula pixels for every axis in the final variable fonts.
    if (!process.env.ANODYNE_DIAGNOSTIC_FONTS) {
      await setAxis('wght', 400); await setAxis('wdth', 100); await setAxis('grad', 0);
      const regular = await page.locator('#math-render').screenshot();
      for (const [axis, value] of [['wght', 800], ['wdth', 75], ['grad', 150]]) {
        await setAxis(axis, value);
        const changed = await page.locator('#math-render').screenshot({path: path.join(output, 'math-axis-' + axis + '.png')});
        assert.equal(regular.equals(changed), false, axis + ' must change actual rendered mathematics');
        await setAxis(axis, axis === 'wght' ? 400 : axis === 'wdth' ? 100 : 0);
      }
    }
    await page.locator('#math-wght').evaluate(input => {input.value = '800'; input.dispatchEvent(new Event('input'));});
    await page.locator('#math-wdth').evaluate(input => {input.value = '75'; input.dispatchEvent(new Event('input'));});
    assert.match(await page.locator('#math-live').evaluate(node => getComputedStyle(node).fontVariationSettings), /"wdth" 75/);
    await page.locator('#math-editor').scrollIntoViewIfNeeded();
    await page.locator('#math-live').screenshot({path: path.join(output, 'math-live-desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.locator('#math-editor').screenshot({path: path.join(output, 'math-editor-mobile.png')});
    assert.deepEqual(errors, []);
    assert.deepEqual(failedAssets, [], 'Every local script, stylesheet and font must load');
    assert.deepEqual(external, [], 'The editor must not load third-party runtime code or fonts');
    const context = await browser.newContext({javaScriptEnabled: false});
    const fallback = await context.newPage();
    await fallback.goto(base);
    assert.equal(await fallback.locator('#math-editor').isVisible(), false);
    assert.equal(await fallback.locator('#math-live math').count(), 9);
    await context.close();
    console.log('Native math checks passed: seven live feature pixel changes, TeX mathcal/chancery, presets, error recovery, unsafe-macro rejection, axes, mobile, offline assets and no-JS formulas.');
  } finally { await browser.close(); }
}

main().catch(error => {console.error(error); process.exitCode = 1;}).finally(() => {if (server) server.kill();});
