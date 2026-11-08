"""Production width masters retain Noto's native designs and math italic angle."""
import os
from pathlib import Path
import sys
import unittest

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources'))
from build import Outline, single_subst_map
from condense import measured_shear, MATH_SIGNS

FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT/'fonts'))


def coordinates(glyphs, name):
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return [(operation, points) for operation, points in pen.value]


def outline(glyphs, name):
    pen = TTGlyphPen(glyphs)
    glyphs[name].draw(pen)
    glyph = pen.glyph()
    if glyph.isComposite():
        raise ValueError('The shear proof requires a simple mathematical I')
    contours, start = [], 0
    for end in glyph.endPtsOfContours:
        contours.append([(glyph.coordinates[i][0], glyph.coordinates[i][1], bool(glyph.flags[i]&1))
                         for i in range(start, end+1)])
        start = end+1
    return Outline(contours, adv=glyphs[name].width)


class BuiltCondensationTests(unittest.TestCase):
    def test_arithmetic_and_relation_widths_stay_coherent_across_the_axes(self):
        for path in (FONTS/'variable').glob('*.ttf'):
            with TTFont(path) as font:
                cmap = font.getBestCmap()
                names = [cmap[ord(character)] for character in MATH_SIGNS]
                for weight in (100, 400, 550, 700, 900):
                    # Compound cells differ between faces and weights. Width
                    # must retain each drawing's own normal-width proportion.
                    normal = font.getGlyphSet(location={'wght':weight, 'wdth':100, 'GRAD':0})
                    proportions = {character: normal[cmap[ord(character)]].width / normal[cmap[ord('+')]].width
                                   for character in ('≔', '⩴')}
                    for width in (62.5, 75, 87.5, 100):
                        for grade in (-100, 0, 150):
                            glyphs = font.getGlyphSet(location={'wght':weight, 'wdth':width, 'GRAD':grade})
                            advances = [glyphs[name].width for name in names]
                            with self.subTest(font=path.name, weight=weight, width=width, grade=grade):
                                self.assertLessEqual(max(advances)-min(advances), 1.25)
                                plus = glyphs[cmap[ord('+')]].width
                                for character, proportion in proportions.items():
                                    self.assertAlmostEqual(glyphs[cmap[ord(character)]].width/plus,
                                                           proportion, delta=.006)

    def test_native_noto_drawings_at_named_and_intermediate_widths(self):
        for italic in (False, True):
            original = ROOT/'src/noto'/('NotoSans-Italic[wdth,wght].ttf' if italic else 'NotoSans[wdth,wght].ttf')
            if not original.exists():
                self.skipTest('Pinned reference fonts are available after make prepare')
            current = FONTS/'variable'/('Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf')
            with TTFont(original) as upstream, TTFont(current) as actual:
                # Include native numeral wrappers: an unchanged component list
                # can still contain a child with its own real width masters.
                # Nonzero numerator/denominator forms use Lisnoti's optical
                # children, so they are not native-copy assertions.
                names = ('H', 'n', 'o', 'e', 'a', 's', 'u', 'uni2139') + tuple(
                    digit + suffix
                    for digit in ('zero', 'one', 'two', 'three', 'four', 'five',
                                  'six', 'seven', 'eight', 'nine')
                    for suffix in ('', '.lf', '.osf', '.tosf'))
                if italic:
                    names += ('uni210E', 'uni210F')
                for weight in (100, 400, 700, 900):
                    for width in (62.5, 75, 87.5, 100):
                        source = upstream.getGlyphSet(location={'wght':weight, 'wdth':width})
                        target = actual.getGlyphSet(location={'wght':weight, 'wdth':width, 'GRAD':0})
                        for name in names:
                            with self.subTest(italic=italic, weight=weight, width=width, glyph=name):
                                left, right = coordinates(source, name), coordinates(target, name)
                                self.assertEqual([v[0] for v in left], [v[0] for v in right])
                                for (_, a), (_, b) in zip(left, right):
                                    self.assertEqual(len(a), len(b))
                                    for pa, pb in zip(a, b):
                                        if pa is not None:
                                            self.assertAlmostEqual(pa[0], pb[0], delta=1.25)
                                            self.assertAlmostEqual(pa[1], pb[1], delta=1.25)
                                self.assertAlmostEqual(source[name].width, target[name].width, delta=1.25)

    def test_derived_math_italic_i_keeps_its_slant_when_condensed(self):
        for path in (FONTS/'variable').glob('*.ttf'):
            with TTFont(path) as font:
                name = font.getBestCmap()[0x1D43C]
                for weight in (100, 400, 700, 900):
                    base = font.getGlyphSet(location={'wght':weight, 'wdth':100, 'GRAD':0})
                    expected = measured_shear(outline(base, name))
                    for width in (62.5, 75, 87.5):
                        narrow = font.getGlyphSet(location={'wght':weight, 'wdth':width, 'GRAD':0})
                        with self.subTest(font=path.name, weight=weight, width=width):
                            self.assertAlmostEqual(measured_shear(outline(narrow, name)), expected, delta=.006)

    def test_math_monospace_latin_greek_and_digits_share_a_cell_on_every_axis(self):
        for path in (FONTS/'variable').glob('*.ttf'):
            with TTFont(path) as font:
                cmap = font.getBestCmap()
                names = {cmap[cp] for cp in list(range(0x1D670, 0x1D6A4))+list(range(0x1D7F6, 0x1D800))}
                greek = single_subst_map(font, 'ss13')
                self.assertTrue(greek, 'The Greek monospace feature must be present')
                names.update(greek.values())
                for weight in (100, 400, 700, 900):
                    for width in (62.5, 75, 87.5, 100):
                        for grade in (-100, 0, 150):
                            glyphs = font.getGlyphSet(location={'wght':weight, 'wdth':width, 'GRAD':grade})
                            advances = [glyphs[name].width for name in names]
                            with self.subTest(font=path.name, weight=weight, width=width, grade=grade):
                                self.assertLess(max(advances)-min(advances), .01)


if __name__ == '__main__':
    unittest.main()
