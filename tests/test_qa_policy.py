"""Narrow diagnostic exceptions must not mask unrelated release failures."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
from qa import exception_for, summarize
from qa import gpos7_lookups
from types import SimpleNamespace

RULES = json.loads((ROOT / 'sources/qa-policy.json').read_text())['exceptions']


def check(identifier, filename='Anodyne-Italic.ttf'):
    return {'key': [f'<FontBakeryCheck:{identifier}>'], 'filename': filename}


def log(code, message, status='FAIL'):
    return {'status': status, 'message': {'code': code, 'message': message}}


class QAPolicyTests(unittest.TestCase):
    def test_gpos7_check_handles_extensions_without_copying_or_mutating(self):
        extension = SimpleNamespace(ExtensionLookupType=7)
        lookups = [SimpleNamespace(LookupType=2), SimpleNamespace(LookupType=7),
                   SimpleNamespace(LookupType=9, SubTable=[extension])]
        font = {'GPOS': SimpleNamespace(table=SimpleNamespace(LookupList=SimpleNamespace(Lookup=lookups)))}
        self.assertEqual(gpos7_lookups(font), [1, 2])
        self.assertFalse(hasattr(extension, 'LookupType'))
        self.assertFalse(hasattr(extension, 'SubTable'))

    def test_zero_advance_exception_is_limited_to_single_italic_character(self):
        diagnostic = log('zero-width-bases', 'uni2E3C (U+2E3C)')
        self.assertIsNotNone(exception_for(check('base_has_width'), diagnostic, RULES))
        self.assertIsNone(exception_for(check('base_has_width', 'Anodyne-Regular.ttf'), diagnostic, RULES))
        self.assertIsNone(exception_for(check('base_has_width'),
            log('zero-width-bases', 'uni2E3C (U+2E3C), A (U+0041)'), RULES))

    def test_known_case_omission_does_not_excuse_any_other_pair(self):
        self.assertIsNotNone(exception_for(check('case_mapping'),
            log('missing-case-counterparts', 'U+2184 -> U+2183'), RULES))
        self.assertIsNone(exception_for(check('case_mapping'),
            log('missing-case-counterparts', 'U+2184 -> U+2183; U+0061 -> U+0041'), RULES))

    def test_summary_keeps_unrecognized_failures_blocking_and_raw_counts_visible(self):
        entry = check('base_has_width')
        entry['logs'] = [log('zero-width-bases', 'uni2E3C (U+2E3C)'),
                         log('new-failure', 'another issue'), log('warning', 'review this', 'WARN')]
        report = {'result': {'FAIL': 1, 'WARN': 1}, 'sections': [{'checks': [entry]}]}
        result = summarize(report, RULES)
        self.assertEqual(result['raw_counts'], report['result'])
        self.assertEqual(len(result['blocking']), 1)
        self.assertEqual(len(result['accepted_diagnostics']), 1)
        self.assertEqual(len(result['warnings']), 1)


if __name__ == '__main__':
    unittest.main()
