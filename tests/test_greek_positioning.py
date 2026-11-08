"""Greek mathematical marks must use real GPOS anchors after substitution."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
import unicodedata

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from greek_positioning import extend_greek_mark_anchors, greek_relations


def specimen_font():
    boxes = {'.notdef': (0, 0, 100, 500, 500), 'alpha': (50, 0, 550, 500, 600),
             'epsilon': (50, 0, 450, 500, 500), 'epsilonSymbol': (80, 0, 500, 500, 550),
             'delta': (30, -100, 510, 700, 550), 'Delta': (0, 0, 700, 700, 720),
             'thetaSymbol': (100, -40, 600, 700, 650), 'partial': (130, -180, 600, 750, 630),
             'nabla': (20, 0, 680, 700, 700), 'mathAlpha': (150, -50, 750, 650, 800),
             'mathThetaSymbol': (50, -100, 700, 800, 800), 'mathEpsilonSymbol': (120, -50, 600, 600, 650),
             'mathPartial': (120, -120, 650, 850, 700), 'mathNabla': (0, 0, 650, 700, 700),
             'scriptAlpha': (200, -100, 900, 900, 1000),
             'circumflexcomb': (-100, 0, 100, 100, 0), 'dotbelowcomb': (-40, -40, 40, 0, 0)}
    cmap = {0x03B1: 'alpha', 0x03B5: 'epsilon', 0x03F5: 'epsilonSymbol', 0x03B4: 'delta',
            0x0394: 'Delta', 0x03D1: 'thetaSymbol', 0x2202: 'partial', 0x2207: 'nabla',
            0x0302: 'circumflexcomb', 0x0323: 'dotbelowcomb'}
    for label, name in [('SMALL ALPHA', 'mathAlpha'), ('THETA SYMBOL', 'mathThetaSymbol'),
                        ('EPSILON SYMBOL', 'mathEpsilonSymbol'), ('PARTIAL DIFFERENTIAL', 'mathPartial'),
                        ('NABLA', 'mathNabla')]:
        cmap[ord(unicodedata.lookup('MATHEMATICAL ITALIC ' + label))] = name
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(list(boxes))
    builder.setupCharacterMap(cmap)
    outlines = {}
    for name, (x0, y0, x1, y1, _advance) in boxes.items():
        pen = TTGlyphPen(None)
        pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
        outlines[name] = pen.glyph()
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics({name: (box[-1], box[0]) for name, box in boxes.items()})
    builder.setupHorizontalHeader(ascent=1100, descent=-300)
    builder.setupNameTable({'familyName': 'GreekAnchorTest', 'styleName': 'Regular'})
    builder.setupOS2(sTypoAscender=1100, sTypoDescender=-300, usWinAscent=1100, usWinDescent=300)
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font, '''
        languagesystem DFLT dflt;
        markClass circumflexcomb <anchor 0 0> @above;
        markClass dotbelowcomb <anchor 0 0> @below;
        feature mark {
          pos base alpha <anchor 300 600> mark @above <anchor 300 -100> mark @below;
          pos base epsilon <anchor 250 600> mark @above <anchor 250 -100> mark @below;
          pos base delta <anchor 270 800> mark @above <anchor 270 -200> mark @below;
          pos base Delta <anchor 350 800> mark @above <anchor 350 -100> mark @below;
          pos base thetaSymbol <anchor 450 810> mark @above <anchor 350 -140> mark @below;
        } mark;
        feature ss08 { sub alpha by scriptAlpha; } ss08;
    ''')
    buildMathTable(builder.font, topAccentAttachments={'mathAlpha': 490, 'scriptAlpha': 730})
    return builder.font


def shaping_font(font):
    output = BytesIO()
    font.save(output)
    return hb.Font(hb.Face(output.getvalue()))


def shape(font, text, features=None):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features or {})
    return [(info.codepoint, position.x_advance, position.x_offset, position.y_offset)
            for info, position in zip(buffer.glyph_infos, buffer.glyph_positions)]


class GreekMarkPositioningTests(unittest.TestCase):
    def test_unicode_variants_and_feature_targets_keep_their_true_base(self):
        relations = greek_relations(specimen_font())
        self.assertEqual(relations['mathThetaSymbol'], 'thetaSymbol')
        self.assertEqual(relations['mathEpsilonSymbol'], 'epsilonSymbol')
        self.assertEqual(relations['mathPartial'], 'partial')
        self.assertEqual(relations['scriptAlpha'], 'alpha')

    def test_actual_harfbuzz_positions_use_geometry_adjusted_above_and_below_anchors(self):
        font = specimen_font()
        before = shaping_font(font)
        untouched = {tag: font.getTableData(tag) for tag in ('glyf', 'cmap', 'hmtx')}
        self.assertGreater(extend_greek_mark_anchors(font)['added_records'], 0)
        after = shaping_font(font)
        alpha = unicodedata.lookup('MATHEMATICAL ITALIC SMALL ALPHA')
        above = shape(after, alpha + '\u0302')
        below = shape(after, alpha + '\u0323')
        self.assertEqual(above[1][1:], (0, -310, 790))
        self.assertEqual(below[1][1:], (0, -350, -190))
        self.assertNotEqual(above, shape(before, alpha + '\u0302'))
        self.assertNotEqual(above, shape(after, alpha + '\u0302', {'mark': False}))
        styled = shape(after, 'α\u0302', {'ss08': True})
        self.assertEqual(font.getGlyphName(styled[0][0]), 'scriptAlpha')
        self.assertEqual(styled[1][1:], (0, -270, 1100))
        for tag, data in untouched.items():
            self.assertEqual(font.getTableData(tag), data)

    def test_missing_native_symbol_anchors_use_calibrated_donors_and_remain_idempotent(self):
        font = specimen_font()
        extend_greek_mark_anchors(font)
        positioned = shaping_font(font)
        for character in 'ϵ∂∇' + ''.join(unicodedata.lookup('MATHEMATICAL ITALIC ' + label)
                                       for label in ('EPSILON SYMBOL', 'PARTIAL DIFFERENTIAL', 'NABLA')):
            with self.subTest(character=character):
                self.assertNotEqual(shape(positioned, character + '\u0302'),
                                    shape(positioned, character + '\u0302', {'mark': False}))
        data = font.getTableData('GPOS')
        self.assertEqual(extend_greek_mark_anchors(font)['added_records'], 0)
        self.assertEqual(font.getTableData('GPOS'), data)
        for lookup in font['GPOS'].table.LookupList.Lookup:
            for subtable in lookup.SubTable:
                if subtable.__class__.__name__ != 'MarkBasePos':
                    continue
                names = subtable.BaseCoverage.glyphs
                self.assertEqual(names, sorted(names, key=font.getGlyphID))
                self.assertEqual(len(names), subtable.BaseArray.BaseCount)
                self.assertEqual(len(names), len(subtable.BaseArray.BaseRecord))
        for target in greek_relations(font):
            self.assertEqual(font['GDEF'].table.GlyphClassDef.classDefs[target], 1)

    def test_real_font_math_greek_marks_do_not_depend_on_fallback_positioning(self):
        path = ROOT / 'fonts/static/Anodyne-Regular.ttf'
        if not path.exists():
            self.skipTest('Build a distribution first')
        with TTFont(path) as font:
            extend_greek_mark_anchors(font)
            positioned = shaping_font(font)
            for character in '𝛂𝛼𝜶𝝰𝞪𝜖𝜕𝛻':
                with self.subTest(character=character):
                    above = shape(positioned, character + '\u0302')
                    self.assertEqual(len(above), 2)
                    self.assertEqual(above[1][1], 0)
                    self.assertNotEqual(above, shape(positioned, character + '\u0302', {'mark': False}))


if __name__ == '__main__':
    unittest.main()
