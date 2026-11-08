"""Greek browser adapters retain notation, drawing selection and math accents."""
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
import unicodedata

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import build as font_build
import greekstyles
import mathweb
from greek_positioning import extend_greek_mark_anchors


class GreekWebContractTests(unittest.TestCase):
    def test_checked_in_contract_matches_authored_feature_families(self):
        spec = importlib.util.spec_from_file_location('greek_contract', ROOT / 'sources/build-greek-web-contract.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        self.assertEqual(json.loads((ROOT / 'assets/greek-math-styles.json').read_text()), generator.contract())
        adapters = {item['tag']: item for item in mathweb.adapter_specs() if item.get('greek')}
        self.assertEqual(set(adapters), set(greekstyles.FEATURES))
        for tag, feature in greekstyles.FEATURES.items():
            self.assertEqual(adapters[tag]['family'], feature['family'])


class GreekWebSubsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf/Lisnoti-Regular.ttf'
        if not path.exists():
            raise unittest.SkipTest('Fetch pinned source faces first')
        cls.font = TTFont(path)
        source = cls.font

        class Outlines(dict):
            def __missing__(self, name):
                self[name] = font_build.read(source, name)
                return self[name]

        greekstyles.apply_to_normal_anchors({weight: Outlines() for weight in (100, 400, 700, 900)}, source)
        extend_greek_mark_anchors(source)

    def test_frozen_cmap_and_math_accents_survive_every_adapter(self):
        original = self.font.getBestCmap()
        for tag, spec in greekstyles.FEATURES.items():
            with self.subTest(style=spec['style']):
                font = mathweb.feature_font(self.font, tag, retain_sources=True, retain_combining_marks=True,
                                           layout_features=[tag, 'ssty', 'mark', 'mkmk', 'kern'])
                cmap = font.getBestCmap()
                mapping = mathweb.single_mapping(self.font, tag)
                self.assertTrue(set(greekstyles.CODEPOINTS).issubset(cmap))
                self.assertNotIn(ord('A'), cmap, 'Latin math alphabets use the full Math fallback')
                self.assertFalse(any(0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0x10FFFD for cp in cmap))
                accent = font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs
                for character in 'αΓςϑ∂∇άΐἄΆΫ':
                    name = original[ord(character)]
                    self.assertEqual(cmap[ord(character)], mapping[name])
                    self.assertIn(mapping[name], accent)
                    self.assertIn(name, font.getGlyphOrder(), 'Retain the original for native GSUB/GPOS closure')
                features = {record.FeatureTag for record in font['GSUB'].table.FeatureList.FeatureRecord}
                self.assertIn(tag, features)
                self.assertFalse((set(greekstyles.FEATURES) - {tag}) & features)
                binary = BytesIO()
                font.save(binary)
                shaped = hb.Font(hb.Face(binary.getvalue()))

                def shape(text, features=None):
                    buffer = hb.Buffer()
                    buffer.add_str(text)
                    buffer.guess_segment_properties()
                    hb.shape(shaped, buffer, features or {})
                    return [(info.codepoint, position.x_advance, position.x_offset, position.y_offset)
                            for info, position in zip(buffer.glyph_infos, buffer.glyph_positions)]

                for character in 'άΐἄΆΫ':
                    self.assertEqual(shape(character), shape(unicodedata.normalize('NFD', character)),
                                     'Canonical typed Greek accents must reach the same adapter drawing')
                self.assertIn(0x0302, cmap, 'An unencoded Greek accent cluster needs one shaping font')
                accents = font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
                attachments = dict(zip(accents.TopAccentCoverage.glyphs,
                                       (record.Value for record in accents.TopAccentAttachment)))
                for character in 'αιλρ':
                    combined = shape(character + '\u0302')
                    self.assertEqual(len(combined), 2)
                    self.assertEqual(combined[1][1], 0)
                    self.assertNotEqual(combined, shape(character + '\u0302', {'mark': False}),
                                        'Greek adapters must retain actual GPOS mark positioning')
                    base, mark = (font.getGlyphName(record[0]) for record in combined)
                    mark_anchors = []
                    for lookup in font['GPOS'].table.LookupList.Lookup:
                        for subtable in lookup.SubTable:
                            subtable = getattr(subtable, 'ExtSubTable', subtable)
                            if subtable.__class__.__name__ == 'MarkBasePos' and base in subtable.BaseCoverage.glyphs and mark in subtable.MarkCoverage.glyphs:
                                record = subtable.MarkArray.MarkRecord[subtable.MarkCoverage.glyphs.index(mark)]
                                if subtable.BaseArray.BaseRecord[subtable.BaseCoverage.glyphs.index(base)].BaseAnchor[record.Class] is not None:
                                    mark_anchors.append(record.MarkAnchor.XCoordinate)
                    self.assertIn(attachments[base], [combined[0][1] + combined[1][2] + x for x in mark_anchors],
                                  f'{character}: typed above marks must align to the authored MATH attachment')


if __name__ == '__main__':
    unittest.main()
