"""Exercise actual text defaults and character variants throughout the axes."""
import os
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont
import uharfbuzz as hb
from fontTools.varLib.varStore import VarStoreInstancer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources'))
from textforms import native_top_anchor
FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


def shape(font, text, features=None):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features or {})
    return [g.codepoint for g in buffer.glyph_infos]


class BuiltTextFormsTests(unittest.TestCase):
    def test_text_files_expose_real_defaults_and_both_variants(self):
        files = list(FONTS.glob('*/*.ttf')) + list((FONTS/'webfonts').glob('*latin*.woff2'))
        files += [FONTS/'mathwebfonts'/name for name in ('anodyne-math.woff2', 'anodyne-math-italic.woff2')]
        for path in files:
            with self.subTest(font=path.name), TTFont(path) as tt:
                if ord('J') not in tt.getBestCmap():
                    continue
                # HarfBuzz reads sfnt, including files distributed as WOFF2.
                tt.flavor = None
                import io
                stream = io.BytesIO()
                tt.save(stream)
                font = hb.Font(hb.Face(stream.getvalue()))
                self.assertNotEqual(shape(font, 'J'), shape(font, 'J', {'c2sc': 1}))
                self.assertEqual(shape(font, 'J', {'c2sc': 1}),
                                 shape(font, 'J', {'c2sc': 1, 'cv03': 1}))
                locations = ({'wght': w, 'wdth': d, 'GRAD': g}
                             for w in (100, 400, 900) for d in (62.5, 100) for g in (-100, 0, 150)) if 'fvar' in tt else [{}]
                for location in locations:
                    font.set_variations(location)
                    regular = shape(font, 'Jt')
                    old_j = shape(font, 'Jt', {'cv03': 1})
                    old_t = shape(font, 'Jt', {'cv04': 1})
                    self.assertNotEqual(regular[0], old_j[0])
                    self.assertEqual(regular[1], old_j[1])
                    self.assertEqual(regular[0], old_t[0])
                    self.assertNotEqual(regular[1], old_t[1])
                    self.assertGreater(font.get_glyph_extents(regular[0]).y_bearing+
                                       font.get_glyph_extents(regular[0]).height, -40)
                    self.assertLess(font.get_glyph_extents(old_j[0]).y_bearing+
                                    font.get_glyph_extents(old_j[0]).height, -100)
                    if 'MATH' in tt:
                        name = tt.getGlyphOrder()[regular[0]]
                        anchor = native_top_anchor(tt, name)
                        expected = anchor.XCoordinate
                        device = getattr(anchor, 'XDeviceTable', None)
                        if device is not None and device.DeltaFormat == 0x8000:
                            normalized = tt.getGlyphSet(location=location).location
                            store = VarStoreInstancer(tt['GDEF'].table.VarStore, tt['fvar'].axes, normalized)
                            expected += store[(device.StartSize << 16)+device.EndSize]
                        self.assertAlmostEqual(font.get_math_glyph_top_accent_attachment(regular[0]),
                                               expected, delta=1.1)


if __name__ == '__main__':
    unittest.main()
