"""Migrated sources retain their original preparation and auditable hash chain."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fontTools.designspaceLib import DesignSpaceDocument, SourceDescriptor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
import pipeline


class SourceMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'sources/overrides').mkdir(parents=True)
        (self.root / 'sources/build.py').write_text('changed generator\n')
        self.original, self.candidate = self.root / 'original', self.root / 'candidate'
        for folder in (self.original, self.candidate):
            for style in ('Roman', 'Italic'):
                location = folder / style
                location.mkdir(parents=True)
                document = DesignSpaceDocument()
                for index in range(24):
                    path = location / f'{style}-{index:02d}.ufoz'
                    path.write_bytes(f'{folder.name} compatible source {index}'.encode())
                    source = SourceDescriptor()
                    source.name, source.path = path.stem, str(path)
                    document.addSource(source)
                document.write(location / f'Anodyne-{style}.designspace')
                (location / 'math').mkdir()
                for name in ('Regular', 'Bold'):
                    (location / 'math' / f'{name}.ufoz').write_bytes(b'math reference')
        self.previous = {'schema': 1, 'inputs': {'build.py': hashlib.sha256(b'old generator').hexdigest()},
                         'source_files': pipeline.prepared_source_hashes(self.original)}
        (self.original / 'preparation.json').write_text(json.dumps(self.previous))
        self.snapshot = self.root / 'baseline.json'
        self.snapshot.write_text(json.dumps({'source_root': str(self.original), 'prepared_manifest': self.previous,
                                            'override_sha256': pipeline.source_digest(self.root / 'sources/overrides')}))
        self.evidence = self.root / 'validation.json'
        self.evidence.write_text(json.dumps({'status': 'passed', 'compatible_masters': 48}))
        self.root_patch = patch.object(pipeline, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.directory.cleanup()

    def record(self):
        return pipeline.record_source_migration(self.candidate, self.snapshot,
            description='Shared-grid zero and width migration with preserved anchors',
            verification={'status': 'passed', 'compatible_masters': 48},
            evidence_files=[self.evidence])

    def test_record_retains_origin_and_allows_current_migrated_build(self):
        result = self.record()
        self.assertEqual(result['inputs'], self.previous['inputs'])
        self.assertEqual(result['origin_source_files'], self.previous['source_files'])
        self.assertEqual(pipeline.effective_preparation_inputs(result), pipeline.signature())
        self.assertEqual(pipeline.prepared_source_hashes(self.original), self.previous['source_files'])
        migration = result['source_migrations'][0]
        for name, digest in migration['evidence_files'].items():
            self.assertTrue((self.candidate / name).is_file())
            self.assertEqual(digest, pipeline.source_digest(self.candidate / name))
        with patch('fetch_sources.fetch') as fetch:
            pipeline.prepare(self.candidate)
            fetch.assert_not_called()

    def test_unrecorded_original_edits_are_preserved_and_rejected(self):
        source = self.original / 'Roman/Roman-00.ufoz'
        source.write_bytes(b'hand-edited source')
        with self.assertRaisesRegex(RuntimeError, 'unrecorded edits'):
            self.record()
        self.assertEqual(source.read_bytes(), b'hand-edited source')

    def test_stale_external_candidate_references_are_rejected(self):
        path = self.candidate / 'Roman/Anodyne-Roman.designspace'
        document = DesignSpaceDocument.fromfile(path)
        document.sources[0].path = str(self.original / 'Roman/Roman-00.ufoz')
        document.write(path)
        with self.assertRaisesRegex(RuntimeError, 'outside its source project'):
            self.record()

    def test_broken_migration_chain_is_rejected(self):
        result = self.record()
        broken = copy.deepcopy(result)
        broken['source_migrations'][0]['from_inputs'] = {'build.py': 'wrong predecessor'}
        with self.assertRaisesRegex(RuntimeError, 'continuous'):
            pipeline.effective_preparation_inputs(broken)
        broken = copy.deepcopy(result)
        broken['source_files']['Roman/Roman-00.ufoz'] = 'wrong final checksum'
        with self.assertRaisesRegex(RuntimeError, 'differs from its migration history'):
            pipeline.effective_preparation_inputs(broken)

    def test_in_place_migration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'separate candidate'):
            pipeline.record_source_migration(self.original, self.snapshot,
                description='in place', verification={'status': 'passed'})


if __name__ == '__main__':
    unittest.main()
