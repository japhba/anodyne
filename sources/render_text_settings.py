#!/usr/bin/env python3
"""Render text-default and character-variant proofs from the final font outlines."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cairosvg
from fontTools.ttLib import TTFont
import uharfbuzz as hb

from proof import glyph_run

ROOT = Path(__file__).resolve().parents[1]


def render(fonts, output):
    sources = [Path(fonts)/'variable'/name for name in
               ('Anodyne[GRAD,wdth,wght].ttf', 'Anodyne-Italic[GRAD,wdth,wght].ttf')]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="760" viewBox="0 0 1400 760">',
             '<title>Anodyne baseline J and square t shoulder, with inherited character variants</title>',
             '<rect width="1400" height="760" fill="#fafbf7"/>',
             '<style>text{font-family:sans-serif;fill:#607573;font-size:19px}</style>']
    version = None
    for index, source in enumerate(sources):
        with TTFont(source) as font:
            version = font['name'].getDebugName(5).removeprefix('Version ')
            shaping = hb.Font(hb.Face(source.read_bytes()))
            shaping.set_variations({'wght': 400, 'wdth': 100, 'GRAD': 0})
            for alternate in (False, True):
                row = index*2+int(alternate)
                baseline = 205+row*157
                label = ('Italic' if index else 'Roman')+' · '+(
                    'inherited forms (cv03 + cv04)' if alternate else 'new defaults')
                parts.append(f'<text x="60" y="{baseline-80}">{label}</text>')
                parts.append(f'<path d="M60 {baseline}H1340" stroke="#d9e2df"/>')
                parts.append(glyph_run(font, shaping, 'Junction · Ĵ · t ţ ť ŧ ṫ ṭ · total',
                                       60, baseline, .064,
                                       {'cv03': 1, 'cv04': 1} if alternate else {}, color='#17373d'))
    parts.insert(4, f'<text x="60" y="55" style="font-size:28px;fill:#17373d">Anodyne {version} · text glyph choices</text>')
    parts.append('</svg>')
    svg = '\n'.join(parts)+'\n'
    (output/'text-settings.svg').write_text(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(output/'text-settings.png'))
    (output/'text-settings.json').write_text(json.dumps({
        'version': version,
        'font_sha256': {source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources},
        'defaults': 'Native baseline J and square upper-left t shoulder',
        'alternates': ['cv03', 'cv04'], 'all_glyphs_drawn_from_font': True,
    }, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, default=ROOT/'fonts')
    parser.add_argument('--out', type=Path, default=ROOT/'images')
    args = parser.parse_args()
    render(args.fonts, args.out)
