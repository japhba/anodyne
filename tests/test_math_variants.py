"""The browser mapping must preserve real Unicode alphabets and Greek variants."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('math_variants', ROOT / 'sources/build-math-variants.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class MathVariantTests(unittest.TestCase):
    def test_checked_in_mapping_matches_pinned_unicode_generator(self):
        checked_in = json.loads((ROOT / 'assets/math-variants.json').read_text())
        self.assertEqual(checked_in, generator.mapping())
        self.assertEqual(checked_in['unicode_version'], '18.0.0')

    def test_all_styles_letterlike_holes_and_greek_symbols_are_distinct(self):
        styles = generator.mapping()['styles']
        self.assertEqual(len(styles), 13)
        self.assertEqual(''.join(styles['script'][c] for c in 'ABEFHILMR'), '𝒜ℬℰℱℋℐℒℳℛ')
        self.assertEqual(''.join(styles['fraktur'][c] for c in 'CHIRZ'), 'ℭℌℑℜℨ')
        self.assertEqual(''.join(styles['double-struck'][c] for c in 'CHNPQRZ'), 'ℂℍℕℙℚℝℤ')
        self.assertEqual(styles['italic']['h'], 'ℎ')
        self.assertEqual(styles['bold']['α'], '𝛂')
        self.assertEqual(styles['bold']['θ'], '𝛉')
        self.assertEqual(styles['bold']['ϑ'], '𝛝')
        self.assertNotEqual(styles['bold']['θ'], styles['bold']['ϑ'])
        self.assertEqual(styles['monospace']['0'], '𝟶')


if __name__ == '__main__':
    unittest.main()
