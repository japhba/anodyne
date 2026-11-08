"""Native Noto zeros, figure selection, optical math and grade regressions."""
import copy
import io
import itertools
from pathlib import Path
import sys
import unittest
import uharfbuzz as hb

from fontTools import subset
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import build
from zero import NativeZeroSources, TEXT_NAMES, FIGURE_FEATURES


def zero_shaper(font):
    stream = io.BytesIO()
    font.save(stream)
    face = hb.Face(stream.getvalue())
    shaped = hb.Font(face)
    def shape(features):
        buffer = hb.Buffer()
        buffer.add_str('0')
        buffer.guess_segment_properties()
        hb.shape(shaped, buffer, features)
        return [font.getGlyphName(info.codepoint) for info in buffer.glyph_infos]
    return shape


class CanonicalCurves(BasePen):
    """Split implied quadratic points and ignore closed-contour start choices."""
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.contours, self.current, self.start = [], [], None
    def _moveTo(self, point):
        self.start, self.current = point, []
    def _lineTo(self, point):
        previous = self._getCurrentPoint()
        if point != previous:
            self.current.append(('L', previous, point))
    def _qCurveToOne(self, control, point):
        self.current.append(('Q', self._getCurrentPoint(), control, point))
    def _curveToOne(self, a, b, point):
        self.current.append(('C', self._getCurrentPoint(), a, b, point))
    def _closePath(self):
        if self._getCurrentPoint() != self.start:
            self.current.append(('L', self._getCurrentPoint(), self.start))
        rotations = [tuple(self.current[i:] + self.current[:i]) for i in range(len(self.current))]
        self.contours.append(min(rotations))
    def signature(self):
        return tuple(sorted(self.contours))


def curve_signature(font, name):
    glyphs = font.getGlyphSet()
    pen = CanonicalCurves(glyphs)
    glyphs[name].draw(pen)
    return pen.signature()


class NativeZeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / 'src/noto/NotoSansMath-Regular.ttf').exists():
            raise unittest.SkipTest('Pinned upstream inputs are available after make fetch')
        cls.math = TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf')
        cls.roman = TTFont(ROOT / 'src/noto/NotoSans[wdth,wght].ttf')
        cls.models, cls.fonts = {}, {}
        for italic in (False, True):
            source = TTFont(ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if italic else 'NotoSans[wdth,wght].ttf'))
            options = subset.Options()
            options.layout_features = list(FIGURE_FEATURES) + ['sups', 'subs', 'numr', 'dnom', 'frac']
            sub = subset.Subsetter(options)
            sub.populate(glyphs=[name for name in TEXT_NAMES if name in source.getGlyphOrder()])
            sub.subset(source)
            fonts = {width: {weight: instantiateVariableFont(copy.deepcopy(source), {'wght': weight, 'wdth': width})
                             for weight in build.WEIGHTS} for width in (100, 62.5)}
            cls.fonts[italic] = fonts
            cls.models[italic] = NativeZeroSources(fonts[100], fonts[62.5], cls.math, italic, cls.roman)

    def test_all_text_zero_forms_use_exact_native_weight_width_drawings(self):
        for italic, model in self.models.items():
            for width, fonts in self.fonts[italic].items():
                for weight, font in fonts.items():
                    for name in model.text_names:
                        with self.subTest(italic=italic, width=width, weight=weight, glyph=name):
                            actual, expected = model.outline(name, weight, width), build.read(font, name)
                            self.assertEqual(actual.contours, expected.contours)
                            self.assertEqual(actual.components, expected.components)
                            self.assertEqual(actual.adv, expected.adv)

    def test_default_roman_math_optical_zeros_are_exact_noto_math(self):
        for name in ('zero.ssty1', 'zero.ssty2'):
            actual = self.models[False].outline(name, 400)
            expected = build.read(self.math, name)
            self.assertEqual(actual.contours, expected.contours)
            self.assertEqual(actual.adv, expected.adv)

    def test_optical_zeros_are_compatible_open_and_grade_preserves_width(self):
        for italic, model in self.models.items():
            for width in (100, 62.5):
                for name in ('zero.ssty1', 'zero.ssty2'):
                    drawings = {weight: model.outline(name, weight, width) for weight in build.WEIGHTS}
                    self.assertEqual(len({build.structure(d) for d in drawings.values()}), 1)
                    self.assertEqual(len(drawings[400].contours), 2)
                    for weight, drawing in drawings.items():
                        self.assertTrue(build.sane(drawings[400], drawing), (italic, width, name, weight))
                    for base, target in itertools.product(drawings.values(), repeat=2):
                        graded = build.grade_outline(base, target)
                        self.assertEqual(graded.adv, base.adv)
                        self.assertTrue(build.sane(base, graded))

    def test_restored_feature_maps_match_native_zero_selection_only(self):
        for italic, model in self.models.items():
            source = TTFont(ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf' / ('Lisnoti-Italic.ttf' if italic else 'Lisnoti-Regular.ttf'))
            before = {name: curve_signature(source, name) for name in ('I', 'l', 'one')}
            # Simulate the old forced substitutions in prepared 0.400 sources.
            build.add_feature(source, 'onum', {'zero': 'zero.osf.slash'} if not italic else {'zero': 'zero.tosf'})
            build.add_feature(source, 'pnum', {'one': 'one.lf'})
            build.add_feature(source, 'lnum', {'zero.osf.slash': 'zero'} if not italic else {'zero.osf': 'zero.lf'})
            model.restore_fonts(source, copy.deepcopy(source))
            zero_names = set(model.names)
            for tag in FIGURE_FEATURES:
                actual = {a: b for a, b in build.single_subst_map(source, tag).items() if a in zero_names or b in zero_names}
                expected = {a: b for a, b in build.single_subst_map(model.noto[400], tag).items() if a in zero_names or b in zero_names}
                self.assertEqual(actual, expected, (italic, tag))
            self.assertEqual(build.single_subst_map(source, 'pnum')['one'], 'one.lf')
            for name in before:
                self.assertEqual(curve_signature(source, name), before[name], name)
            self.assertEqual(source['glyf']['zero'].numberOfContours, 2)
            self.assertEqual(source['glyf']['zero.slash'].numberOfContours, 3)

    def test_combined_native_figure_features_select_the_same_zero(self):
        for italic, model in self.models.items():
            font = TTFont(ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf' / ('Lisnoti-Italic.ttf' if italic else 'Lisnoti-Regular.ttf'))
            model.restore_fonts(font, copy.deepcopy(font))
            actual, native = zero_shaper(font), zero_shaper(model.noto[400])
            for enabled in itertools.product((False, True), repeat=len(FIGURE_FEATURES)):
                features = dict(zip(FIGURE_FEATURES, enabled))
                with self.subTest(italic=italic, features=features):
                    self.assertEqual(actual(features), native(features))

    def test_math_bold_double_struck_and_mono_zero_were_already_native_designs(self):
        source = TTFont(ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf/Lisnoti-Regular.ttf')
        for name in ('u1D7EC', 'u1D7D8', 'u1D7F6'):
            self.assertEqual(curve_signature(source, name), curve_signature(self.math, name), name)
        self.assertEqual(self.math['glyf']['u1D7F6'].numberOfContours, 3,
                         'The Noto Math monospace zero itself contains a dot; it is not a Lisnoti change')


if __name__ == '__main__':
    unittest.main()
