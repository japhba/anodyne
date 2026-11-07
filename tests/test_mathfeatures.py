"""Feature generation and shaping checks using the pinned Lisnoti source faces.

Run after fetching sources: python -m unittest discover -s tests -p test_mathfeatures.py
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import mathfeatures


class MathFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf'
        if not source.is_dir():
            raise unittest.SkipTest('Fetch the pinned Lisnoti source faces first')
        cls.fonts = {}
        cls.hb_fonts = {}
        cls.originals = {}
        cls.counts = {}
        for style in ('Regular', 'Bold', 'Italic', 'BoldItalic'):
            font = TTFont(source / f'Lisnoti-{style}.ttf')
            cls.originals[style] = mathfeatures._single_substitutions(font, {'ss01'})
            cls.counts[style] = mathfeatures.add_math_features(font)
            output = BytesIO()
            font.save(output)
            # Reloading verifies that the OpenType tables compile and decode.
            cls.fonts[style] = TTFont(BytesIO(output.getvalue()))
            cls.hb_fonts[style] = hb.Font(hb.Face(output.getvalue()))

    def shape(self, style, text, features=None):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb_fonts[style], buf, features or {})
        order = self.fonts[style].getGlyphOrder()
        return [order[g.codepoint] for g in buf.glyph_infos]

    def test_named_features_and_original_script_set(self):
        for style, font in self.fonts.items():
            with self.subTest(style=style):
                records = {r.FeatureTag: r for r in font['GSUB'].table.FeatureList.FeatureRecord}
                self.assertEqual(mathfeatures._single_substitutions(font, {'ss01'}), self.originals[style])
                for tag, spec in mathfeatures.FEATURES.items():
                    self.assertGreater(self.counts[style][tag], 0)
                    params = records[tag].Feature.FeatureParams
                    name_id = params.UINameID if tag.startswith('ss') else params.FeatUILabelNameID
                    self.assertEqual(font['name'].getDebugName(name_id), spec['name'])

    def test_each_feature_changes_its_sample(self):
        for style in self.fonts:
            for tag, spec in mathfeatures.FEATURES.items():
                with self.subTest(style=style, feature=tag):
                    sample = spec['sample'][0]
                    self.assertNotEqual(self.shape(style, sample), self.shape(style, sample, {tag: 1}))

    def test_integral_math_variant_closure(self):
        for style, font in self.fonts.items():
            with self.subTest(style=style):
                base = font.getBestCmap()[0x222B]
                alternate = self.shape(style, '∫', {'ss02': 1})[0]
                variants = font['MATH'].table.MathVariants
                constructions = dict(zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction))
                self.assertIn(alternate, constructions)
                original = constructions[base]
                upright = constructions[alternate]
                self.assertEqual(len(original.MathGlyphVariantRecord), len(upright.MathGlyphVariantRecord))
                for a, b in zip(original.MathGlyphVariantRecord, upright.MathGlyphVariantRecord):
                    self.assertEqual(b.VariantGlyph, a.VariantGlyph + '.anodyne.upright')
                    self.assertEqual(b.AdvanceMeasurement, a.AdvanceMeasurement)
                self.assertIsNotNone(upright.GlyphAssembly)
                self.assertEqual(upright.GlyphAssembly.ItalicsCorrection.Value, 0)
                for part in upright.GlyphAssembly.PartRecords:
                    self.assertIn(part.glyph, font['glyf'])

    def test_upright_stems_and_round_contour_rings(self):
        for style, font in self.fonts.items():
            with self.subTest(style=style):
                base = font.getBestCmap()[0x222B]
                alternate = self.shape(style, '∫', {'ss02': 1})[0]
                self.assertGreater(abs(mathfeatures._integral_slope(font, base)), .04)
                self.assertLess(abs(mathfeatures._integral_slope(font, alternate)), .005)
                source = font.getBestCmap()[0x222E]
                target = self.shape(style, '∮', {'ss02': 1})[0]
                original_points, ends, _ = mathfeatures._coordinates(font, source)
                upright_points, target_ends, _ = mathfeatures._coordinates(font, target)
                self.assertEqual(ends, target_ends)
                height = max(y for _, y in original_points)-min(y for _, y in original_points)
                start = 0
                rings_checked = 0
                for end in ends:
                    original = original_points[start:end+1]
                    if max(y for _, y in original)-min(y for _, y in original) < height*.65:
                        changed = upright_points[start:end+1]
                        self.assertEqual([y for _, y in original], [y for _, y in changed])
                        shifts = [b[0]-a[0] for a, b in zip(original, changed)]
                        self.assertLessEqual(max(shifts)-min(shifts), 1)
                        rings_checked += 1
                    start = end+1
                self.assertEqual(rings_checked, 2)

    def test_combined_styles_keep_both_choices(self):
        for style in self.fonts:
            for sample, feature in (('∉', 'ss04'), ('≰', 'ss03')):
                with self.subTest(style=style, sample=sample):
                    selected = self.shape(style, sample, {feature: 1})[0]
                    combined = self.shape(style, sample, {feature: 1, 'ss05': 1})[0]
                    self.assertNotEqual(selected, combined)
                    self.assertIn('compact' if feature == 'ss04' else 'slanted', combined)
                    self.assertTrue(combined.endswith('.vertical'))


if __name__ == '__main__':
    unittest.main()
