"""Release fonts must carry working Greek GPOS, including partial web adapters."""
import os
from pathlib import Path
import sys
import unittest

import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from check import harfbuzz_font
from greek_positioning import GREEK_FEATURES

FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


def shape(font, text, features):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features)
    return [(info.codepoint, position.x_advance, position.x_offset, position.y_offset)
            for info, position in zip(buffer.glyph_infos, buffer.glyph_positions)]


class BuiltGreekPositioningTests(unittest.TestCase):
    def assert_mark_positioned(self, font, text, features):
        positioned = shape(font, text, dict(features, mark=True))
        unpositioned = shape(font, text, dict(features, mark=False))
        self.assertEqual(len(positioned), 2)
        self.assertTrue(all(record[0] for record in positioned), 'No missing Greek or combining mark glyph')
        self.assertEqual(positioned[1][1], 0)
        self.assertNotEqual(positioned, unpositioned, 'The compiled mark lookup must position the real Greek glyph')

    def test_desktop_math_alphabets_and_named_greek_features_position_marks(self):
        files = sorted(FONTS.glob('*/*.ttf'))
        self.assertEqual(len(files), 6)
        for path in files:
            font = harfbuzz_font(path)
            points = [(400, 100, 0)] if path.parent.name == 'static' else [(400, 100, 0), (100, 62.5, -100), (900, 62.5, 150)]
            for weight, width, grade in points:
                font.set_variations({'wght': weight, 'wdth': width, 'GRAD': grade})
                for character in '𝛂𝛼𝜶𝝰𝞪𝜖𝜕𝛻':
                    for mark in '\u0302\u0323':
                        with self.subTest(font=path.name, character=character, mark=mark, weight=weight, width=width, grade=grade):
                            self.assert_mark_positioned(font, character + mark, {})
                for tag in sorted(GREEK_FEATURES):
                    with self.subTest(font=path.name, tag=tag, weight=weight, width=width, grade=grade):
                        self.assert_mark_positioned(font, 'α\u0302', {tag: True})

    def test_partial_greek_web_families_keep_marks_in_the_same_shaping_font(self):
        files = sorted((FONTS / 'mathwebfonts').glob('*-greek-*.woff2'))
        self.assertEqual(len(files), 14)
        for path in files:
            font = harfbuzz_font(path)
            for weight, width, grade in [(400, 100, 0), (800, 75, 100)]:
                font.set_variations({'wght': weight, 'wdth': width, 'GRAD': grade})
                for mark in '\u0302\u0323':
                    with self.subTest(font=path.name, mark=mark, weight=weight, width=width, grade=grade):
                        self.assert_mark_positioned(font, 'α' + mark, {})


if __name__ == '__main__':
    unittest.main()
