#!/usr/bin/env python3
"""Release checks for outlines, shaping, variable maths and the packaged fonts.

Run after the build: python sources/check.py --fonts fonts --sanitize.
The JSON result records sampled coordinates; it is not a claim of exhaustive
visual validation. Formula proofs live in sources/proof.py.
"""
from __future__ import annotations

import argparse
import itertools
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
MATH_TEXT = '𝑥𝑦𝛼𝛽∑∏∫∮√≤≥≠∅ℏ()[]{}⟨⟩'
SHAPING_TEXT = 'AV To x\u0301 0123456789 ' + MATH_TEXT


def harfbuzz_font(path):
    """HarfBuzz's blob API expects SFNT data, not a compressed WOFF2 wrapper."""
    path = Path(path)
    if path.suffix == '.woff2':
        with TTFont(path, recalcTimestamp=False) as font:
            font.flavor = None
            stream = BytesIO()
            font.save(stream)
            return hb.Font(hb.Face(stream.getvalue()))
    return hb.Font(hb.Face(path.read_bytes()))


def shape(font, text, features=None):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features or {})
    return [(i.codepoint, p.x_advance, p.x_offset, p.y_offset)
            for i, p in zip(buffer.glyph_infos, buffer.glyph_positions)]


def check_metadata(path, version):
    errors = []
    with TTFont(path) as font:
        if font['name'].getDebugName(5) != f'Version {version}':
            errors.append('name-table version does not match build VERSION')
        if abs(font['head'].fontRevision - float(version)) > 1 / 65536:
            errors.append('head.fontRevision does not match build VERSION')
        for table in ('cmap', 'glyf', 'GSUB', 'GPOS', 'name'):
            if table not in font:
                errors.append(f'missing {table}')
        if path.suffix == '.ttf' and 'MATH' not in font:
            errors.append('desktop font has no MATH table')
        if path.parent.name == 'webfonts' and 'MATH' in font:
            errors.append('text web subset unexpectedly contains MATH')
        if path.parent.name == 'mathwebfonts' and 'MATH' not in font:
            errors.append('browser maths font has no MATH table')
        # Compile every table, not just the ones needed to read metadata.
        for tag in font.keys():
            if tag != 'GlyphOrder':
                font.getTableData(tag)
    return errors


def check_variation(path):
    """Check all glyph advances and representative actual curves at axis corners."""
    errors, samples = [], []
    tt = TTFont(path)
    face = hb.Face(path.read_bytes())
    font = hb.Font(face)
    cmap = tt.getBestCmap()
    names = sorted({cmap[ord(c)] for c in ''.join(chr(i) for i in range(33, 127)) + MATH_TEXT
                    if ord(c) in cmap})
    for weight, width in itertools.product((100, 400, 900), (62.5, 100)):
        location = {'wght': weight, 'wdth': width, 'GRAD': 0}
        font.set_variations(location)
        baseline_advances = [font.get_glyph_h_advance(i) for i in range(face.glyph_count)]
        baseline_shape = shape(font, SHAPING_TEXT)
        baseline_glyphs = tt.getGlyphSet(location=location)
        areas = {}
        for name in names:
            pen = AreaPen(baseline_glyphs)
            baseline_glyphs[name].draw(pen)
            areas[name] = pen.value
        for grade in (-100, 150):
            location = dict(location, GRAD=grade)
            font.set_variations(location)
            moved = [i for i, advance in enumerate(baseline_advances)
                     if advance != font.get_glyph_h_advance(i)]
            if moved:
                errors.append(f'{location}: grade changes {len(moved)} glyph advances')
            current = shape(font, SHAPING_TEXT)
            if [(g[0], g[1]) for g in current] != [(g[0], g[1]) for g in baseline_shape]:
                errors.append(f'{location}: grade changes shaped text advances')
            glyphs = tt.getGlyphSet(location=location)
            flipped = []
            for name in names:
                pen = AreaPen(glyphs)
                glyphs[name].draw(pen)
                if abs(areas[name]) > 1 and areas[name] * pen.value <= 0:
                    flipped.append(name)
            if flipped:
                errors.append(f'{location}: outline area flips: {", ".join(flipped[:12])}')
            samples.append(dict(location, glyph_advance_changes=len(moved), area_flips=flipped))
    font.set_variations({'wght': 400, 'wdth': 100, 'GRAD': 0})
    normal = shape(font, 'AV To x\u0301')
    font.set_variations({'wght': 400, 'wdth': 62.5, 'GRAD': 0})
    narrow = shape(font, 'AV To x\u0301')
    if sum(p[1] for p in normal) <= sum(p[1] for p in narrow):
        errors.append('width axis does not condense shaped text')
    if not getattr(tt['GDEF'].table, 'VarStore', None):
        errors.append('variable layout has no GDEF variation store')
    tt.close()
    return errors, samples


def check_math(path):
    """Check constructions and measure MATH values through the consumer API."""
    errors, readings = [], []
    with TTFont(path) as tt:
        math = tt['MATH'].table
        names = set(tt.getGlyphOrder())
        variants = math.MathVariants
        for axis in ('Vert', 'Horiz'):
            cov = getattr(variants, axis + 'GlyphCoverage')
            constructions = getattr(variants, axis + 'GlyphConstruction') or []
            if len(cov.glyphs if cov else []) != len(constructions):
                errors.append(f'{axis} coverage/construction count mismatch')
            for construction in constructions:
                advances = [v.AdvanceMeasurement for v in construction.MathGlyphVariantRecord]
                if advances != sorted(advances):
                    errors.append(f'{axis} variant measurements are not sorted')
                for variant in construction.MathGlyphVariantRecord:
                    if variant.VariantGlyph not in names:
                        errors.append(f'missing variant {variant.VariantGlyph}')
                if construction.GlyphAssembly:
                    for part in construction.GlyphAssembly.PartRecords:
                        if part.glyph not in names:
                            errors.append(f'missing assembly glyph {part.glyph}')
                        if min(part.StartConnectorLength, part.EndConnectorLength) < 0 or max(part.StartConnectorLength, part.EndConnectorLength) > part.FullAdvance:
                            errors.append(f'invalid connectors in {part.glyph}')
        if 'fvar' in tt:
            font = harfbuzz_font(path)
            x = font.get_nominal_glyph(ord('𝑥'))
            for weight, width, grade in ((100, 100, 0), (400, 100, 0), (900, 100, 0),
                                         (400, 62.5, 0), (400, 100, 150)):
                font.set_variations({'wght': weight, 'wdth': width, 'GRAD': grade})
                readings.append({'wght': weight, 'wdth': width, 'GRAD': grade,
                    'x_accent': font.get_math_glyph_top_accent_attachment(x) if x is not None else None,
                    'fraction_rule': font.get_math_constant(hb.OTMathConstant.FRACTION_RULE_THICKNESS),
                    'x_italics_correction': font.get_math_glyph_italics_correction(x) if x is not None else None})
            if x is not None and readings[1]['x_accent'] == readings[3]['x_accent']:
                errors.append('math accent attachment does not follow width axis')
            if readings[0]['fraction_rule'] >= readings[2]['fraction_rule']:
                errors.append('math fraction rule does not follow weight axis')
    return errors, readings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, default=ROOT / 'fonts')
    parser.add_argument('--json', type=Path, default=ROOT / 'build/qa.json')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    version = re.search(r"^VERSION = ['\"]([^'\"]+)", (ROOT / 'sources/build.py').read_text(), re.M)[1]
    files = sorted(p for p in args.fonts.glob('*/*') if p.suffix in ('.ttf', '.woff2'))
    if not files:
        parser.error(f'no packaged fonts found in {args.fonts}')
    result = {'version': version, 'files': [], 'errors': []}
    sanitizer = shutil.which('ots-sanitize')
    if args.sanitize and not sanitizer:
        parser.error('--sanitize requires ots-sanitize (opentype-sanitizer package)')
    for path in files:
        errors = check_metadata(path, version)
        row = {'file': str(path), 'errors': errors}
        if path.parent.name == 'variable':
            errs, row['variation_samples'] = check_variation(path)
            errors.extend(errs)
        if path.suffix == '.ttf' or path.parent.name == 'mathwebfonts':
            errs, row['math_readings'] = check_math(path)
            errors.extend(errs)
        if args.sanitize:
            with tempfile.TemporaryDirectory() as scratch:
                sanitized = subprocess.run([sanitizer, str(path), str(Path(scratch) / 'font.ttf')],
                                           capture_output=True, text=True)
                row['sanitizer_log'] = sanitized.stdout + sanitized.stderr
                if sanitized.returncode:
                    errors.append('OpenType sanitizer rejected font')
        result['files'].append(row)
        result['errors'].extend(f'{path.name}: {e}' for e in errors)
        print(('FAIL' if errors else 'PASS'), path.name, flush=True)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + '\n')
    print(f'{len(files)} fonts checked; {len(result["errors"])} failures. Report: {args.json}')
    for error in result['errors']:
        print(' ', error)
    raise SystemExit(bool(result['errors']))


if __name__ == '__main__':
    main()
