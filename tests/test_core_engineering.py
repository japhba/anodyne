"""Runtime regressions for grade safety and a shared GPOS/MATH variation store."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sources'))
import build as anodyne


def font_master(path, rule, accent, kern):
    builder = FontBuilder(1000, isTTF=True)
    order = ['.notdef', 'H', 'x']
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({72: 'H', 120: 'x'})
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0)); pen.lineTo((50, 700))
        pen.lineTo((450, 700)); pen.lineTo((450, 0)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500, 50) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'MathVariationTest', 'styleName': 'Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font, f'feature kern {{ pos H x {kern}; }} kern;')
    buildMathTable(builder.font, constants={'FractionRuleThickness': rule}, topAccentAttachments={'x': accent})
    builder.save(path)


class EngineeringTests(unittest.TestCase):
    @staticmethod
    def stem_font(points=None, glyph=None):
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(['.notdef', 'l'])
        if glyph is None:
            pen = TTGlyphPen(None)
            pen.moveTo(points[0])
            for point in points[1:]:
                pen.lineTo(point)
            pen.closePath()
            glyph = pen.glyph()
        empty = TTGlyphPen(None).glyph()
        builder.setupGlyf({'.notdef': empty, 'l': glyph})
        builder.setupHorizontalMetrics({'.notdef': (500, 0), 'l': (500, 0)})
        return builder.font

    def test_italic_stem_measurement_excludes_full_height_shear(self):
        slanted = self.stem_font([(0, 0), (161, 760), (187, 760), (26, 0)])
        upright = self.stem_font([(0, 0), (0, 760), (26, 760), (26, 0)])
        self.assertEqual(slanted['glyf']['l'].xMax - slanted['glyf']['l'].xMin, 187)
        self.assertEqual(anodyne.measure_stem(slanted), 26)
        self.assertEqual(anodyne.measure_stem(upright), 26)

    def test_pinned_noto_stems_at_all_weight_width_masters(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
            ('NotoSans[wdth,wght].ttf', 100): (26, 88, 150.8284912109375, 191),
            ('NotoSans[wdth,wght].ttf', 62.5): (26, 81, 130.4088134765625, 162),
            ('NotoSans-Italic[wdth,wght].ttf', 100): (26, 88, 149.6085205078125, 189),
            ('NotoSans-Italic[wdth,wght].ttf', 62.5): (26, 77, 127.93377685546875, 160.5),
        }
        if not all((root / 'src/noto' / name).exists() for name, _ in expected):
            self.skipTest('Pinned Noto inputs are available after make prepare')
        for (name, width), stems in expected.items():
            with TTFont(root / 'src/noto' / name) as source:
                for weight, expected_stem in zip((100, 400, 700, 900), stems):
                    # Instance the measured glyph only, keeping this regression
                    # inexpensive rather than instancing a complete source font.
                    glyphs = source.getGlyphSet(location={'wght': weight, 'wdth': width})
                    pen = TTGlyphPen(glyphs)
                    glyphs['l'].draw(pen)
                    font = self.stem_font(glyph=pen.glyph(round=lambda value: value))
                    with self.subTest(source=name, weight=weight, width=width):
                        # The complete instancer quantizes normalized locations
                        # to F2Dot14; glyph-set sampling retains float locations.
                        self.assertAlmostEqual(anodyne.measure_stem(font), expected_stem, delta=.01)

    def test_grade_preserves_advance_and_backs_off_inverted_stroke(self):
        base = anodyne.Outline([[(100, 0, True), (100, 700, True), (120, 700, True), (120, 0, True)]], adv=300)
        # Removing the target's advance growth at the base point positions would
        # make the right edge pass the left. The guard must retain positive ink.
        target = anodyne.Outline([[(100, 0, True), (100, 700, True), (110, 700, True), (110, 0, True)]], adv=600)
        result = anodyne.grade_outline(base, target)
        self.assertEqual(result.adv, base.adv)
        self.assertGreater(anodyne.area(base.contours[0]) * anodyne.area(result.contours[0]), 0)

    def test_preflight_rejects_equal_point_counts_with_incompatible_curve_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / 'regular.ttf', Path(tmp) / 'black.ttf']
            for path in paths:
                font_master(path, 30, 300, -40)
            anodyne.validate_master_compatibility(paths)
            altered = TTFont(paths[1])
            # This is the rejected-fit failure: the number of points still
            # matches, but one master has an off-curve point at the same index.
            altered['glyf']['x'].flags[1] &= ~1
            altered.save(paths[1])
            with self.assertRaisesRegex(ValueError, 'Incompatible master glyphs.*x:'):
                anodyne.validate_master_compatibility(paths)

    def test_math_and_positioning_share_store_in_runtime_and_static_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / 'regular.ttf', root / 'black.ttf']
            font_master(paths[0], 30, 300, -40)
            font_master(paths[1], 90, 150, -80)
            ds = DesignSpaceDocument()
            axis = AxisDescriptor()
            axis.tag, axis.name = 'wght', 'Weight'
            axis.minimum, axis.default, axis.maximum = 400, 400, 900
            ds.addAxis(axis)
            for weight, path in zip((400, 900), paths):
                source = SourceDescriptor()
                source.path, source.location = str(path), {'Weight': weight}
                ds.addSource(source)
            variable, model, master_paths = build_variable(ds)
            original_data_count = len(variable['GDEF'].table.VarStore.VarData)
            anodyne.add_math_variations(variable, model, master_paths)
            self.assertGreater(len(variable['GDEF'].table.VarStore.VarData), original_data_count)
            output = root / 'variable.ttf'
            variable.save(output)
            for weight, rule, accent, advance in ((400, 30, 300, 960), (900, 90, 150, 920)):
                runtime = hb.Font(hb.Face(output.read_bytes()))
                runtime.set_variations({'wght': weight})
                self.assertEqual(runtime.get_math_constant(hb.OTMathConstant.FRACTION_RULE_THICKNESS), rule)
                self.assertEqual(runtime.get_math_glyph_top_accent_attachment(2), accent)
                buf = hb.Buffer(); buf.add_str('Hx'); buf.guess_segment_properties()
                hb.shape(runtime, buf)
                self.assertEqual(sum(p.x_advance for p in buf.glyph_positions), advance)
                instance = instantiateVariableFont(copy.deepcopy(variable), {'wght': weight})
                self.assertEqual(instance['MATH'].table.MathConstants.FractionRuleThickness.Value, rule)
                self.assertEqual(instance['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment[0].Value, accent)
                static_path = root / f'{weight}.ttf'
                instance.save(static_path)
                reloaded = TTFont(static_path)
                self.assertNotIn('fvar', reloaded)
                self.assertIsNone(reloaded['MATH'].table.MathConstants.FractionRuleThickness.DeviceTable)


if __name__ == '__main__':
    unittest.main()
