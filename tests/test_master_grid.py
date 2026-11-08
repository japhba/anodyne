"""The persisted-anchor and cold-import grid use one geometry contract."""
from pathlib import Path
import sys
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sources'))
import build
from master_grid import graded, normalize_monospace, quantize, write_outlines


def rectangle(left, right, advance=680):
    return build.Outline([[(left, 0, True), (left, 700, True),
                           (right, 700, True), (right, 0, True)]], adv=advance)


def fixture():
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', 'parent', 'child', 'mono', 'mono.alt', 'digit'])
    builder.setupCharacterMap({0x1D670: 'mono', 0x1D7F6: 'digit'})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in builder.font.getGlyphOrder()})
    builder.setupHorizontalMetrics({name: (680, 0) for name in builder.font.getGlyphOrder()})
    return builder.font


class MasterGridTests(unittest.TestCase):
    def test_quantized_advance_matches_persisted_writer_for_negative_marks(self):
        for advance in (-62.4, -.6, 0, 500.5):
            drawing = rectangle(20, 60, advance)
            font = fixture()
            build.write(font, 'mono', drawing)
            self.assertEqual(quantize(drawing).adv, font['hmtx']['mono'][0])
        self.assertEqual(quantize(rectangle(20, 60, -62.4)).adv, 0)

    def test_final_component_lsb_uses_updated_children(self):
        font = fixture()
        build.write(font, 'child', rectangle(10, 50))
        drawings = {'parent': build.Outline(components=[('child', 30, 0, None)], adv=680),
                    'child': rectangle(100, 150)}
        write_outlines(font, drawings)
        self.assertEqual(font['glyf']['parent'].xMin, 130)
        self.assertEqual(font['hmtx']['parent'][1], 130)
        points = RecordingPointPen()
        font.getGlyphSet()['parent'].drawPoints(points)
        component = next(args for operation, args, _ in points.value if operation == 'addComponent')
        self.assertEqual(component[1][-2:], (30, 0), 'No stale LSB translation may move the component')

    def test_mono_cell_is_fixed_and_black_fit_preserves_height_and_topology(self):
        font = fixture()
        normal = {weight: {'mono': rectangle(-20, 800, 783), 'digit': rectangle(80, 520, 600)}
                  for weight in build.WEIGHTS}
        report = normalize_monospace(normal, font)
        self.assertEqual(len(report), 8)
        for drawings in normal.values():
            for name, outline in drawings.items():
                self.assertEqual(outline.adv, 680)
                self.assertEqual(build.bbox(outline.contours)[1::2], (0, 700))
                self.assertEqual(build.structure(outline), build.structure(rectangle(0, 1)))
            self.assertEqual(build.bbox(drawings['mono'].contours), (8, 0, 672, 700))
            self.assertEqual(build.bbox(drawings['digit'].contours), (120, 0, 560, 700))

    def test_integer_persisted_anchors_derive_identical_grade_drawings(self):
        raw = {weight: {'mono': rectangle(20.25, 55.75 + weight / 10, 680.2)}
               for weight in build.WEIGHTS}
        cold = {w: {g: quantize(o) for g, o in drawings.items()} for w, drawings in raw.items()}
        persisted = {}
        for weight in build.WEIGHTS:
            font = fixture()
            write_outlines(font, raw[weight])
            persisted[weight] = {'mono': build.read(font, 'mono')}
        for weight in build.WEIGHTS:
            for grade in (-100, 0, 150):
                a = {g: quantize(o) for g, o in graded(cold, weight, grade)}
                b = {g: quantize(o) for g, o in graded(persisted, weight, grade)}
                self.assertEqual(a['mono'].contours, b['mono'].contours)
                self.assertEqual(a['mono'].adv, 680)


if __name__ == '__main__':
    unittest.main()
