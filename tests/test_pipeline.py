"""Regression tests for editable source roundtrips and isolated math instances."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json
import os

from fontTools import subset
from fontTools.ttLib import TTFont
from ufoLib2 import Font

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path(os.environ.get('ANODYNE_FONTS', ROOT / 'fonts'))
sys.path.insert(0, str(ROOT / 'sources'))
import masters
import fetch_sources
import pipeline
from instance import create_instance


class EditableSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = TTFont(FONTS / 'static/Anodyne-Regular.ttf')
        options = subset.Options()
        options.notdef_outline = True
        options.layout_features = ['kern', 'mark', 'mkmk']
        tool = subset.Subsetter(options)
        tool.populate(glyphs=['.notdef', 'space', 'H', 'o', 'acutecomb'])
        tool.subset(cls.font)

    def test_roundtrip_preserves_curves_advances_and_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'master.ufoz'
            masters.export_font(copy.deepcopy(self.font), path)
            rebuilt = masters.compile_font(path)
            self.assertEqual(self.font.getGlyphOrder(), rebuilt.getGlyphOrder())
            for name in self.font.getGlyphOrder():
                before = self.font['glyf'][name].getCoordinates(self.font['glyf'])
                after = rebuilt['glyf'][name].getCoordinates(rebuilt['glyf'])
                self.assertEqual(before[0], after[0])
                self.assertEqual(list(before[1]), list(after[1]))
                self.assertEqual([f & 1 for f in before[2]], [f & 1 for f in after[2]])
                self.assertEqual(self.font['hmtx'][name], rebuilt['hmtx'][name])
            for tag in ('GPOS', 'GSUB', 'GDEF', 'MATH'):
                if tag in self.font:
                    self.assertEqual(self.font.getTableData(tag), rebuilt.getTableData(tag))

    def test_directory_source_and_tracked_override_are_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'master.ufoz'
            masters.export_font(copy.deepcopy(self.font), path)
            with Font.open(path, lazy=False) as source:
                editable = Path(directory) / 'master.ufo'
                source['H'].width += 17
                source.save(editable)
                override = Font()
                override.layers.defaultLayer['H'] = copy.deepcopy(source['H'])
                override['H'].width += 23
                override_path = Path(directory) / 'override.ufo'
                override.save(override_path)
            rebuilt = masters.compile_font(editable, override_path)
            self.assertEqual(rebuilt['hmtx']['H'][0], self.font['hmtx']['H'][0] + 40)
            self.assertEqual(rebuilt['hmtx']['o'], self.font['hmtx']['o'])

    def test_source_archive_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'master.ufoz'
            masters.export_font(copy.deepcopy(self.font), path)
            first = hashlib.sha256(path.read_bytes()).digest()
            masters.export_font(copy.deepcopy(self.font), path)
            self.assertEqual(first, hashlib.sha256(path.read_bytes()).digest())


class InstanceTests(unittest.TestCase):
    def test_arbitrary_instance_is_static_math_and_does_not_mutate_source(self):
        source = TTFont(FONTS / 'variable/Anodyne[GRAD,wdth,wght].ttf')
        font = create_instance(source, weight=550, width=75, grade=50)
        self.assertIn('fvar', source)
        self.assertNotIn('fvar', font)
        self.assertIn('MATH', font)
        self.assertEqual(font['name'].getDebugName(6), 'Anodyne-w550-wd75-g50')

    def test_woff2_input_produces_real_ttf(self):
        with tempfile.TemporaryDirectory() as directory:
            source = TTFont(FONTS / 'variable/Anodyne[GRAD,wdth,wght].ttf')
            source.flavor = 'woff2'
            output = Path(directory) / 'instance.ttf'
            create_instance(source, output=output)
            self.assertEqual(output.read_bytes()[:4], b'\x00\x01\x00\x00')

    def test_invalid_axes_are_rejected(self):
        with self.assertRaises(ValueError):
            create_instance(FONTS / 'variable/Anodyne[GRAD,wdth,wght].ttf', weight=99)


class SourceLockTests(unittest.TestCase):
    def test_prepared_source_build_does_not_fetch_upstream_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'preparation.json').write_text(json.dumps({'inputs': {'generator': 'same'}}))
            with patch.object(fetch_sources, 'fetch') as fetch, patch.object(pipeline, 'signature', return_value={'generator': 'same'}):
                pipeline.prepare(folder)
                fetch.assert_not_called()

    def test_altered_cached_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.ttf'
            source.write_bytes(b'pinned-input')
            lock = root / 'lock.json'
            lock.write_text(json.dumps({'files': [{'path': 'input.ttf',
                'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]}))
            with patch.object(fetch_sources, 'LOCK', lock):
                fetch_sources.fetch(root, verify_only=True)
                source.write_bytes(b'changed-input')
                with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                    fetch_sources.fetch(root, verify_only=True)

    def test_regeneration_refuses_to_overwrite_edited_packed_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'master.ufoz'
            source.write_bytes(b'original-master')
            manifest = {'inputs': {'generator': 'old'},
                        'source_files': pipeline.prepared_source_hashes(folder)}
            (folder / 'preparation.json').write_text(json.dumps(manifest))
            source.write_bytes(b'edited-master')
            with patch.object(fetch_sources, 'fetch'), patch.object(pipeline, 'signature', return_value={'generator': 'new'}):
                with self.assertRaisesRegex(RuntimeError, 'already exist'):
                    pipeline.prepare(folder)
                with self.assertRaisesRegex(RuntimeError, 'have been edited'):
                    pipeline.prepare(folder, force=True)
            self.assertEqual(source.read_bytes(), b'edited-master')


if __name__ == '__main__':
    unittest.main()
