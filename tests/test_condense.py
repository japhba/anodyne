"""Condensed geometry keeps stroke/spacing decisions distinct from scaling."""
from pathlib import Path
import sys
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sources'))
from build import Outline, bbox, structure, sane
from condense import Policy, condense_outline, measured_stroke, measured_shear


def bar(stroke=80, height=700, advance=500, shear=0):
    return Outline([[(100, 0, True), (100+shear*height, height, True),
                     (100+shear*height+stroke, height, True), (100+stroke, 0, True)]], adv=advance)


def policy_font(condensed=False):
    names = ['.notdef', 'n', 'o', 'h', 'd', 'e', 'a', 's', 'u', 'l',
             'zero', 'plus', 'minus', 'supminus', 'esh', 'relation',
             'P', 'Sigma', 'D', 'i', 'weierstrass', 'doubleSum', 'doubleSum.rtlm', 'doubleD',
             'doubleI', 'doubleI.dtls', 'doubleI.opt']
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((20, 0))
        pen.lineTo((20, 700))
        pen.lineTo((84 if condensed else 100, 700))
        pen.lineTo((84 if condensed else 100, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    for name in ('esh', 'relation'):
        pen = TTGlyphPen(glyphs)
        pen.addComponent('supminus', (1, 0, 0, 1, 0, 0))
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupCharacterMap({**{ord(c): c for c in 'nohdeasulPDi'},
                               ord('0'): 'zero', ord('+'): 'plus',
                               ord('−'): 'minus', 0x207C: 'supminus',
                               0x1DF0B: 'esh', 0x2254: 'relation',
                               0x03A3: 'Sigma', 0x2118: 'weierstrass',
                               0x2140: 'doubleSum', 0x2145: 'doubleD', 0x2148: 'doubleI'})
    metrics = {name: (400 if condensed else 500, 20) for name in names}
    metrics.update(plus=(450 if condensed else 600, 20),
                   zero=(400 if condensed else 600, 20),
                   esh=(190 if condensed else 200, 20),
                   P=(420 if condensed else 600, 20),
                   Sigma=(520 if condensed else 650, 20),
                   i=(210 if condensed else 300, 20),
                   D=(500, 20), weierstrass=(600, 20),
                   doubleSum=(1000, 20), doubleD=(600, 20),
                   doubleI=(343, 20))
    metrics['doubleSum.rtlm'] = (1000, 20)
    metrics['doubleI.dtls'] = (343, 20)
    metrics['doubleI.opt'] = (206 if condensed else 343, 20)
    builder.setupHorizontalMetrics(metrics)
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font,
        'feature sups { sub minus by supminus; } sups;'
        'feature rtlm { sub doubleSum by doubleSum.rtlm; } rtlm;'
        'feature dtls { sub doubleI by doubleI.dtls; } dtls;'
        'feature ssty { sub doubleI by doubleI.opt; } ssty;')
    return builder.font


class CondensationTests(unittest.TestCase):
    def test_historical_math_letters_use_responsive_skeletons_and_rtl_inherits_them(self):
        normal, narrow = policy_font(), policy_font(True)
        policy = Policy(normal, {400: normal}, {400: narrow})
        self.assertAlmostEqual(policy.width_ratio('weierstrass', 400), .7)
        self.assertAlmostEqual(policy.width_ratio('doubleSum', 400), .8)
        self.assertAlmostEqual(policy.width_ratio('doubleSum.rtlm', 400), .8)
        self.assertAlmostEqual(policy.width_ratio('doubleD', 400), .8,
                               msg='A width-static D reference needs the calibrated fallback')
        self.assertAlmostEqual(policy.width_ratio('doubleI', 400), .7)
        self.assertAlmostEqual(policy.width_ratio('doubleI.dtls', 400), .7,
                               msg='Dotless and dotted cells must use the same responsive reference')
        self.assertAlmostEqual(policy.width_ratio('doubleI.opt', 400), 206/343,
                               msg='An already responsive optical reference must be retained')

    def test_sign_components_do_not_reclassify_phonetic_letters_as_relations(self):
        normal, narrow = policy_font(), policy_font(True)
        policy = Policy(normal, {400: normal}, {400: narrow})
        self.assertTrue({'minus', 'supminus', 'relation'} <= policy.math_signs)
        self.assertNotIn('esh', policy.math_signs)
        self.assertIn('esh', policy.affected_math_signs)
        self.assertAlmostEqual(policy.width_ratio('relation', 400), .75)
        self.assertAlmostEqual(policy.width_ratio('esh', 400), .95)

    def test_strokes_are_relative_to_glyph_size_and_advance_stays_at_target(self):
        for stroke, height in ((80, 700), (40, 350), (24, 190)):
            source = bar(stroke, height)
            result = condense_outline(source, .7, .9, 88)
            self.assertAlmostEqual(measured_stroke(result, 88), stroke*.9)
            self.assertEqual(result.adv, 350)
            self.assertEqual(bbox(result.contours)[1::2], (0, height))
            self.assertEqual(structure(result), structure(source))
            self.assertTrue(sane(source, result))

    def test_italic_shear_is_preserved_while_counter_width_changes(self):
        source = bar(shear=.21)
        result = condense_outline(source, .7, .9, 88, shear=.21)
        points = result.contours[0]
        top = (points[1][0]+points[2][0])/2
        bottom = (points[0][0]+points[3][0])/2
        self.assertAlmostEqual((top-bottom)/700, .21)
        self.assertEqual(result.adv, 350)
        self.assertAlmostEqual(measured_shear(source), .21)
        self.assertAlmostEqual(measured_shear(result), .21)

    def test_round_dots_keep_shape_but_condense_spacing(self):
        contours = [[(x, 0, True), (x, 60, True), (x+60, 60, True), (x+60, 0, True)]
                    for x in (20, 180, 340)]
        result = condense_outline(Outline(contours, adv=440), .7, .9, 88)
        for original, condensed in zip(contours, result.contours):
            x0, y0, x1, y1 = bbox([condensed])
            self.assertEqual((x1-x0, y1-y0), (60, 60))
            before = bbox([original])
            self.assertAlmostEqual((x0+x1)/2, .7*(before[0]+before[2])/2)
        self.assertEqual(result.adv, 308)

    def test_small_letter_with_a_counter_is_not_treated_as_a_dot(self):
        outer = [(0, 0, True), (0, 140, True), (120, 140, True), (120, 0, True)]
        inner = [(30, 30, True), (90, 30, True), (90, 110, True), (30, 110, True)]
        source = Outline([outer, inner], adv=160)
        result = condense_outline(source, .7, .9, 88)
        self.assertLess(bbox(result.contours)[2]-bbox(result.contours)[0], 120)
        self.assertTrue(sane(source, result))

    def test_horizontal_rules_keep_vertical_thickness(self):
        source = Outline([[(0, 0, True), (0, 30, True), (600, 30, True), (600, 0, True)]], adv=660)
        result = condense_outline(source, .7, .9, 88)
        self.assertEqual(measured_stroke(source, 88), 0)
        self.assertEqual(bbox(result.contours), (0, 0, 420, 30))
        self.assertAlmostEqual(result.adv, 462)

    def test_zero_advance_combining_marks_keep_zero_advance(self):
        source = bar(stroke=20, height=190, advance=0)
        self.assertEqual(condense_outline(source, .7, .9, 88).adv, 0)


if __name__ == '__main__':
    unittest.main()
