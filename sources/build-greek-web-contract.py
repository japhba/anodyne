#!/usr/bin/env python3
"""Keep Greek feature adapters and the browser's style names in one contract."""
import json
from pathlib import Path

from greekstyles import FEATURES

ROOT = Path(__file__).resolve().parents[1]


def contract():
    return {
        'source': 'Anodyne Greek OpenType features; characters retain their Greek Unicode semantics',
        'greek_ranges': [[0x0370, 0x03FF], [0x1F00, 0x1FFF]],
        'extra_codepoints': [0x2202, 0x2207],
        'styles': {spec['style']: {'tag': tag, 'family': spec['family'],
                                  'suffix': 'greek-' + spec['style']}
                   for tag, spec in FEATURES.items()},
    }


if __name__ == '__main__':
    path = ROOT / 'assets/greek-math-styles.json'
    path.write_text(json.dumps(contract(), ensure_ascii=False, indent=2) + '\n')
    print(path)
