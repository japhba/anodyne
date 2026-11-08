/* Original Greek Unicode with named Anodyne styles absent from Unicode blocks. */
import greek from '../assets/greek-math-styles.json';

export function greekMathSupport(variants) {
  const isGreek = character => {
    const base = variants.bases[character] || character;
    const cp = base.codePointAt(0);
    return greek.extra_codepoints.includes(cp) || greek.greek_ranges.some(([lo, hi]) => cp >= lo && cp <= hi);
  };
  const greekNFC = text => text.replace(/\p{Script=Greek}\p{M}*/gu, run => run.normalize('NFC'));
  const declaredStyle = token => token.closest('[mathvariant]')?.getAttribute('mathvariant');
  const familyStack = (style, chancery = false) => {
    const selected = style === 'script' && chancery ? 'chancery' : style;
    const families = [greek.styles[selected].family];
    if (style === 'script' && chancery) families.push('Anodyne Math Chancery');
    families.push('Anodyne Math');
    return families.map(family => JSON.stringify(family)).join(', ');
  };

  function rememberStyle(token, variant) {
    if (greek.styles[variant] && Array.from(token.textContent).some(isGreek)) {
      token.dataset.anodyneGreekStyle = variant;
      // Greek NFC retains canonical notation and selects explicit accented
      // drawings instead of relying on unknown GPOS anchors in a styled face.
      token.textContent = greekNFC(token.textContent);
    } else if (variant && variant !== 'normal') {
      delete token.dataset.anodyneGreekStyle;
    }
  }

  function combineMarks(math) {
    // A TeX parser emits literal combining marks as separate operator tokens.
    // Restore their Unicode cluster before selecting the authored NFC glyph;
    // structured MathML accents such as mover remain separate layout objects.
    for (const token of math.querySelectorAll('mi')) {
      if (!/\p{Script=Greek}\p{M}*$/u.test(token.textContent)) continue;
      let mark = token.nextElementSibling;
      while (mark && /^(?:mi|mo|mtext)$/.test(mark.localName) && /^\p{M}+$/u.test(mark.textContent)
          && declaredStyle(mark) === declaredStyle(token)) {
        token.textContent += mark.textContent;
        const next = mark.nextElementSibling;
        mark.remove();
        mark = next;
      }
    }
  }

  function mapCharacter(character, variant, alphabet) {
    const base = variants.bases[character] || character;
    if (greek.styles[variant] && isGreek(base)) return base;
    const fallback = variant === 'sans-serif-italic' && isGreek(base) ? variants.styles.italic : null;
    const direct = alphabet[base] || (fallback && fallback[base]);
    if (direct) return direct;
    // Standard Unicode Greek bold/italic alphabets have no precomposed accented
    // forms. Compose those semantic alphabets with the real combining marks.
    if (isGreek(base)) {
      const decomposed = Array.from(base.normalize('NFD'));
      const first = alphabet[decomposed[0]] || (fallback && fallback[decomposed[0]]);
      if (decomposed.length > 1 && first) return first + decomposed.slice(1).join('');
    }
    return character;
  }

  function applyStyles(math, {chancery = false} = {}) {
    for (const token of math.querySelectorAll('[data-anodyne-greek-style]')) {
      const style = token.dataset.anodyneGreekStyle;
      if (!greek.styles[style]) continue;
      token.style.fontFamily = familyStack(style, chancery);
      token.setAttribute('mathvariant', 'normal');
    }
    return math;
  }

  return {rememberStyle, mapCharacter, combineMarks, applyStyles, styles: greek.styles};
}
