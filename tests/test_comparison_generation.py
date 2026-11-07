"""A failed comparison render must preserve the last complete published catalog."""
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('comparison_generator', ROOT / 'sources/mathfonts/build.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonPublicationTests(unittest.TestCase):
    def test_failed_svg_conversion_retains_previous_images(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            sample, strip = output / 'anodyne.svg', output / 'anodyne-ss02.svg'
            sample.write_text('previous sample')
            strip.write_text('previous alternate')
            with patch.object(comparison, 'OUT', output), \
                 patch.object(comparison, 'bboxes', side_effect=FileNotFoundError('gs')):
                with self.assertRaises(FileNotFoundError):
                    comparison.to_svg({'id': 'anodyne'}, {}, output / 'sample.pdf')
            self.assertEqual(sample.read_text(), 'previous sample')
            self.assertEqual(strip.read_text(), 'previous alternate')
            self.assertEqual(sorted(p.name for p in output.iterdir()), ['anodyne-ss02.svg', 'anodyne.svg'])

    def test_incomplete_catalog_does_not_replace_either_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog, page = root / 'mathfonts.json', root / 'index.html'
            original = json.dumps({'fonts': [{'id': 'anodyne'}, {'id': 'lisnoti'}]})
            catalog.write_text(original)
            page.write_text('previous page')
            with patch.object(comparison, 'JSON_OUT', catalog), patch.object(comparison, 'INDEX', page):
                with self.assertRaisesRegex(RuntimeError, 'retain Anodyne'):
                    comparison.publish_catalog([{'id': 'lisnoti'}], {}, 'replacement')
                with self.assertRaisesRegex(RuntimeError, 'existing comparison fonts'):
                    comparison.publish_catalog([{'id': 'anodyne'}], {}, 'replacement')
                with patch.object(comparison, 'page_text', side_effect=RuntimeError('invalid page data')):
                    with self.assertRaisesRegex(RuntimeError, 'invalid page data'):
                        comparison.publish_catalog([{'id': 'anodyne'}, {'id': 'lisnoti'}], {}, 'replacement')
            self.assertEqual(catalog.read_text(), original)
            self.assertEqual(page.read_text(), 'previous page')

    def test_failed_only_render_never_publishes_the_remaining_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache, output = root / 'cache', root / 'images'
            cache.mkdir()
            output.mkdir()
            info = {'image': {'file': 'images/mathfonts/anodyne.svg'}, 'sets': []}
            (cache / 'state.json').write_text(json.dumps({'anodyne': info}))
            catalog, page = root / 'mathfonts.json', root / 'index.html'
            original = json.dumps({'fonts': [{'id': 'anodyne'}, {'id': 'lisnoti'}]})
            catalog.write_text(original)
            page.write_text('previous page')
            (output / 'anodyne.svg').write_text('previous sample')
            font = Mock()
            font.getBestCmap.return_value = {}
            with patch.object(comparison, 'CACHE', cache), patch.object(comparison, 'OUT', output), \
                 patch.object(comparison, 'WORK', root / 'work'), patch.object(comparison, 'TEXMFVAR', root / 'texmfvar'), \
                 patch.object(comparison, 'JSON_OUT', catalog), patch.object(comparison, 'INDEX', page), \
                 patch.object(comparison, 'FONTS', [{'id': 'anodyne', 'math': 'dummy.ttf'}, {'id': 'latinmodern', 'math': 'dummy.ttf'}]), \
                 patch.object(comparison, 'local_or_cached', return_value=root / 'dummy.ttf'), \
                 patch.object(comparison, 'render', side_effect=FileNotFoundError('gs')), \
                 patch('fontTools.ttLib.TTFont', return_value=font), \
                 patch.object(sys, 'argv', ['build.py', 'render', 'page', '--only', 'anodyne', '--no-systemd']), \
                 redirect_stdout(StringIO()):
                with self.assertRaisesRegex(SystemExit, 'published catalog and page were preserved'):
                    comparison.main()
            self.assertEqual(catalog.read_text(), original)
            self.assertEqual(page.read_text(), 'previous page')
            self.assertEqual((output / 'anodyne.svg').read_text(), 'previous sample')
            self.assertEqual(json.loads((cache / 'state.json').read_text())['anodyne']['image'], info['image'])


if __name__ == '__main__':
    unittest.main()
