"""Text defaults must retain native design, shaping and optional old drawings."""
import copy
import io
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from textforms import apply_text_forms, native_top_anchor, SUFFIX


def runtime(font):
    stream = io.BytesIO()
    font.save(stream)
    return hb.Font(hb.Face(stream.getvalue()))


def shape(font, text, features=None):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features or {})
    return [(g.codepoint, p.x_advance, p.x_offset, p.y_offset)
            for g, p in zip(buffer.glyph_infos, buffer.glyph_positions)]


class TextFormsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.faces = []
        for style in ('Regular', 'Italic'):
            path = ROOT / f'src/lisnoti/font-Lisnoti/Lisnoti-ttf/Lisnoti-{style}.ttf'
            if not path.exists():
                raise unittest.SkipTest('Run make fetch for pinned source drawings')
            original = TTFont(path)
            changed = copy.deepcopy(original)
            cls.faces.append((style, original, changed, apply_text_forms(changed),
                              runtime(original), runtime(changed)))

    def test_baseline_J_is_the_complete_native_alternate(self):
        for style, original, changed, report, before, after in self.faces:
            for char, name in (('J', 'J.salt'), ('Ĵ', 'Jcircumflex.salt')):
                with self.subTest(style=style, char=char):
                    self.assertEqual(changed.getBestCmap()[ord(char)], name)
                    self.assertEqual(changed['hmtx'][name], original['hmtx'][name])
                    self.assertEqual(changed['glyf'][name].compile(changed['glyf']),
                                     original['glyf'][name].compile(original['glyf']))
                    # A normal curved-baseline overshoot, rather than a descender.
                    self.assertGreater(changed['glyf'][name].yMin, -20)
                    self.assertEqual(shape(after, char, {'cv03': 1}), shape(before, char))

    def test_t_changes_only_the_shoulder_and_keeps_originals_exact(self):
        for style, original, changed, report, before, after in self.faces:
            for name in report['square_t']:
                with self.subTest(style=style, glyph=name):
                    saved = changed['glyf'][name+SUFFIX]
                    old = original['glyf'][name]
                    if not saved.isComposite():
                        self.assertEqual(list(saved.coordinates), list(old.coordinates))
                        self.assertEqual(list(saved.flags), list(old.flags))
                    self.assertEqual(changed['hmtx'][name+SUFFIX], original['hmtx'][name])
            old, new = original['glyf']['t'], changed['glyf']['t']
            self.assertNotEqual(list(new.coordinates), list(old.coordinates))
            # The foot and terminals remain native: no blanket corner rounding.
            for previous, current in zip(old.coordinates, new.coordinates):
                if previous[1] < 400:
                    self.assertEqual(previous, current)

    def test_legacy_marks_accents_and_small_caps_keep_working(self):
        for style, original, changed, report, before, after in self.faces:
            for text in ('t', 'ţ', 'ť', 'ŧ', 'ṫ', 'ṭ', 't\u0301', 't\u0323'):
                with self.subTest(style=style, text=text):
                    expected = shape(before, text)
                    actual = shape(after, text, {'cv04': 1})
                    # New glyph IDs select exact copies of the old drawings;
                    # positioning and advances must remain identical.
                    self.assertEqual([p[1:] for p in actual], [p[1:] for p in expected])
                    self.assertTrue(all(p[0] for p in actual))
            if any(r.FeatureTag == 'c2sc' for r in original['GSUB'].table.FeatureList.FeatureRecord):
                self.assertEqual(shape(before, 'J', {'c2sc': 1}), shape(after, 'J', {'c2sc': 1}))

    def test_registration_preserves_existing_tables_and_is_idempotent(self):
        for style, original, changed, report, before, after in self.faces:
            old = {r.FeatureTag for r in original['GSUB'].table.FeatureList.FeatureRecord}
            new = {r.FeatureTag for r in changed['GSUB'].table.FeatureList.FeatureRecord}
            self.assertEqual(new, old | {'cv03', 'cv04'})
            self.assertEqual(apply_text_forms(changed), {})
            for tag in ('GSUB', 'GPOS', 'GDEF', 'MATH'):
                changed[tag].compile(changed)

    def test_baseline_J_math_accent_follows_the_stem(self):
        for style, original, changed, report, before, after in self.faces:
            accents = changed['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
            values = dict(zip(accents.TopAccentCoverage.glyphs,
                              [record.Value for record in accents.TopAccentAttachment]))
            points = list(changed['glyf']['J.salt'].coordinates)
            top = max(y for x, y in points)
            xs = [x for x, y in points if y == top]
            self.assertAlmostEqual(values['J.salt'], (min(xs)+max(xs))/2, delta=1)

    def test_square_t_accents_follow_its_cap_and_legacy_math_is_preserved(self):
        for style, original, changed, report, before, after in self.faces:
            old = original['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
            old_values = dict(zip(old.TopAccentCoverage.glyphs, [r.Value for r in old.TopAccentAttachment]))
            new = changed['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
            values = dict(zip(new.TopAccentCoverage.glyphs, [r.Value for r in new.TopAccentAttachment]))
            self.assertEqual(values['t'+SUFFIX], old_values['t'])
            self.assertEqual(values['t'], native_top_anchor(changed, 't').XCoordinate)
            self.assertEqual(native_top_anchor(changed, 't'+SUFFIX).XCoordinate,
                             native_top_anchor(original, 't').XCoordinate)
            def cap(font):
                points = list(font['glyf']['t'].coordinates)
                top = max(y for x, y in points)
                xs = [x for x, y in points if y == top]
                return (min(xs)+max(xs))/2
            delta = round(cap(changed)-cap(original))
            self.assertEqual(native_top_anchor(changed, 't').XCoordinate,
                             native_top_anchor(original, 't').XCoordinate+delta)
            expected, actual = shape(before, 't\u0301'), shape(after, 't\u0301')
            self.assertEqual(len(expected), 2)
            self.assertLess(actual[1][2], expected[1][2])


if __name__ == '__main__':
    unittest.main()
