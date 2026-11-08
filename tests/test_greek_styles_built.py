"""Every added Greek alphabet must vary in the released desktop fonts."""
import os
from pathlib import Path
import sys
import unittest

from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from build import single_subst_map

FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


class BuiltGreekStyleVariationTests(unittest.TestCase):
    def test_all_greek_style_targets_respond_to_weight_width_and_grade(self):
        files = sorted((FONTS / 'variable').glob('*.ttf'))
        self.assertEqual(len(files), 2)
        for path in files:
            with TTFont(path) as font:
                names = set()
                for number in range(8, 15):
                    mapping = single_subst_map(font, f'ss{number:02d}')
                    self.assertTrue(mapping, f'{path.name}: Greek ss{number:02d} missing')
                    names.update(mapping.values())
                self.assertEqual(len(names), 2121)
                glyphsets = [font.getGlyphSet(location=location) for location in (
                    {'wght': 400, 'wdth': 100, 'GRAD': 0},
                    {'wght': 900, 'wdth': 100, 'GRAD': 0},
                    {'wght': 400, 'wdth': 62.5, 'GRAD': 0},
                    {'wght': 400, 'wdth': 100, 'GRAD': 150},
                )]
                unchanged = {'weight': [], 'width': [], 'grade': []}
                moved_by_grade = []
                for name in sorted(names):
                    areas = []
                    for glyphset in glyphsets:
                        pen = AreaPen(glyphset)
                        glyphset[name].draw(pen)
                        areas.append(pen.value)
                    for index, axis in enumerate(unchanged, 1):
                        if abs(areas[index] - areas[0]) < 1:
                            unchanged[axis].append(name)
                    if abs(glyphsets[3][name].width - glyphsets[0][name].width) > .01:
                        moved_by_grade.append(name)
                with self.subTest(font=path.name):
                    self.assertEqual(unchanged, {'weight': [], 'width': [], 'grade': []})
                    self.assertEqual(moved_by_grade, [])


if __name__ == '__main__':
    unittest.main()
