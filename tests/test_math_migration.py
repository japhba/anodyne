"""Native zero handling takes precedence over semantic math forced-width sets."""
import unittest

import test_zero as zero_tests
from master_grid import quantize
from migrate_math_letters import condensed_subset


class RejectGeneric:
    def draw(self, *arguments):
        raise AssertionError('A restored native zero reached generic condensation')


class MathMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        zero_tests.NativeZeroTests.setUpClass()

    def test_all_native_zero_variants_override_forced_width_classification(self):
        for italic, model in zero_tests.NativeZeroTests.models.items():
            normal = model.normal_outlines()
            # An empty native set reproduces the forced-width exclusion that
            # previously sent the Italic zero family through generic drawing.
            actual = condensed_subset(normal, set(model.names), set(), RejectGeneric(), model.noto_c, model)
            for weight, glyphs in actual.items():
                for name, drawing in glyphs.items():
                    expected = quantize(model.condensed(name, weight))
                    with self.subTest(italic=italic, weight=weight, glyph=name):
                        self.assertEqual((drawing.contours, drawing.components, drawing.adv),
                                         (expected.contours, expected.components, expected.adv))


if __name__ == '__main__':
    unittest.main()
