"""Incremental operator changes cannot silently change unrelated layout."""
import copy
from pathlib import Path
import tempfile
import unittest

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib.builder import buildAnchor, buildLookup, buildMarkBasePosSubtable
from test_core_engineering import font_master
import build
from migrate_sign_widths import verify_gpos, verify_unaffected_math


class SignMigrationTests(unittest.TestCase):
    def font(self, directory):
        path = Path(directory) / 'master.ttf'
        font_master(path, 30, 300, -40)
        return TTFont(path)

    def test_extension_wrapper_is_transparent_to_strict_positioning_check(self):
        with tempfile.TemporaryDirectory() as directory:
            before = self.font(directory)
            after = copy.deepcopy(before)
            lookup = after['GPOS'].table.LookupList.Lookup[0]
            wrapper = ot.ExtensionPos()
            wrapper.Format = 1
            wrapper.ExtensionLookupType = lookup.LookupType
            wrapper.ExtSubTable = lookup.SubTable[0]
            lookup.LookupType = 9
            lookup.SubTable = [wrapper]
            self.assertEqual(verify_gpos(before, after, before, set()), 0)

    def test_unrelated_pair_scaling_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            before = self.font(directory)
            after = copy.deepcopy(before)
            after['GPOS'].table.LookupList.Lookup[0].SubTable[0].PairSet[0].PairValueRecord[0].Value1.XAdvance = -20
            with self.assertRaisesRegex(RuntimeError, 'Unrelated GPOS field'):
                verify_gpos(before, after, before, set())

    def test_affected_anchor_must_match_geometry_and_keep_format_and_marks(self):
        with tempfile.TemporaryDirectory() as directory:
            before = self.font(directory)
            subtable = buildMarkBasePosSubtable({'x': (0, buildAnchor(0, 0))},
                                               {'H': {0: buildAnchor(250, 700)}},
                                               before.getReverseGlyphMap())
            before['GPOS'].table.LookupList.Lookup.append(buildLookup([subtable]))
            before['GPOS'].table.LookupList.LookupCount = 2
            after = copy.deepcopy(before)
            build.write(after, 'H', build.Outline([[(50, 0, True), (50, 700, True),
                                                   (250, 700, True), (250, 0, True)]], adv=500))
            target = after['GPOS'].table.LookupList.Lookup[1].SubTable[0]
            anchor = target.BaseArray.BaseRecord[0].BaseAnchor[0]
            anchor.XCoordinate = 150
            self.assertEqual(verify_gpos(before, after, before, {'H'}), 1)
            anchor.XCoordinate = 151
            with self.assertRaisesRegex(RuntimeError, 'native-master geometry remap'):
                verify_gpos(before, after, before, {'H'})
            anchor.XCoordinate = 150
            anchor.Format, anchor.AnchorPoint = 2, 1
            with self.assertRaisesRegex(RuntimeError, 'Unrelated GPOS field'):
                verify_gpos(before, after, before, {'H'})

    def test_only_affected_math_attachment_changes_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            before = self.font(directory)
            after = copy.deepcopy(before)
            after['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment[0].Value += 50
            with self.assertRaisesRegex(RuntimeError, 'Unrelated MATH record'):
                verify_unaffected_math(before, after, set())
            self.assertGreater(verify_unaffected_math(before, after, {'x'}), 0)


if __name__ == '__main__':
    unittest.main()
