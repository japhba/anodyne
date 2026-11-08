"""Integration checks for features in a staged or installed distribution.

ANODYNE_FONTS=build/release/fonts python -m unittest discover -s tests
"""
import itertools
import os
from pathlib import Path
import sys
import unittest

from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from mathfeatures import FEATURES, _integral_slope
from check import harfbuzz_font

FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))
SAMPLES = {'ss02': '∫', 'ss03': '≤', 'ss04': '∈', 'ss05': '≠', 'cv01': '∅', 'cv02': 'ℏ'}


def shape(font, text, features=None):
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, features or {})
    return [g.codepoint for g in buf.glyph_infos]


class BuiltMathFeaturesTests(unittest.TestCase):
    def test_browser_operator_fonts_keep_unicode_variations_and_math_sizes(self):
        paths = sorted((FONTS / 'mathwebfonts').glob('*-upright*.woff2'))
        self.assertEqual(len(paths), 2)
        for path in paths:
            with self.subTest(font=path.name), TTFont(path) as tt:
                self.assertIn('fvar', tt)
                self.assertIn('MATH', tt)
                self.assertNotIn(0xE000, tt.getBestCmap(), 'Original Unicode notation must be preserved')
                font = harfbuzz_font(path)
                for weight, width, grade in ((100, 62.5, -100), (400, 100, 0), (900, 100, 150)):
                    font.set_variations({'wght': weight, 'wdth': width, 'GRAD': grade})
                    glyph = font.get_nominal_glyph(0x222B)
                    self.assertIsNotNone(glyph)
                    # Web subsets can discard PostScript glyph names. Check
                    # the actual outline instead of trusting a name suffix.
                    self.assertLess(abs(_integral_slope(tt, tt.getGlyphOrder()[glyph])), .02)
                    variants = font.get_math_glyph_variants(glyph, 'ttb')
                    self.assertGreater(len(variants), 1)
                    self.assertTrue(all(v.glyph > 0 and v.advance > 0 for v in variants))
                    correction = font.get_math_glyph_italics_correction(glyph)
                    self.assertGreaterEqual(correction, 0)
                    if (weight, width, grade) == (400, 100, 0):
                        self.assertEqual(correction, 0)

    def test_features_shape_and_keep_winding_at_variable_corners(self):
        paths = sorted((FONTS / 'variable').glob('*.ttf'))
        self.assertEqual(len(paths), 2)
        for path in paths:
            with TTFont(path) as tt:
                font = hb.Font(hb.Face(path.read_bytes()))
                order = tt.getGlyphOrder()
                for weight, width in itertools.product((100, 900), (62.5, 100)):
                    location = {'wght': weight, 'wdth': width, 'GRAD': 0}
                    font.set_variations(location)
                    glyphs = tt.getGlyphSet(location=location)
                    baseline = {}
                    for tag, text in SAMPLES.items():
                        selected = shape(font, text, {tag: 1})
                        self.assertNotEqual(selected, shape(font, text), (path, location, tag))
                        self.assertNotIn(0, selected, (path, location, tag))
                        pen = AreaPen(glyphs)
                        glyphs[order[selected[0]]].draw(pen)
                        baseline[tag] = pen.value
                    for grade in (-100, 150):
                        current = dict(location, GRAD=grade)
                        font.set_variations(current)
                        glyphs = tt.getGlyphSet(location=current)
                        for tag, text in SAMPLES.items():
                            with self.subTest(font=path.name, **current, feature=tag):
                                selected = shape(font, text, {tag: 1})
                                self.assertNotEqual(selected, shape(font, text))
                                self.assertNotIn(0, selected)
                                pen = AreaPen(glyphs)
                                glyphs[order[selected[0]]].draw(pen)
                                self.assertGreater(baseline[tag]*pen.value, 0,
                                                   'The selected alternate collapsed or reversed area')

    def test_feature_names_survive_math_web_subsets(self):
        paths = sorted((FONTS / 'webfonts').glob('*-math.woff2'))
        self.assertEqual(len(paths), 2)
        paths += [FONTS / 'mathwebfonts' / name for name in ('anodyne-math.woff2', 'anodyne-math-italic.woff2')]
        for path in paths:
            with TTFont(path) as tt:
                records = {r.FeatureTag: r for r in tt['GSUB'].table.FeatureList.FeatureRecord}
                for tag, spec in FEATURES.items():
                    with self.subTest(font=path.name, feature=tag):
                        self.assertIn(tag, records)
                        params = records[tag].Feature.FeatureParams
                        name_id = params.UINameID if tag.startswith('ss') else params.FeatUILabelNameID
                        self.assertEqual(tt['name'].getDebugName(name_id), spec['name'])

    def test_all_math_faces_keep_upright_integral_constructions(self):
        paths = sorted((FONTS / 'static').glob('*.ttf'))
        paths += sorted((FONTS / 'variable').glob('*.ttf'))
        paths += [FONTS / 'mathwebfonts' / name for name in ('anodyne-math.woff2', 'anodyne-math-italic.woff2')]
        self.assertGreaterEqual(len(paths), 6)
        for path in paths:
            with self.subTest(font=path.name), TTFont(path) as tt:
                records = [r for r in tt['GSUB'].table.FeatureList.FeatureRecord if r.FeatureTag == 'ss02']
                self.assertEqual(len(records), 1)
                mapping = {}
                for index in records[0].Feature.LookupListIndex:
                    lookup = tt['GSUB'].table.LookupList.Lookup[index]
                    for sub in lookup.SubTable:
                        if lookup.LookupType == 7:
                            sub = sub.ExtSubTable
                        mapping.update(getattr(sub, 'mapping', {}))
                variants = tt['MATH'].table.MathVariants
                constructions = dict(zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction))
                order = set(tt.getGlyphOrder())
                for cp in (0x222B, 0x222C, 0x222E):
                    source = tt.getBestCmap()[cp]
                    target = mapping[source]
                    self.assertIn(target, constructions)
                    originals = constructions[source].MathGlyphVariantRecord
                    alternates = constructions[target].MathGlyphVariantRecord
                    self.assertEqual(len(originals), len(alternates))
                    for old, record in zip(originals, alternates):
                        self.assertIn(record.VariantGlyph, order)
                        self.assertEqual(record.VariantGlyph, mapping[old.VariantGlyph])
                    if constructions[target].GlyphAssembly:
                        for part in constructions[target].GlyphAssembly.PartRecords:
                            self.assertIn(part.glyph, order)


if __name__ == '__main__':
    unittest.main()
