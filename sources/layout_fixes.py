"""Deterministic source-level layout corrections independent of font geometry."""
from __future__ import annotations

import json
from pathlib import Path

POLICY = Path(__file__).with_name('layout-fixes.json')


def apply_layout_fixes(font, policy_path=POLICY):
    """Select existing clean script glyphs; return the substitutions changed.

    The policy is idempotent and checks the expected old target, so an upstream
    layout update requires review rather than silently receiving a stale patch.
    A font without the affected glyphs is outside this policy's scope.
    """
    policy = json.loads(Path(policy_path).read_text())
    if policy['schema'] != 1:
        raise ValueError('Unsupported Anodyne layout-fix policy schema')
    changes = []
    names = set(font.getGlyphOrder())
    for fix in policy['fixes']:
        if fix['base'] not in names:
            continue
        if fix['replacement'] not in names:
            raise ValueError(f'Layout fix replacement {fix["replacement"]} is absent')
        matched = False
        table = font['GSUB'].table
        for record in table.FeatureList.FeatureRecord:
            if record.FeatureTag != fix['feature']:
                continue
            for index in record.Feature.LookupListIndex:
                for subtable in table.LookupList.Lookup[index].SubTable:
                    subtable = getattr(subtable, 'ExtSubTable', subtable)
                    alternates = getattr(subtable, 'alternates', {}).get(fix['base'])
                    if alternates is None:
                        continue
                    matched = True
                    level = fix['level'] - 1
                    if len(alternates) <= level:
                        raise ValueError(f'{fix["base"]}: missing script alternate {fix["level"]}')
                    actual = alternates[level]
                    if actual == fix['replacement']:
                        continue
                    if actual != fix['expected']:
                        raise ValueError(f'{fix["base"]}: expected {fix["expected"]}, found {actual}; review layout policy')
                    alternates[level] = fix['replacement']
                    changes.append(dict(fix))
        if not matched:
            raise ValueError(f'{fix["base"]}: no {fix["feature"]} alternate lookup found')
    return changes
