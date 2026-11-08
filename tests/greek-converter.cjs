/* Greek MathML semantics and style routing, independent of font build time. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const contract = require('../assets/greek-math-styles.json');

async function main() {
  const html = fs.readFileSync(path.resolve(__dirname, '../index.html'), 'utf8');
  const fullPreview = html.match(/fullfont: String\.raw`([\s\S]*?)`/)[1];
  const specimen = fs.readFileSync(path.resolve(__dirname, '../sources/specimen/math.tex'), 'utf8');
  const comparable = text => text.replace(/\s+/g, '');
  const expandMacros = text => text.replace(/\\Res\b/g, String.raw`\operatorname{Res}`)
    .replace(/\\diff\b/g, String.raw`\mathop{}\!\mathrm{d}`)
    .replace(/\\symbfsf\{([^{}]+)\}/g, (_match, body) => String.raw`\boldsymbol{\mathsf{${body}}}`)
    .replace(/\\symtt\b/g, String.raw`\mathtt`);
  for (const block of specimen.matchAll(/\\\[([\s\S]*?)\\\]/g)) {
    assert.ok(comparable(fullPreview).includes(comparable(expandMacros(block[1]))),
      'The editable preview must retain each complete specimen expression');
  }
  assert.ok(fullPreview.length <= 8000);
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto('about:blank');
    await page.addScriptTag({path: path.resolve(__dirname, '../assets/vendor/mathjax-tex-4.1.3.min.js')});
    const result = await page.evaluate(async fullPreview => {
      const api = window.AnodyneTeX;
      const parse = text => new DOMParser().parseFromString(text, 'application/xml').documentElement;
      const styles = ['script', 'bold-script', 'fraktur', 'bold-fraktur', 'double-struck', 'monospace'];
      const rows = styles.map(style => {
        const math = parse(`<math xmlns="http://www.w3.org/1998/Math/MathML"><mi mathvariant="${style}">ΑΩαβςϑ∂∇άΐἄΆΫ</mi></math>`);
        api.normalizeMathVariants(math);
        api.normalizeMathVariants(math); // normalizing the result is idempotent
        const token = math.querySelector('mi');
        return {style, text: token.textContent, family: token.style.fontFamily,
          variant: token.getAttribute('mathvariant'), selected: token.dataset.anodyneGreekStyle};
      });
      const mixed = parse('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi mathvariant="script">Aαa</mi><mi mathvariant="bold-script">Γ</mi><mi mathvariant="script">ά</mi></math>');
      api.normalizeMathVariants(mixed);
      api.applyGreekMathStyles(mixed, {chancery: true});
      const mixedRows = Array.from(mixed.querySelectorAll('mi'), token => ({text: token.textContent, family: token.style.fontFamily}));
      const standard = parse('<math xmlns="http://www.w3.org/1998/Math/MathML"><mstyle mathvariant="script"><mi>α</mi><mi mathvariant="normal">β</mi><mi mathvariant="bold">γ</mi></mstyle><mi mathvariant="italic">ά</mi><mi mathvariant="sans-serif-italic">α</mi></math>');
      api.normalizeMathVariants(standard);
      const standardRows = Array.from(standard.querySelectorAll('mi'), token => ({text: token.textContent, family: token.style.fontFamily}));
      const restyled = parse('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi mathvariant="fraktur">𝛼𝛝</mi></math>');
      api.normalizeMathVariants(restyled);
      const commands = {};
      for (const [name, source] of Object.entries({script: String.raw`\mathcal{\alpha\Gamma\partial\nabla άΐἄΆΫ}`, fraktur: String.raw`\mathfrak{\alpha\Gamma\partial\nabla άΐἄΆΫ}`,
          'bold-script': String.raw`\boldsymbol{\mathcal{\alpha\Gamma\partial\nabla άΐἄΆΫ}}`,
          'bold-fraktur': String.raw`\mathbffrak{\alpha\Gamma\partial\nabla άΐἄΆΫ}`,
          'double-struck': String.raw`\mathbb{\alpha\Gamma\partial\nabla άΐἄΆΫ}`, monospace: String.raw`\mathtt{\alpha\Gamma\partial\nabla άΐἄΆΫ}`})) {
        const math = parse(await api.tex2mmlPromise(source));
        api.normalizeMathVariants(math);
        commands[name] = Array.from(math.querySelectorAll('mi'), token => ({text: token.textContent, family: token.style.fontFamily}));
      }
      const nfd = parse(await api.tex2mmlPromise(String.raw`\mathcal{\alphá ΐ}`));
      api.normalizeMathVariants(nfd);
      const full = parse(await api.tex2mmlPromise(fullPreview));
      api.normalizeMathVariants(full);
      return {rows, mixedRows, standardRows, commands, restyled: restyled.querySelector('mi').textContent,
        full: {text: full.textContent, rows: full.querySelectorAll('mtable > mtr').length,
          fractions: full.querySelectorAll('mfrac').length, roots: full.querySelectorAll('msqrt, mroot').length,
          accents: full.querySelectorAll('mover').length, scripts: full.querySelectorAll('msup, msub, msubsup, munderover').length,
          greekStyles: Array.from(new Set(Array.from(full.querySelectorAll('[data-anodyne-greek-style]'), node => node.dataset.anodyneGreekStyle))).sort(),
          errors: full.querySelectorAll('merror, parsererror').length},
        nfd: Array.from(nfd.querySelectorAll('mi, mo'), token => ({text: token.textContent, family: token.style.fontFamily}))};
    }, fullPreview);
    for (const row of result.rows) {
      assert.equal(row.text, 'ΑΩαβςϑ∂∇άΐἄΆΫ', `${row.style} must preserve Greek notation`);
      assert.equal(row.variant, 'normal', 'Native MathML must not remap the frozen Greek cmap');
      assert.equal(row.selected, row.style);
      assert.ok(row.family.includes(contract.styles[row.style].family));
      assert.ok(row.family.includes('Anodyne Math'), 'Mixed Latin tokens need the full mathematical fallback');
    }
    assert.equal(result.mixedRows[0].text, '𝒜α𝒶');
    assert.match(result.mixedRows[0].family, /Anodyne Greek Chancery/);
    assert.match(result.mixedRows[0].family, /Anodyne Math Chancery/);
    assert.match(result.mixedRows[1].family, /Anodyne Greek Bold Script/);
    assert.doesNotMatch(result.mixedRows[1].family, /Chancery/);
    assert.equal(result.mixedRows[2].text, 'ά', 'Greek NFD accents must select the NFC composite drawing');
    assert.match(result.standardRows[0].family, /Anodyne Greek Script/);
    assert.deepEqual(result.standardRows.slice(1).map(row => row.text), ['β', '𝛄', '𝛼́', '𝛼']);
    assert.equal(result.standardRows[1].family, '', 'An explicit normal child must override inherited script');
    assert.equal(result.restyled, 'αϑ', 'An explicit Greek alphabet must override an existing mathematical Unicode style');
    for (const [style, tokens] of Object.entries(result.commands)) {
      assert.equal(tokens.map(token => token.text).join(''), 'αΓ∂∇άΐἄΆΫ');
      assert.ok(tokens.every(token => token.family.includes(contract.styles[style].family)), style);
    }
    assert.deepEqual(result.nfd.map(token => token.text), ['ά', 'ΐ']);
    assert.ok(result.nfd.every(token => token.family.includes(contract.styles.script.family)));
    assert.equal(result.full.errors, 0);
    assert.ok(result.full.rows >= 18);
    assert.ok(result.full.fractions >= 6);
    assert.ok(result.full.roots >= 2);
    assert.ok(result.full.accents >= 24);
    assert.ok(result.full.scripts >= 20);
    assert.match(result.full.text, /Res/);
    assert.deepEqual(result.full.greekStyles, ['bold-fraktur', 'bold-script', 'double-struck', 'fraktur', 'monospace', 'script']);
    assert.deepEqual(errors, []);
    console.log('Conversion passed: Greek semantic styles, accents, mixed Latin, chancery, actual TeX commands and the complete editable font specimen.');
  } finally { await browser.close(); }
}

main().catch(error => {console.error(error); process.exitCode = 1;});
