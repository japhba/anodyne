#!/usr/bin/env python3
"""Render the text/axis specimen from real variable-font outlines, without CSS fonts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cairosvg
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]


class Drawing:
    def __init__(self, source, dark=False):
        self.tt = TTFont(source)
        self.source = Path(source)
        self.version = self.tt['name'].getDebugName(5).removeprefix('Version ')
        self.font = hb.Font(hb.Face(Path(source).read_bytes()))
        self.names = self.tt.getGlyphOrder()
        self.upem = self.tt['head'].unitsPerEm
        self.ink, self.muted, self.line, self.paper = (
            ('#f1f5f3', '#abbfbd', '#354c4c', '#10282c') if dark else
            ('#17373d', '#607573', '#cdd9d5', '#fafbf7'))
        self.parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1110" viewBox="0 0 1400 1110">',
                      '<title>Anodyne text, Greek, figures and variable axes</title>',
                      f'<rect width="1400" height="1110" fill="{self.paper}"/>']

    def text(self, value, x, y, size, weight=400, width=100, grade=0, features=None, muted=False, limit=1280):
        location = {'wght': weight, 'wdth': width, 'GRAD': grade}
        self.font.set_variations(location)
        buffer = hb.Buffer()
        buffer.add_str(value)
        buffer.guess_segment_properties()
        hb.shape(self.font, buffer, features or {})
        if any(info.codepoint == 0 for info in buffer.glyph_infos):
            raise ValueError('Missing specimen glyph: '+value)
        advance = sum(p.x_advance for p in buffer.glyph_positions)
        scale = min(size/self.upem, limit/(advance or 1))
        glyphs = self.tt.getGlyphSet(location=location)
        cursor = 0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            pen = SVGPathPen(glyphs)
            glyphs[self.names[info.codepoint]].draw(pen)
            self.parts.append(f'<path d="{pen.getCommands()}" fill="{self.muted if muted else self.ink}" '
                              f'transform="translate({x+(cursor+position.x_offset)*scale:g},{y-position.y_offset*scale:g}) scale({scale:g},{-scale:g})"/>')
            cursor += position.x_advance

    def rule(self, y):
        self.parts.append(f'<path d="M60 {y}H1340" stroke="{self.line}"/>')

    def finish(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.parts.append('</svg>')
        destination.with_suffix('.svg').write_text('\n'.join(self.parts)+'\n')
        cairosvg.svg2png(bytestring=('\n'.join(self.parts)).encode(), write_to=str(destination))
        destination.with_suffix('.json').write_text(json.dumps({
            'version': self.version,
            'font_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'all_glyphs_drawn_from_font': True,
            'missing_glyphs': False,
        }, indent=2)+'\n')
        self.tt.close()


def render(source, destination, dark=False):
    page = Drawing(source, dark)
    page.text('Anodyne', 60, 145, 120, weight=550)
    page.text(f'{page.version}  /  TEXT + MATHEMATICS', 62, 195, 22, muted=True)
    page.rule(225)
    page.text('Clear forms, a coherent family.', 60, 300, 57, weight=450)
    page.text('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 60, 370, 47)
    page.text('abcdefghijklmnopqrstuvwxyz', 60, 430, 49)
    page.text('0123456789   O0o   I l 1   ( ) [ ] { }   + − × ÷ =', 60, 490, 43)
    page.text('ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ', 60, 555, 46)
    page.text('αβγδεζηθικλμνξοπρστυφχψω   ς ϵ ϑ ϕ ϖ ϱ ϰ', 60, 617, 43)
    page.rule(650)
    page.text('WIDTH', 60, 690, 18, muted=True)
    for x, label, width in ((60, 'Normal · 100', 100), (505, 'Condensed · 75', 75), (950, 'ExtraCondensed · 62.5', 62.5)):
        page.text(label, x, 728, 20, muted=True, limit=390)
        page.text('Hamburg 0123', x, 790, 48, width=width, limit=390)
    page.rule(820)
    page.text('GRADE  /  SAME ADVANCES', 60, 860, 18, muted=True)
    for x, label, grade in ((60, '−100', -100), (505, '0', 0), (950, '+150', 150)):
        page.text(label, x, 896, 20, muted=True)
        page.text('Mathematics 0123', x, 952, 40, grade=grade, limit=390)
    page.rule(982)
    page.text('Small capitals 0123456789', 60, 1035, 31, features={'smcp':1, 'onum':1}, limit=650)
    page.text('Proportional 0123456789', 760, 1035, 29, features={'pnum':1}, limit=580)
    page.text('Noto figure defaults · weight 100–900 · width 62.5–100 · grade −100–150', 60, 1080, 18, muted=True)
    page.finish(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, default=ROOT/'fonts')
    parser.add_argument('--out', type=Path, default=ROOT/'images')
    args = parser.parse_args()
    source = args.fonts/'variable/Anodyne[GRAD,wdth,wght].ttf'
    render(source, args.out/'specimen.png')
    render(source, args.out/'specimen-dark.png', dark=True)
    print(args.out/'specimen.png')


if __name__ == '__main__':
    main()
