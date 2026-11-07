"""Style compilation caches must never hide source or output changes."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, sentinel

from fontTools.designspaceLib import DesignSpaceDocument, SourceDescriptor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import pipeline


class CompileCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'sources/overrides').mkdir(parents=True)
        for name in pipeline.COMPILER_MODULES:
            (self.root / 'sources' / name).write_text('original compiler source\n')
        (self.root / 'requirements.lock').write_text('fonttools==4.68.0\n')
        self.masters = self.root / 'masters'
        self.style = self.masters / 'Roman'
        self.style.mkdir(parents=True)
        self.source = self.style / 'master.ufoz'
        self.source.write_bytes(b'original editable source')
        document = DesignSpaceDocument()
        source = SourceDescriptor()
        source.name, source.path = 'master', str(self.source)
        document.addSource(source)
        document.write(self.style / 'Anodyne-Roman.designspace')
        self.root_patch = patch.object(pipeline, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.directory.cleanup()

    def key(self):
        return pipeline.style_cache_key(pipeline.style_cache_inputs(self.masters))

    def test_source_override_and_compiler_edits_invalidate_key(self):
        original = self.key()
        self.source.write_bytes(b'edited source')
        self.assertNotEqual(self.key(), original)
        self.source.write_bytes(b'original editable source')
        self.assertEqual(self.key(), original)
        overrides = self.root / 'sources/overrides/Roman'
        overrides.mkdir()
        (overrides / 'edited.glif').write_text('<glyph/>')
        self.assertNotEqual(self.key(), original)
        shutil.rmtree(overrides)
        (self.root / 'sources/metadata.py').write_text('changed compiler\n')
        self.assertNotEqual(self.key(), original)

    def test_dependency_changes_invalidate_key(self):
        original = self.key()
        with patch.object(pipeline, 'dependency_versions', return_value={'fonttools': 'future version'}):
            self.assertNotEqual(self.key(), original)

    def test_corrupted_output_is_not_reused(self):
        output = self.root / 'font.ttf'
        output.write_bytes(b'font output')
        cache = self.root / 'cache.json'
        cache.write_text(json.dumps({'key': self.key(), 'output_sha256': pipeline.source_digest(output)}))
        self.assertTrue(pipeline.valid_style_cache(cache, output, self.key()))
        output.write_bytes(b'corrupted output')
        self.assertFalse(pipeline.valid_style_cache(cache, output, self.key()))

    def test_valid_cache_skips_expensive_master_compilation(self):
        flat = self.root / 'compiled'
        flat.mkdir()
        output = flat / 'Anodyne[GRAD,wdth,wght].ttf'
        output.write_bytes(b'font output')
        (flat / 'Anodyne-Roman.cache.json').write_text(json.dumps({
            'key': self.key(), 'output_sha256': pipeline.source_digest(output)}))
        with patch('masters.compile_designspace') as compile_masters, \
                patch('fontTools.ttLib.TTFont', return_value=sentinel.font):
            self.assertIs(pipeline.compile_style(self.masters, flat), sentinel.font)
            compile_masters.assert_not_called()


if __name__ == '__main__':
    unittest.main()
