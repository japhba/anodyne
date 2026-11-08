#!/usr/bin/env python3
"""Restore canonical native Italic zero condensation after an import-only bug.

The cold generator already prioritizes NativeZeroSources. An earlier narrow
math-letter migration omitted that dispatch rule. This fourth, explicit source
migration restores only its12 Italic condensed corners and affected layout;
compiler inputs and every Roman source/cache remain unchanged.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil

from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools.varLib.instancer import instantiateVariableFont

import build
from greek_positioning import extend_greek_mark_anchors
from master_grid import graded, quantize, write_outlines
from migrate_math_letters import component_parents
from migrate_sign_widths import (digest, outline_value, check_patched_glifs,
                                 verify_unaffected, verify_unaffected_math, verify_gpos)
import pipeline
from source_patch import patch_ufoz
from zero import NativeZeroSources

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'build/masters-0.500-mathletters'
CANDIDATE = ROOT / 'build/masters-0.500-zero-corrected'
NEW_TTFS = ROOT / 'build/master-grid-0.500-zero-corrected/Italic'


def preflight():
    manifest = json.loads((BASELINE / 'preparation.json').read_text())
    if pipeline.prepared_source_hashes(BASELINE) != manifest['source_files']:
        raise RuntimeError('Previous source candidate changed after its validated migration')
    inputs = pipeline.signature()
    compiler = pipeline.compiler_fingerprint()
    if pipeline.effective_preparation_inputs(manifest) != inputs:
        raise RuntimeError('This correction must not change any compiler input signature')
    roman_cache = json.loads((ROOT / 'build/compiled/Anodyne-Roman.cache.json').read_text())
    if roman_cache['inputs']['compiler_sources'] != compiler:
        raise RuntimeError('Roman cached compiler fingerprint differs from the unchanged current compiler')
    utilities = {name: digest(ROOT / 'sources' / name) for name in
                 ('migrate_italic_zeros.py', 'migrate_math_letters.py', 'migrate_sign_widths.py', 'source_patch.py')}
    previous_report = json.loads((BASELINE / 'math-letter-Italic.json').read_text())
    current_ttf_hashes = {}
    for row in previous_report['masters']:
        if '-62.5-' not in row['master']:
            continue
        path = ROOT / 'build/master-grid-0.500-mathletters/Italic' / (row['master'] + '.ttf')
        if digest(path) != row['ttf_sha256']:
            raise RuntimeError(f'Validated previous master TTF changed: {path}')
        current_ttf_hashes[str(path)] = row['ttf_sha256']
    original_report = json.loads((BASELINE / 'migration-Italic.json').read_text())
    default_hash = next(row['ttf_sha256'] for row in original_report['masters'] if row['master'] == 'Italic-400-100-0')
    default_path = ROOT / 'build/master-grid-0.500/Italic/Italic-400-100-0.ttf'
    if digest(default_path) != default_hash:
        raise RuntimeError('Retained Default400 reference TTF changed')
    canonical_project = ROOT / 'build/masters-0.500-signs'
    canonical_manifest = json.loads((canonical_project / 'preparation.json').read_text())
    if pipeline.prepared_source_hashes(canonical_project) != canonical_manifest['source_files']:
        raise RuntimeError('Retained native-zero source project has unrecorded edits')
    canonical_report = json.loads((canonical_project / 'sign-width-Italic.json').read_text())
    canonical_ttf_hashes = {row['master']: row['ttf_sha256_after'] for row in canonical_report['masters']}
    native_path = ROOT / 'src/noto/NotoSans-Italic[wdth,wght].ttf'
    noto = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 100, 'wght': w}) for w in build.WEIGHTS}
    narrow = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 62.5, 'wght': w}) for w in build.WEIGHTS}
    zero = NativeZeroSources(noto, narrow, TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf'), True,
                            TTFont(ROOT / 'src/noto/NotoSans[wdth,wght].ttf'))
    anchors = {w: {name: quantize(zero.condensed(name, w)) for name in zero.names} for w in build.WEIGHTS}
    checked, source_hashes = 0, {}
    for weight in build.WEIGHTS:
        for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
            name = f'Italic-{weight}-62.5-{grade}'
            path = ROOT / 'build/master-grid-0.500-signs/Italic' / (name + '.ttf')
            if digest(path) != canonical_ttf_hashes[name]:
                raise RuntimeError(f'Retained canonical zero master TTF changed: {name}')
            expected = anchors[weight] if grade == 0 else {g: quantize(o) for g, o in graded(anchors, weight, grade)}
            with TTFont(path) as gold:
                for glyph, drawing in expected.items():
                    if outline_value(build.read(gold, glyph)) != outline_value(drawing):
                        raise RuntimeError(f'Canonical NativeZero preflight differs from retained native master: {name}/{glyph}')
                    if grade == 0 and glyph in zero.text_names:
                        if outline_value(drawing) != outline_value(quantize(build.read(narrow[weight], glyph))):
                            raise RuntimeError(f'Text zero differs from pinned native Noto: {name}/{glyph}')
                    checked += 1
            source_hashes[str(path)] = digest(path)
    if inputs != pipeline.signature() or compiler != pipeline.compiler_fingerprint():
        raise RuntimeError('Compiler inputs changed during the native-zero preflight')
    if any(digest(ROOT / 'sources' / name) != value for name, value in utilities.items()):
        raise RuntimeError('Migration/validation utility changed during native-zero preflight')
    report = {'status': 'passed', 'inputs': inputs, 'zero_names': list(zero.names),
              'compiler_fingerprint': compiler,
              'native_text_names': list(zero.text_names), 'canonical_glyph_corners_checked': checked,
              'text_zero_weight_width_corners_checked': 4 * len(zero.text_names),
              'retained_canonical_ttf_sha256': source_hashes,
              'validated_current_ttf_sha256': current_ttf_hashes,
              'default_reference_ttf_sha256': default_hash,
              'utility_sha256': utilities,
              'scope': 'All11 Italic text/math optical zero drawings in every condensed weight/grade corner match the cold NativeZero-first model;36 grade0 text forms match pinned Noto exactly.',
              'compiler_signature_unchanged': True}
    path = ROOT / 'build/500-native-zero-correction-preflight.json'
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'Native zero preflight passed: {checked} canonical glyph corners; all36 native text corners exact.', flush=True)
    return manifest, zero, anchors, noto, narrow, report


def main():
    manifest, zero, anchors, noto, narrow, proof = preflight()
    if CANDIDATE.exists():
        raise RuntimeError('Preserve the previous correction candidate before rerunning')
    before_sources = pipeline.prepared_source_hashes(BASELINE)
    overrides = pipeline.source_digest(ROOT / 'sources/overrides')
    signature = pipeline.signature()
    shutil.copytree(BASELINE, CANDIDATE)
    default_path = ROOT / 'build/master-grid-0.500/Italic/Italic-400-100-0.ttf'
    reference = TTFont(default_path)
    affected = component_parents(reference, set(zero.names))
    results, paths = [], []
    NEW_TTFS.mkdir(parents=True, exist_ok=True)
    for weight in build.WEIGHTS:
        for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
            name = f'Italic-{weight}-62.5-{grade}'
            source_ttf = ROOT / 'build/master-grid-0.500-mathletters/Italic' / (name + '.ttf')
            before, font = TTFont(source_ttf), TTFont(source_ttf)
            drawings = anchors[weight] if grade == 0 else {g: quantize(o) for g, o in graded(anchors, weight, grade)}
            write_outlines(font, drawings)
            # Ancestors' drawing data can stay identical while their child's
            # bounds change. Normalize their final LSBs before point rendering.
            for glyph in affected:
                outline = font['glyf'][glyph]
                outline.recalcBounds(font['glyf'])
                advance, _ = font['hmtx'][glyph]
                font['hmtx'][glyph] = advance, outline.xMin if outline.numberOfContours else 0
            font['GPOS'] = copy.deepcopy(reference['GPOS'])
            scale = sum(narrow[weight]['hmtx'][g][0] / noto[weight]['hmtx'][g][0] for g in 'nohdeasu') / 8
            build.position_master(font, reference, narrow[weight], scale)
            build.refresh_math_metrics(font, reference)
            extend_greek_mark_anchors(font)
            reorderGlyphs(font, font.getGlyphOrder())
            font['maxp'].recalc(font)
            checked = verify_unaffected(before, font, affected)
            mark_count = verify_gpos(before, font, narrow[weight], affected)
            math_count = verify_unaffected_math(before, font, affected)
            for tag in ('GSUB', 'GDEF'):
                if before.getTableData(tag) != font.getTableData(tag):
                    raise RuntimeError(f'{name}: unrelated {tag} changed')
            for glyph, expected in drawings.items():
                if outline_value(build.read(font, glyph)) != outline_value(expected):
                    raise RuntimeError('Final corrected frame differs from its canonical zero model')
            changed = sorted(g for g in zero.names if outline_value(build.read(before, g)) != outline_value(build.read(font, g)))
            destination_ttf = NEW_TTFS / (name + '.ttf')
            font.save(destination_ttf)
            source, destination = BASELINE / 'Italic' / (name + '.ufoz'), CANDIDATE / 'Italic' / (name + '.ufoz')
            members = patch_ufoz(source, destination, font, changed)
            check_patched_glifs(destination, font, set(zero.names))
            results.append({'master': name, 'changed_zero_drawings': changed,
                            'source_sha256_before': digest(source), 'source_sha256_after': digest(destination),
                            'ttf_sha256': digest(destination_ttf), 'changed_zip_members': members,
                            'unrelated_rendered_glyphs_verified': checked, 'unrelated_math_records_verified': math_count,
                            'affected_native_anchors_verified': mark_count,
                            'other_gpos_fields_exact': True, 'gsub_gdef_byte_exact': True})
            paths.append(destination_ttf)
            before.close(); font.close()
            print(f'{name}: canonical native zeros restored; {checked} unrelated rendered glyphs/advances exact.', flush=True)
    paths.extend(ROOT / 'build/master-grid-0.500-mathletters/Italic' / f'Italic-{w}-100-{g}.ttf'
                 for w in build.WEIGHTS for g in (0, build.GRAD_MIN, build.GRAD_MAX)
                 if (w, g) != (400, 0))
    paths.append(default_path)
    build.validate_master_compatibility(paths)
    if (pipeline.signature() != signature or pipeline.compiler_fingerprint() != proof['compiler_fingerprint']
            or pipeline.prepared_source_hashes(BASELINE) != before_sources):
        raise RuntimeError('Compiler inputs or preserved source baseline changed during correction')
    if pipeline.source_digest(ROOT / 'sources/overrides') != overrides:
        raise RuntimeError('Tracked topology overrides changed during correction')
    if any(digest(ROOT / 'sources' / name) != value for name, value in proof['utility_sha256'].items()):
        raise RuntimeError('Migration/validation utility changed during correction')
    for path, expected in proof['validated_current_ttf_sha256'].items():
        if digest(path) != expected:
            raise RuntimeError('Previous master TTF changed during correction')
    for path, expected in proof['retained_canonical_ttf_sha256'].items():
        if digest(path) != expected:
            raise RuntimeError('Retained canonical zero TTF changed during correction')
    if digest(default_path) != proof['default_reference_ttf_sha256']:
        raise RuntimeError('Default reference TTF changed during correction')
    after_sources = pipeline.prepared_source_hashes(CANDIDATE)
    changed_sources = {name for name in before_sources if before_sources[name] != after_sources[name]}
    expected_sources = {f'Italic/Italic-{w}-62.5-{g}.ufoz' for w in build.WEIGHTS for g in (0, build.GRAD_MIN, build.GRAD_MAX)}
    if changed_sources != expected_sources:
        raise RuntimeError('Correction changed sources outside exactly12 Italic condensed masters')
    report = {'status': 'passed', 'inputs': signature, 'preflight': proof, 'masters': results,
              'affected_zero_and_rendered_component_closure': sorted(affected),
              'changed_source_files': sorted(changed_sources), 'unchanged_source_files': 42,
              'tracked_overrides_sha256': overrides, 'driver_sha256': digest(__file__),
              'cause': 'An incremental math-letter migration omitted the existing cold generator NativeZeroSources.condensed priority for semantically reachable zero variants.',
              'correction': 'Migration3 dispatch now applies that priority; only actual zero source geometry/layout is restored. All compiler modules/signatures are unchanged.'}
    report_path = ROOT / 'build/500-native-zero-source-correction.json'
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    pipeline.record_source_migration(CANDIDATE, BASELINE,
        description='Restore canonical NativeZero-first condensed drawings after an incremental-import dispatch error. Only12 Italic condensed sources/layout sidecars change; compiler signature, all Roman sources, default faces, references and tracked overrides stay exact.',
        verification={'status': 'passed', 'native_zero_correction': report, 'compiler_signature_unchanged': True,
                      'tracked_overrides_before': overrides, 'tracked_overrides_after': overrides},
        evidence_files=[ROOT / 'build/500-native-zero-correction-preflight.json', report_path,
                        ROOT / 'sources/migrate_italic_zeros.py', ROOT / 'sources/migrate_math_letters.py'])
    final = json.loads((CANDIDATE / 'preparation.json').read_text())
    if pipeline.effective_preparation_inputs(final) != signature or final['source_files'] != after_sources:
        raise RuntimeError('Corrected source ledger does not match unchanged generator/current source hashes')
    print('Fourth source migration passed; allRoman/default/reference sources and compiler inputs unchanged.', flush=True)


if __name__ == '__main__':
    main()
