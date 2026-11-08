"""A radical's drawn cap and the renderer's MATH rule must have one thickness."""
import io
import os
from pathlib import Path
import unittest

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))


class RadicalJoinTests(unittest.TestCase):
    def test_caps_match_MATH_at_every_size_and_axis_corner(self):
        files = list(FONTS.glob('*/*.ttf'))
        files += [FONTS/'mathwebfonts'/name for name in ('anodyne-math.woff2', 'anodyne-math-italic.woff2')]
        for path in files:
            with self.subTest(font=path.name), TTFont(path) as tt:
                root = tt.getBestCmap()[0x221A]
                variants = tt['MATH'].table.MathVariants
                construction = variants.VertGlyphConstruction[variants.VertGlyphCoverage.glyphs.index(root)]
                names = {record.VariantGlyph for record in construction.MathGlyphVariantRecord}
                names.add(root)
                names.add(construction.GlyphAssembly.PartRecords[-1].glyph)
                tt.flavor = None
                stream = io.BytesIO()
                tt.save(stream)
                font = hb.Font(hb.Face(stream.getvalue()))
                locations = ({'wght': w, 'wdth': d, 'GRAD': g}
                             for w in (100, 400, 900) for d in (62.5, 100) for g in (-100, 0, 150)) if 'fvar' in tt else [{}]
                for location in locations:
                    font.set_variations(location)
                    thickness = font.get_math_constant(hb.OTMathConstant.RADICAL_RULE_THICKNESS)
                    glyphs = tt.getGlyphSet(location=location)
                    for name in names:
                        pen = TTGlyphPen(glyphs)
                        glyphs[name].draw(pen)
                        points = list(pen.glyph().coordinates)
                        right = max(x for x, y in points)
                        ys = [y for x, y in points if x == right]
                        self.assertAlmostEqual(max(ys)-min(ys), thickness, delta=1.1,
                                               msg=f'{path.name}/{name}/{location}')


if __name__ == '__main__':
    unittest.main()
