#!/usr/bin/env python3
"""Preserve responsive native compound glyphs during width derivation.

This source-only migration applies the corrected cold import classification to
retained integer anchors. It preserves every child drawing, normal-width face,
reference, feature table and tracked topology override, and records its exact
source and compiler transition before fresh variable-font compilation.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools.varLib.instancer import instantiateVariableFont

import build
from greek_positioning import extend_greek_mark_anchors
from master_grid import graded, quantize, write_outlines
import mathletters
from migrate_math_letters import component_parents, condensed_subset
from migrate_sign_widths import (digest, outline_value, native_names,
    check_patched_glifs, verify_unaffected, verify_unaffected_math, verify_gpos)
import pipeline
from source_patch import patch_ufoz
from zero import NativeZeroSources

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'build/masters-0.500-zero-corrected'
CANDIDATE = ROOT / 'build/masters-0.500-native-wrappers'
NEW_TTFS = ROOT / 'build/master-grid-0.500-native-wrappers'
UTILITIES = ('migrate_native_wrappers.py', 'migrate_math_letters.py',
             'migrate_sign_widths.py', 'source_patch.py')


def frame(style, weight, width, grade):
    if (weight, width, grade) == (400, 100, 0):
        folder = 'master-grid-0.500'
    elif style == 'Italic' and width == 62.5:
        folder = 'master-grid-0.500-zero-corrected'
    else:
        folder = 'master-grid-0.500-mathletters'
    return ROOT / 'build' / folder / style / f'{style}-{weight}-{width}-{grade}.ttf'


def prepare():
    manifest = json.loads((BASELINE / 'preparation.json').read_text())
    source_hashes = pipeline.prepared_source_hashes(BASELINE)
    if source_hashes != manifest['source_files'] or CANDIDATE.exists():
        raise RuntimeError('Preserve the exact validated baseline and use a fresh candidate')
    before, after = pipeline.effective_preparation_inputs(manifest), pipeline.signature()
    if {k for k in set(before) | set(after) if before.get(k) != after.get(k)} != {'mathletters.py'}:
        raise RuntimeError('Only flattened native width classification may change the generator')
    compiler = pipeline.compiler_fingerprint()
    for style in ('Roman', 'Italic'):
        cached = json.loads((ROOT / f'build/compiled-source4/Anodyne-{style}.cache.json').read_text())
        old_compiler = cached['inputs']['compiler_sources']
        if {k for k in set(old_compiler) | set(compiler) if old_compiler.get(k) != compiler.get(k)} != {'mathletters.py'}:
            raise RuntimeError('An unrelated compiler module changed')
        if digest(ROOT / 'build/compiled-source4' / cached['output']) != cached['output_sha256']:
            raise RuntimeError('Preserved prior verified VF changed')
    ttf_hashes = {}
    correction = manifest['source_migrations'][-1]['verification']['native_zero_correction']
    zero_rows = {row['master']: row['ttf_sha256'] for row in correction['masters']}
    for style in ('Roman', 'Italic'):
        rows = json.loads((BASELINE / f'math-letter-{style}.json').read_text())['masters']
        hashes = {row['master']: row['ttf_sha256'] for row in rows if 'ttf_sha256' in row}
        original = json.loads((BASELINE / f'migration-{style}.json').read_text())['masters']
        default = f'{style}-400-100-0'
        hashes[default] = next(row['ttf_sha256'] for row in original if row['master'] == default)
        if style == 'Italic':
            hashes.update(zero_rows)
        for weight in build.WEIGHTS:
            for width in (100, 62.5):
                for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
                    path = frame(style, weight, width, grade)
                    if digest(path) != hashes[path.stem]:
                        raise RuntimeError(f'Validated source frame changed: {path}')
                    ttf_hashes[str(path)] = hashes[path.stem]
    state = {'baseline': str(BASELINE), 'source_files': source_hashes,
             'from_inputs': before, 'target_inputs': after, 'compiler_fingerprint': compiler,
             'utility_sha256': {name: digest(ROOT / 'sources' / name) for name in UTILITIES},
             'native_sha256': {name: digest(ROOT / 'src/noto' / name) for name in
                ('NotoSans[wdth,wght].ttf', 'NotoSans-Italic[wdth,wght].ttf', 'NotoSansMath-Regular.ttf')},
             'tracked_overrides_sha256': pipeline.source_digest(ROOT / 'sources/overrides'),
             'validated_frame_sha256': ttf_hashes}
    shutil.copytree(BASELINE, CANDIDATE)
    (CANDIDATE / 'native-wrapper-baseline.json').write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    print('Source4, both verified VFs, all48 frame hashes and utility hashes preserved.', flush=True)


def check_state():
    state = json.loads((CANDIDATE / 'native-wrapper-baseline.json').read_text())
    if pipeline.signature() != state['target_inputs'] or pipeline.compiler_fingerprint() != state['compiler_fingerprint']:
        raise RuntimeError('Generator/compiler changed during the native-wrapper migration')
    if pipeline.prepared_source_hashes(BASELINE) != state['source_files']:
        raise RuntimeError('Preserved baseline source project changed')
    if pipeline.source_digest(ROOT / 'sources/overrides') != state['tracked_overrides_sha256']:
        raise RuntimeError('Tracked topology overrides changed')
    for name, expected in state['utility_sha256'].items():
        if digest(ROOT / 'sources' / name) != expected:
            raise RuntimeError('Migration or validation utility changed')
    for name, expected in state['native_sha256'].items():
        if digest(ROOT / 'src/noto' / name) != expected:
            raise RuntimeError('Pinned native font input changed')
    for path, expected in state['validated_frame_sha256'].items():
        if digest(path) != expected:
            raise RuntimeError('A validated input TTF frame changed')
    return state


def classification(reference, wide, narrow, repaired):
    names = mathletters.semantic_names(reference)
    old_seeds, new_seeds = set(), set()
    for name in names:
        if name not in wide['glyf'] or name not in narrow['glyf']:
            continue
        left, right = build.read(wide, name), build.read(narrow, name)
        if left.contours == right.contours and left.components == right.components:
            old_seeds.add(name)
        if mathletters.native_width_static(wide, narrow, name):
            new_seeds.add(name)
    def closure(seeds):
        current = set(seeds) | set(repaired) | {reference.getBestCmap()[0x2140]}
        edges = mathletters.semantic_edges(reference)
        while True:
            added = {b for a, b in edges if a in current and b in names} - current
            if not added:
                return current
            current.update(added)
    old, new = closure(old_seeds), closure(new_seeds)
    if new - old:
        raise RuntimeError('Flattened comparison unexpectedly introduced new forced glyphs')
    raw_native = native_names(reference, wide)
    previous_native, current_native = raw_native - old, raw_native - new
    if previous_native - current_native:
        raise RuntimeError('An existing native-copy donor was removed')
    return old, new, current_native - previous_native


def assert_native_donors(font, native, zero, italic):
    names = ('H', 'n', 'o', 'e', 'a', 's', 'u', 'uni2139') + tuple(
        digit + suffix for digit in ('zero', 'one', 'two', 'three', 'four', 'five',
                                    'six', 'seven', 'eight', 'nine')
        for suffix in ('', '.lf', '.osf', '.tosf'))
    names = set(names) | set(zero.text_names)
    if italic:
        names.update(('uni210E', 'uni210F'))
    target, source = font.getGlyphSet(), native.getGlyphSet()
    for name in sorted(names):
        pens = [DecomposingRecordingPen(glyphs) for glyphs in (target, source)]
        for glyphs, pen in zip((target, source), pens):
            glyphs[name].draw(pen)
        if [row[0] for row in pens[0].value] != [row[0] for row in pens[1].value]:
            raise RuntimeError(f'Native donor path changed: {name}')
        for (_, left), (_, right) in zip(pens[0].value, pens[1].value):
            if len(left) != len(right):
                raise RuntimeError(f'Native donor topology changed: {name}')
            for a, b in zip(left, right):
                if a is None or b is None:
                    if a != b:
                        raise RuntimeError(f'Native donor curve flags changed: {name}')
                elif max(abs(a[i] - b[i]) for i in (0, 1)) > 1.25:
                    raise RuntimeError(f'Native donor differs from pinned Noto: {name}: {a} vs {b}')
        if abs(target[name].width - source[name].width) > 1.25:
            raise RuntimeError(f'Native donor advance differs from pinned Noto: {name}')
    return len(names)


def normalize_parents(font, names):
    for name in names:
        glyph = font['glyf'][name]
        glyph.recalcBounds(font['glyf'])
        advance, _ = font['hmtx'][name]
        font['hmtx'][name] = advance, glyph.xMin if glyph.numberOfContours else 0


def migrate_style(style):
    state = check_state()
    report_path = CANDIDATE / f'native-wrapper-{style}.json'
    if report_path.exists():
        raise RuntimeError('Preserve an existing completed style report before rerunning')
    reference = TTFont(frame(style, 400, 100, 0))
    native_path = ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if style == 'Italic' else 'NotoSans[wdth,wght].ttf')
    wide = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 100, 'wght': w}) for w in build.WEIGHTS}
    narrow = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 62.5, 'wght': w}) for w in build.WEIGHTS}
    zero = NativeZeroSources(wide, narrow, TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf'), style == 'Italic',
                            TTFont(ROOT / 'src/noto/NotoSans[wdth,wght].ttf') if style == 'Italic' else None)
    previous = json.loads((BASELINE / f'math-letter-{style}.json').read_text())
    old_forced, new_forced, native = classification(reference, wide[400], narrow[400], previous['repaired_weight_names'])
    if old_forced != set(previous['forced_width_names']):
        raise RuntimeError('Historical classification did not reconstruct exactly')
    affected = component_parents(reference, native)
    class RejectGeneric:
        def draw(self, *args):
            raise RuntimeError('A newly restored native donor reached synthetic condensation')
    anchors = condensed_subset({w: {} for w in build.WEIGHTS}, native, native, RejectGeneric(), narrow, zero)
    preflight = []
    for weight in build.WEIGHTS:
        with TTFont(frame(style, weight, 62.5, 0)) as prototype:
            write_outlines(prototype, anchors[weight])
            normalize_parents(prototype, affected)
            checked = assert_native_donors(prototype, narrow[weight], zero, style == 'Italic')
            preflight.append({'weight': weight, 'native_rendered_donors_checked': checked})
    proof = {'status': 'passed', 'style': style, 'old_forced': sorted(old_forced), 'new_forced': sorted(new_forced),
             'native_copy_restored': sorted(native), 'affected_component_closure': sorted(affected),
             'native_donor_checks_before_export': preflight,
             'normal_weight_drawings_and_child_optics_preserved': True}
    (CANDIDATE / f'native-wrapper-preflight-{style}.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
    print(f'{style}: all4 native donor preflights passed before source export; {len(native)} restored native-copy paths.', flush=True)
    results, paths = [], []
    for weight in build.WEIGHTS:
        for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
            name = f'{style}-{weight}-62.5-{grade}'
            input_path = frame(style, weight, 62.5, grade)
            before, font = TTFont(input_path), TTFont(input_path)
            drawings = anchors[weight] if grade == 0 else {g: quantize(o) for g, o in graded(anchors, weight, grade)}
            write_outlines(font, drawings)
            normalize_parents(font, affected)
            changed = sorted(g for g in affected if outline_value(build.read(before, g)) != outline_value(build.read(font, g)))
            # Positioning is always derived from the untouched normal reference.
            font['GPOS'] = copy.deepcopy(reference['GPOS'])
            scale = sum(narrow[weight]['hmtx'][g][0] / wide[weight]['hmtx'][g][0] for g in 'nohdeasu') / 8
            build.position_master(font, reference, narrow[weight], scale)
            build.refresh_math_metrics(font, reference)
            extend_greek_mark_anchors(font)
            reorderGlyphs(font, font.getGlyphOrder())
            font['maxp'].recalc(font)
            protected = set() if style == 'Italic' else affected
            glyph_count = verify_unaffected(before, font, protected)
            anchor_count = verify_gpos(before, font, narrow[weight], protected)
            math_count = verify_unaffected_math(before, font, protected)
            for tag in ('GSUB', 'GDEF'):
                if before.getTableData(tag) != font.getTableData(tag):
                    raise RuntimeError(f'{name}: unrelated {tag} changed')
            for glyph in native:
                if font['hmtx'][glyph][0] != anchors[weight][glyph].adv:
                    raise RuntimeError(f'{name}: restored native advance changes with grade: {glyph}')
            source, destination = BASELINE / style / (name + '.ufoz'), CANDIDATE / style / (name + '.ufoz')
            entries = []
            if style == 'Italic':
                if changed:
                    raise RuntimeError('The independently unchanged Italic geometry changed')
                output_path = input_path
            else:
                output_path = NEW_TTFS / style / (name + '.ttf')
                output_path.parent.mkdir(parents=True, exist_ok=True)
                font.save(output_path)
                entries = patch_ufoz(source, destination, font, changed)
                check_patched_glifs(destination, font, native)
            results.append({'master': name, 'changed_raw_drawings_and_advances': changed,
                'unrelated_rendered_glyphs_verified': glyph_count, 'unrelated_math_records_verified': math_count,
                'affected_native_anchors_verified': anchor_count, 'other_gpos_fields_exact': True,
                'gsub_gdef_byte_exact': True, 'input_ttf': str(input_path), 'input_ttf_sha256': digest(input_path),
                'output_ttf': str(output_path), 'output_ttf_sha256': digest(output_path),
                'source_sha256_before': digest(source), 'source_sha256_after': digest(destination),
                'changed_zip_members': entries})
            paths.append(output_path)
            before.close(); font.close()
            print(f'{name}: {len(changed)} corrected raw drawings/advances; {glyph_count} unrelated glyphs exact.', flush=True)
    paths.extend(frame(style, w, 100, g) for w in build.WEIGHTS for g in (0, build.GRAD_MIN, build.GRAD_MAX))
    build.validate_master_compatibility(paths)
    check_state()
    report = {'status': 'passed', 'style': style, 'inputs': state['target_inputs'], 'preflight': proof,
              'masters': results, 'compatibility_24_masters': 'passed', 'normal_and_reference_sources_unchanged': True}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'{style}: native wrapper source correction and24-master compatibility passed.', flush=True)


def finalize():
    state = check_state()
    reports = [json.loads((CANDIDATE / f'native-wrapper-{style}.json').read_text()) for style in ('Roman', 'Italic')]
    for report in reports:
        if report['status'] != 'passed' or report['inputs'] != state['target_inputs']:
            raise RuntimeError('Both style reports must pass against the current generator')
        for row in report['masters']:
            if digest(CANDIDATE / report['style'] / (row['master'] + '.ufoz')) != row['source_sha256_after']:
                raise RuntimeError('A corrected source changed after validation')
            if digest(row['output_ttf']) != row['output_ttf_sha256']:
                raise RuntimeError('A corrected TTF changed after validation')
    after = pipeline.prepared_source_hashes(CANDIDATE)
    changed = {name for name in state['source_files'] if state['source_files'][name] != after[name]}
    expected = {f'Roman/Roman-{w}-62.5-{g}.ufoz' for w in build.WEIGHTS for g in (0, build.GRAD_MIN, build.GRAD_MAX)}
    if changed != expected:
        raise RuntimeError(f'Only12 Roman condensed source files may change: {sorted(changed)}')
    pipeline.record_source_migration(CANDIDATE, BASELINE,
        description='Detect native width response through transformed component children, restoring native compound-donor condensation instead of unnecessary synthesis. Preserve all normal/reference/Italic sources and inherited optical children. Recompile both styles from the new source/compiler signature.',
        verification={'status': 'passed', 'styles': reports, 'only_roman_12_condensed_sources_changed': True,
                      'preserved_source4_vfs': 'build/compiled-source4', 'no_cache_equivalence_or_rekey': True,
                      'tracked_overrides_before': state['tracked_overrides_sha256'],
                      'tracked_overrides_after': pipeline.source_digest(ROOT / 'sources/overrides')},
        evidence_files=[CANDIDATE / 'native-wrapper-baseline.json',
                        CANDIDATE / 'native-wrapper-preflight-Roman.json', CANDIDATE / 'native-wrapper-preflight-Italic.json',
                        CANDIDATE / 'native-wrapper-Roman.json', CANDIDATE / 'native-wrapper-Italic.json',
                        ROOT / 'sources/migrate_native_wrappers.py', ROOT / 'tests/test_mathletters.py'])
    manifest = json.loads((CANDIDATE / 'preparation.json').read_text())
    if pipeline.effective_preparation_inputs(manifest) != pipeline.signature() or manifest['source_files'] != after:
        raise RuntimeError('Final source ledger does not match actual source/input hashes')
    print('Fifth source ledger validated:12 Roman C sources changed,42 source files exact.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--style', choices=('Roman', 'Italic'))
    group.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.style:
        migrate_style(args.style)
    else:
        finalize()


if __name__ == '__main__':
    main()
