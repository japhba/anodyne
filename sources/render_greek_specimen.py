#!/usr/bin/env python3
"""Draw every Greek math alphabet from the built font as PNG, SVG and PDF.

Examples:
  python sources/render_greek_specimen.py --fonts fonts --out images
  python sources/render_greek_specimen.py --weight 100 --out build/greek-thin

The outlines are shaped with HarfBuzz. No locally installed fonts, browser font
fallbacks, private Unicode characters or screenshot rasterization are involved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import cairosvg
from cairosvg.surface import PDFSurface, cairo
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

import greekstyles

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1920, 4630
INK, MUTED, LINE, PAPER = '#17373d', '#607573', '#cdd9d5', '#fafbf7'
ROWS = (
    ('CAPITALS', greekstyles.UPPER),
    ('LOWERCASE', greekstyles.LOWER),
    ('VARIANTS', greekstyles.VARIANTS),
    ('MODERN ACCENTS', greekstyles.MODERN_ACCENTS),
    ('POLYTONIC SAMPLE', 'ἄἆἌἍᾄᾌᾳῇΐῧ'),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Page:
    def __init__(self, source, location):
        self.source = Path(source)
        self.tt = TTFont(source)
        self.version = self.tt['name'].getDebugName(5).removeprefix('Version ')
        self.font = hb.Font(hb.Face(self.source.read_bytes()))
        self.names = self.tt.getGlyphOrder()
        self.upem = self.tt['head'].unitsPerEm
        self.location = location
        self.drawn = set()
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
                      '<title>Anodyne Greek mathematical alphabet specimen</title>',
                      '<desc>Seven named Greek style interpretations, with complete uppercase and lowercase alphabets, mathematical variants, modern accents and polytonic examples. All letters are outlines from the compiled font.</desc>',
                      f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>']

    def text(self, value, x, y, size, feature=None, muted=False, location=None):
        location = location or self.location
        self.font.set_variations(location)
        buffer = hb.Buffer()
        buffer.add_str(value)
        buffer.guess_segment_properties()
        hb.shape(self.font, buffer, {feature: 1} if feature else {})
        if any(info.codepoint == 0 for info in buffer.glyph_infos):
            raise ValueError('Missing specimen character in '+repr(value))
        glyphs = self.tt.getGlyphSet(location=location if 'fvar' in self.tt else None)
        scale = size/self.upem
        cursor = 0
        for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = self.names[info.codepoint]
            if feature and '.anodyne.grk.' not in name:
                raise ValueError(f'{feature} did not style {value!r}: {name}')
            self.drawn.add(name)
            pen = SVGPathPen(glyphs)
            glyphs[name].draw(pen)
            if pen.getCommands():
                self.parts.append(f'<path d="{pen.getCommands()}" fill="{MUTED if muted else INK}" '
                                  f'transform="translate({x+(cursor+pos.x_offset)*scale:g},{y-pos.y_offset*scale:g}) scale({scale:g},{-scale:g})"/>')
            cursor += pos.x_advance

    def label(self, value, x, y, size=20):
        self.text(value, x, y, size, muted=True,
                  location={'wght': 400, 'wdth': 100, 'GRAD': 0})

    def rule(self, y):
        self.parts.append(f'<path d="M96 {y}H1824" stroke="{LINE}" stroke-width="2"/>')


def render(source, output, location, pixels=3200):
    source, output = Path(source), Path(output)
    page = Page(source, location)
    tags = {f.FeatureTag for f in page.tt['GSUB'].table.FeatureList.FeatureRecord}
    missing = set(greekstyles.FEATURES)-tags
    if missing:
        raise ValueError('This font predates the Greek alphabets: missing '+', '.join(sorted(missing)))
    page.text('Anodyne', 96, 152, 108, location={'wght': 550, 'wdth': 100, 'GRAD': 0})
    page.label('GREEK MATHEMATICAL ALPHABETS', 98, 214, 30)
    page.label(f'{page.version}   /   WEIGHT {location["wght"]:g}   WIDTH {location["wdth"]:g}   GRADE {location["GRAD"]:g}', 98, 258, 22)
    page.label('Original Greek characters. Seven Anodyne interpretations. Every style follows all three variable axes.', 98, 300, 22)
    page.rule(330)
    y = 375
    for tag, spec in greekstyles.FEATURES.items():
        page.text(spec['name'], 96, y, 39, location={'wght': 500, 'wdth': 100, 'GRAD': 0})
        page.label(tag, 1695, y, 24)
        for label, characters in ROWS:
            y += 43
            page.label(label, 98, y, 16)
            y += 60
            for index, character in enumerate(characters):
                page.text(character, 100+index*71.5, y, 58, feature=tag)
        y += 57
        page.rule(y-21)
    y += 20
    page.label(f'{len(greekstyles.CODEPOINTS)} source Greek characters per family, including all {len(greekstyles.ACCENTED_CHARACTERS)} native precomposed accent forms.', 98, y, 22)
    page.label('Breathings and tonos use the original accent drawings; iota subscript remains below the styled body.', 98, y+38, 22)
    page.label('Script, fraktur, double-struck and monospace Greek have no dedicated Unicode alphabet blocks.', 98, y+76, 22)
    page.label('Named OpenType stylistic sets preserve the underlying Greek text. Drawings and font: SIL Open Font License 1.1.', 98, y+114, 21)
    page.parts.append('</svg>')
    svg = ('\n'.join(page.parts)+'\n').encode()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.greek-specimen-', dir=output) as temporary:
        stage = Path(temporary)
        (stage/'greek-math-styles.svg').write_bytes(svg)
        cairosvg.svg2png(bytestring=svg, write_to=str(stage/'greek-math-styles.png'), output_width=pixels)
        epoch = int(os.environ.get('SOURCE_DATE_EPOCH',
                    json.loads((ROOT/'sources/source-lock.json').read_text())['source_date_epoch']))
        timestamp = datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        class StablePDF(PDFSurface):
            def finish(self):
                self.cairo.set_metadata(cairo.PDF_METADATA_CREATE_DATE, timestamp)
                super().finish()
        StablePDF.convert(bytestring=svg, write_to=str(stage/'greek-math-styles.pdf'))
        manifest = {'version': page.version, 'font_sha256': sha(source),
                    'generator_sha256': sha(__file__), 'greek_sources_sha256': sha(greekstyles.__file__),
                    'location': location, 'pixels': pixels, 'source_date_epoch': epoch,
                    'source_characters_per_family': len(greekstyles.CODEPOINTS),
                    'native_accented_characters_per_family': len(greekstyles.ACCENTED_CHARACTERS),
                    'features': greekstyles.FEATURES, 'missing_glyphs': False,
                    'all_glyphs_drawn_from_font': True,
                    'outputs': {p.name: sha(p) for p in sorted(stage.iterdir())}}
        (stage/'greek-math-styles.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
        for path in stage.iterdir():
            path.replace(output/path.name)
    page.tt.close()
    print(output/'greek-math-styles.png')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fonts', type=Path, default=ROOT/'fonts')
    parser.add_argument('--font', type=Path, help='Override the normal variable font path')
    parser.add_argument('--out', type=Path, default=ROOT/'images')
    parser.add_argument('--weight', type=float, default=400)
    parser.add_argument('--width', type=float, default=100)
    parser.add_argument('--grade', type=float, default=0)
    parser.add_argument('--pixels', type=int, default=3200, help='PNG width; vector outputs retain all outlines')
    args = parser.parse_args()
    if not (100 <= args.weight <= 900 and 62.5 <= args.width <= 100 and -100 <= args.grade <= 150):
        parser.error('Axes must lie inside wght 100–900, wdth 62.5–100, GRAD −100–150')
    if not 960 <= args.pixels <= 6400:
        parser.error('--pixels must be between 960 and 6400')
    render(args.font or args.fonts/'variable/Anodyne[GRAD,wdth,wght].ttf', args.out,
           {'wght': args.weight, 'wdth': args.width, 'GRAD': args.grade}, args.pixels)


if __name__ == '__main__':
    main()
