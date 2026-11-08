"""Regression checks on built fonts. Set ANODYNE_FONTS for a staged distribution."""
import os
from pathlib import Path
import re
import sys
import unittest
import unicodedata
from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from check import check_metadata, check_variation, check_math
from mathweb import adapter_specs

FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


class FontReleaseTests(unittest.TestCase):
    def test_metadata(self):
        version = re.search(r"^VERSION = ['\"]([^'\"]+)", (ROOT / 'sources/build.py').read_text(), re.M)[1]
        files = sorted(p for p in FONTS.glob('*/*') if p.suffix in ('.ttf', '.woff2'))
        self.assertEqual(len(files), 22 + 2 * len(adapter_specs()))
        for path in files:
            with self.subTest(font=path.name):
                self.assertEqual(check_metadata(path, version), [])

    def test_grade_and_layout(self):
        for path in (FONTS / 'variable').glob('*.ttf'):
            with self.subTest(font=path.name):
                errors, samples = check_variation(path)
                self.assertEqual(errors, [])
                self.assertEqual(len(samples), 12)

    def test_math_constructions_and_variations(self):
        for path in list(FONTS.glob('*/*.ttf')) + list((FONTS / 'mathwebfonts').glob('*.woff2')):
            with self.subTest(font=path.name):
                errors, _ = check_math(path)
                self.assertEqual(errors, [])

    def test_every_math_alphanumeric_responds_to_weight_width_and_grade(self):
        for path in (FONTS / 'variable').glob('*.ttf'):
            with self.subTest(font=path.name), TTFont(path) as font:
                characters = {codepoint: name for codepoint, name in font.getBestCmap().items()
                              if (0x1D400 <= codepoint <= 0x1D7FF
                                  or 0x1EE00 <= codepoint <= 0x1EEFF
                                  or (0x2100 <= codepoint <= 0x214F
                                      and (unicodedata.decomposition(chr(codepoint)).startswith('<font>')
                                           or unicodedata.name(chr(codepoint), '').startswith(
                                               ('SCRIPT ', 'BLACK-LETTER ', 'DOUBLE-STRUCK ')))))}
                self.assertGreaterEqual(len(characters), 1177)
                self.assertTrue({0x212C, 0x210C, 0x210D, 0x2118, 0x213D, 0x2146} <= characters.keys(),
                                'Historical mathematical letterlike symbols belong to the alphabet test')
                # This sans-serif family intentionally aliases some serif and
                # sans mathematical codepoints to the same drawing.
                names = set(characters.values())
                # Optical, dotless and chancery glyphs also belong to these
                # alphabets. The separate Greek suite covers the new ss08–14
                # families, so avoid rechecking its 2,121 targets here.
                edges = []
                for lookup in font['GSUB'].table.LookupList.Lookup:
                    for subtable in lookup.SubTable:
                        subtable = getattr(subtable, 'ExtSubTable', subtable)
                        for source, targets in getattr(subtable, 'mapping', {}).items():
                            edges.extend((source, target) for target in
                                         (targets if isinstance(targets, list) else [targets]))
                        for source, targets in getattr(subtable, 'alternates', {}).items():
                            edges.extend((source, target) for target in targets)
                while True:
                    descendants = {target for source, target in edges if source in names
                                   and '.anodyne.grk.' not in target}
                    if descendants <= names:
                        break
                    names.update(descendants)
                locations = [
                    {'wght': 400, 'wdth': 100, 'GRAD': 0},
                    {'wght': 900, 'wdth': 100, 'GRAD': 0},
                    {'wght': 400, 'wdth': 62.5, 'GRAD': 0},
                    {'wght': 400, 'wdth': 100, 'GRAD': 150},
                ]
                glyphsets = [font.getGlyphSet(location=l) for l in locations]
                unchanged = {'weight': [], 'width': [], 'grade': []}
                for name in names:
                    areas = []
                    for glyphset in glyphsets:
                        pen = AreaPen(glyphset)
                        glyphset[name].draw(pen)
                        areas.append(pen.value)
                    for i, axis in enumerate(unchanged, 1):
                        if abs(areas[0] - areas[i]) < 1:
                            unchanged[axis].append(name)
                self.assertEqual(unchanged, {'weight': [], 'width': [], 'grade': []})


if __name__ == '__main__':
    unittest.main()
