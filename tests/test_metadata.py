"""Final metric regressions: text line height and mathematical clipping differ."""
from pathlib import Path
import sys
import unittest
import os

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))
sys.path.insert(0, str(ROOT / 'sources'))
from metadata import finalize_metrics, static_stat
import build


class MetadataTests(unittest.TestCase):
    def test_math_clip_bounds_do_not_change_text_line_height(self):
        font = TTFont(FONTS / 'static/Anodyne-Regular.ttf')
        metrics = (font['hhea'].ascent, font['hhea'].descent, font['hhea'].lineGap)
        finalize_metrics(font)
        self.assertGreaterEqual(font['OS/2'].usWinAscent, font['head'].yMax)
        self.assertGreaterEqual(font['OS/2'].usWinDescent, -font['head'].yMin)
        self.assertEqual(metrics, (font['hhea'].ascent, font['hhea'].descent, font['hhea'].lineGap))
        self.assertTrue(font['OS/2'].fsSelection & 0x80)

    def test_text_subset_clip_envelope_covers_axis_corners(self):
        font = TTFont(FONTS / 'variable/Anodyne[GRAD,wdth,wght].ttf')
        options = subset.Options()
        options.notdef_outline = True
        tool = subset.Subsetter(options)
        tool.populate(glyphs=['.notdef', 'space', 'H', 'x', 'acutecomb'])
        tool.subset(font)
        finalize_metrics(font, reset_clip=True)
        self.assertLess(font['OS/2'].usWinAscent, 2000)
        for weight in (100, 400, 900):
            for width in (62.5, 100):
                for grade in (-100, 150):
                    glyphset = font.getGlyphSet(location={'wght': weight, 'wdth': width, 'GRAD': grade})
                    for name in font.getGlyphOrder():
                        pen = BoundsPen(glyphset)
                        glyphset[name].draw(pen)
                        if pen.bounds:
                            self.assertGreaterEqual(font['OS/2'].usWinAscent, pen.bounds[3])
                            self.assertGreaterEqual(font['OS/2'].usWinDescent, -pen.bounds[1])

    def test_static_stat_keeps_arbitrary_axis_coordinates(self):
        font = TTFont(FONTS / 'static/Anodyne-Regular.ttf')
        static_stat(font, 550, 75, 50, True)
        table = font['STAT'].table
        values = {table.DesignAxisRecord.Axis[a.AxisIndex].AxisTag: a.Value for a in table.AxisValueArray.AxisValue}
        self.assertEqual(values, {'wght': 550, 'wdth': 75, 'GRAD': 50, 'ital': 1})

    def test_all_variable_menu_names_fit_legacy_windows_limit(self):
        for italic, filename in ((False, 'Anodyne[GRAD,wdth,wght].ttf'),
                                 (True, 'Anodyne-Italic[GRAD,wdth,wght].ttf')):
            font = TTFont(FONTS / 'variable' / filename)
            build.stat(font, italic)
            family = font['name'].getDebugName(1)
            for instance in font['fvar'].instances:
                name = font['name'].getDebugName(instance.subfamilyNameID)
                self.assertLessEqual(len(f'{family} {name}'), 31, name)
            values = font['STAT'].table.AxisValueArray.AxisValue
            weights = [font['name'].getDebugName(v.ValueNameID) for v in values if v.AxisIndex == 0 and not v.Flags & 2]
            widths = [font['name'].getDebugName(v.ValueNameID) for v in values if v.AxisIndex == 1 and not v.Flags & 2]
            for weight in weights:
                for width in widths:
                    name = ' '.join([family, width, weight] + (['Italic'] if italic else []))
                    self.assertLessEqual(len(name), 31, name)


if __name__ == '__main__':
    unittest.main()
