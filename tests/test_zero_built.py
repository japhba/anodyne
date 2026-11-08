"""Release-level zero defaults and explicitly selected Noto figure designs."""
from pathlib import Path
import os
import sys
import unittest

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from test_zero import curve_signature, zero_shaper
from zero import TEXT_NAMES
FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


class ReleasedZeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        references = ('NotoSans[wdth,wght].ttf', 'NotoSans-Italic[wdth,wght].ttf',
                      'NotoSansMath-Regular.ttf')
        if not all((ROOT / 'src/noto' / name).is_file() for name in references):
            raise unittest.SkipTest('Pinned Noto comparisons are available after make fetch')

    def test_variable_text_zero_family_matches_native_at_weight_width_corners(self):
        for italic in (False, True):
            path = FONTS / 'variable' / ('Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf')
            if not path.exists():
                self.skipTest('Release fonts are built by make build')
            with TTFont(path) as actual:
                if actual['head'].fontRevision < .499:
                    self.skipTest('Native-zero restoration is released in version 0.500')
                with TTFont(ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if italic else 'NotoSans[wdth,wght].ttf')) as native:
                    names = [name for name in TEXT_NAMES if name in native.getGlyphOrder()]
                    for weight in (100, 400, 700, 900):
                        for width in (62.5, 100):
                            left = actual.getGlyphSet(location={'wght': weight, 'wdth': width, 'GRAD': 0})
                            right = native.getGlyphSet(location={'wght': weight, 'wdth': width})
                            for name in names:
                                with self.subTest(italic=italic, weight=weight, width=width, glyph=name):
                                    pens = [DecomposingRecordingPen(glyphs) for glyphs in (left, right)]
                                    for glyphs, pen in zip((left, right), pens):
                                        glyphs[name].draw(pen)
                                    self.assertEqual([item[0] for item in pens[0].value], [item[0] for item in pens[1].value])
                                    for (_, a), (_, b) in zip(pens[0].value, pens[1].value):
                                        self.assertEqual(len(a), len(b))
                                        for point_a, point_b in zip(a, b):
                                            if point_a is None or point_b is None:
                                                self.assertEqual(point_a, point_b)
                                            else:
                                                for axis in (0, 1):
                                                    self.assertAlmostEqual(point_a[axis], point_b[axis], delta=1.25)
                                    self.assertAlmostEqual(left[name].width, right[name].width, delta=1.25)

    def test_released_normal_faces_have_native_open_defaults_and_figure_choices(self):
        for italic in (False, True):
            path = FONTS / 'static' / ('Anodyne-Italic.ttf' if italic else 'Anodyne-Regular.ttf')
            if not path.exists():
                self.skipTest('Release fonts are built by make build')
            with TTFont(path) as font:
                if font['head'].fontRevision < .499:
                    self.skipTest('Native-zero restoration is released in version 0.500')
                with TTFont(ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if italic else 'NotoSans[wdth,wght].ttf')) as native:
                    actual, expected = zero_shaper(font), zero_shaper(native)
                    for features in ({}, {'onum': True}, {'pnum': True}, {'case': True}, {'zero': True},
                                     {'onum': True, 'zero': True}, {'onum': True, 'pnum': True, 'zero': True}):
                        selected, native_selected = actual(features)[0], expected(features)[0]
                        self.assertEqual(selected, native_selected, (italic, features))
                        self.assertEqual(curve_signature(font, selected), curve_signature(native, native_selected),
                                         (italic, features, selected))
                    self.assertEqual(font['glyf']['zero'].numberOfContours, 2)
                if not italic:
                    with TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf') as math:
                        for name in ('zero.ssty1', 'zero.ssty2'):
                            self.assertEqual(curve_signature(font, name), curve_signature(math, name), name)


if __name__ == '__main__':
    unittest.main()
