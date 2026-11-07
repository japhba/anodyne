/* MathJax parses TeX; the browser renders its MathML with Anodyne's own font. */
import {mathjax} from '@mathjax/src/js/mathjax.js';
import {TeX} from '@mathjax/src/js/input/tex.js';
import {browserAdaptor} from '@mathjax/src/js/adaptors/browserAdaptor.js';
import {RegisterHTMLHandler} from '@mathjax/src/js/handlers/html.js';
import {STATE} from '@mathjax/src/js/core/MathItem.js';
import {SerializedMmlVisitor} from '@mathjax/src/js/core/MmlTree/SerializedMmlVisitor.js';
import '@mathjax/src/js/input/tex/base/BaseConfiguration.js';
import '@mathjax/src/js/input/tex/ams/AmsConfiguration.js';
import variants from '../assets/math-variants.json';

RegisterHTMLHandler(browserAdaptor());
const input = new TeX({
  packages: ['base', 'ams'],
  maxBuffer: 12000,
  maxMacros: 1000,
  formatError(_jax, error) { throw error; },
});
const mathDocument = mathjax.document('', {InputJax: input});
const visitor = new SerializedMmlVisitor();

async function tex2mmlPromise(source) {
  if (typeof source !== 'string' || source.length > 8000) {
    throw new Error('Keep formulas under 8,000 characters.');
  }
  if (!source.trim()) throw new Error('Enter a formula to render.');
  // No output jax, extension loader, HTML, URL or user-defined macro packages
  // are loaded. Conversion stops before rendering or fetching any font assets.
  const node = mathDocument.convert(source, {display: true, end: STATE.CONVERT});
  return visitor.visitTree(node);
}

function normalizeMathVariants(math) {
  for (const token of math.querySelectorAll('mi, mn, mo, mtext')) {
    const declared = token.closest('[mathvariant]');
    const variant = declared && declared.getAttribute('mathvariant');
    const alphabet = variants.styles[variant];
    if (!alphabet) continue;
    token.textContent = Array.from(token.textContent, character => {
      const base = variants.bases[character] || character;
      return alphabet[base] || character;
    }).join('');
    // Preserve the selected literal Unicode alphabet instead of asking the
    // browser to interpret unsupported legacy MathML mathvariant values again.
    token.setAttribute('mathvariant', 'normal');
  }
  return math;
}

window.AnodyneTeX = Object.freeze({version: '4.1.3', tex2mmlPromise, normalizeMathVariants});
window.dispatchEvent(new CustomEvent('anodyne-tex-ready'));
