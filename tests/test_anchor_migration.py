"""Only the explicitly recorded topology repairs may enter an anchor migration."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from ufoLib2 import Font
from test_master_grid import fixture, rectangle
import build
from migrate_sources import REPAIRS, apply_anchor_repairs, validate_advance_clamp_audit


class AnchorMigrationTests(unittest.TestCase):
    def test_clamp_audit_does_not_allow_other_fingerprint_changes(self):
        before = {'master_grid.py': 'old', 'build.py': 'before'}
        after = {'master_grid.py': 'new', 'build.py': 'after'}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'audit.json'
            path.write_text(json.dumps({'kind': 'nonnegative-advance-clamp', 'status': 'passed',
                                        'input_signature_before': before, 'input_signature_after': after}))
            with patch('migrate_sources.pipeline.signature', return_value=after):
                with self.assertRaisesRegex(RuntimeError, 'exact single-field signature change'):
                    validate_advance_clamp_audit(path, [{'inputs': before}], Path(temporary))

    def test_clamp_audit_rejects_unrelated_master_grid_edits(self):
        before, after = {'master_grid.py': 'old'}, {'master_grid.py': 'new'}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'audit.json'
            old_source = Path(temporary) / 'old.py'
            old_source.write_text('unrelated source change\n')
            path.write_text(json.dumps({'kind': 'nonnegative-advance-clamp', 'status': 'passed',
                                        'input_signature_before': before, 'input_signature_after': after,
                                        'old_master_grid_source': str(old_source)}))
            with patch('migrate_sources.pipeline.signature', return_value=after):
                with self.assertRaisesRegex(RuntimeError, 'more than the approved advance clamp'):
                    validate_advance_clamp_audit(path, [{'inputs': before}], Path(temporary))

    def test_unknown_user_override_is_rejected_before_font_changes(self):
        font = fixture()
        before = build.read(font, 'mono').adv
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'partial.ufo'
            source = Font()
            source.newGlyph('mono').width = 999
            source.save(path)
            with self.assertRaisesRegex(RuntimeError, 'additional edited override glyphs'):
                apply_anchor_repairs(font, path)
        self.assertEqual(build.read(font, 'mono').adv, before)

    def test_recorded_repair_drawings_replace_raw_anchor_coordinates(self):
        font = fixture()
        font.setGlyphOrder(font.getGlyphOrder() + sorted(REPAIRS))
        for name in REPAIRS:
            build.write(font, name, rectangle(10, 80, 500))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'partial.ufo'
            source = Font()
            for name in REPAIRS:
                glyph = source.newGlyph(name)
                pen = glyph.getPen()
                pen.moveTo((42, 0)); pen.lineTo((42, 700))
                pen.lineTo((180, 700)); pen.lineTo((180, 0)); pen.closePath()
                glyph.width = 600
            source.save(path)
            apply_anchor_repairs(font, path)
        for name in REPAIRS:
            actual = build.read(font, name)
            self.assertEqual(actual.contours, rectangle(42, 180, 600).contours)
            self.assertEqual(actual.adv, 600)


if __name__ == '__main__':
    unittest.main()
