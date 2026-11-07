#!/usr/bin/env python3
"""Generate MathML mathvariant -> Unicode math alphabet mappings, including holes.

MathML Core renders literal mathematical alphanumerics consistently. Unicode's
direct <font> decompositions preserve Greek symbol variants that recursive NFKD
would collapse (for example theta symbol versus ordinary theta).
"""
import json
from pathlib import Path

import unicodedata2 as ud

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = [
    ('SANS-SERIF BOLD ITALIC ', 'sans-serif-bold-italic'),
    ('SANS-SERIF BOLD ', 'bold-sans-serif'),
    ('SANS-SERIF ITALIC ', 'sans-serif-italic'),
    ('SANS-SERIF ', 'sans-serif'),
    ('BOLD SCRIPT ', 'bold-script'),
    ('BOLD FRAKTUR ', 'bold-fraktur'),
    ('BOLD ITALIC ', 'bold-italic'),
    ('BOLD ', 'bold'), ('ITALIC ', 'italic'), ('SCRIPT ', 'script'),
    ('FRAKTUR ', 'fraktur'), ('BLACK-LETTER ', 'fraktur'),
    ('DOUBLE-STRUCK ', 'double-struck'), ('MONOSPACE ', 'monospace'),
]


def mapping():
    styles = {style: {} for _, style in PREFIXES}
    bases = {}
    # Letterlike Symbols supplies historical holes such as script B/E/F and
    # italic h. Later Mathematical Alphanumeric characters win where both exist.
    for codepoint in list(range(0x2100, 0x2150)) + list(range(0x1D400, 0x1D800)):
        character = chr(codepoint)
        name = ud.name(character, '').removeprefix('MATHEMATICAL ')
        style = next((style for prefix, style in PREFIXES if name.startswith(prefix)), None)
        if ud.name(character, '') == 'PLANCK CONSTANT':
            style = 'italic'
        if style is None:
            continue
        decomposition = ud.decomposition(character).split()
        if len(decomposition) != 2 or decomposition[0] != '<font>':
            continue
        base = chr(int(decomposition[1], 16))
        # Double-struck italic differential letters (ⅅⅆⅇⅈⅉ) have their own
        # semantics; they are not the ordinary double-struck alphabet.
        if name.startswith('DOUBLE-STRUCK ITALIC '):
            continue
        styles[style][base] = character
        bases[character] = base
    return {
        'unicode_version': ud.unidata_version,
        'source': 'Unicode character names and direct font decompositions, via unicodedata2',
        'copyright': 'Copyright © 1991-2026 Unicode, Inc.',
        'license': 'Unicode License V3; see assets/vendor/Unicode-LICENSE.txt',
        'styles': styles, 'bases': bases,
    }


def main():
    result = mapping()
    path = ROOT / 'assets/math-variants.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print(f'{path}: {sum(len(style) for style in result["styles"].values())} mappings, Unicode {ud.unidata_version}')


if __name__ == '__main__':
    main()
