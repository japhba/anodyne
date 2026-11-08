#!/usr/bin/env python3
"""Repair frozen mathematical alphabets without repeating contour matching.

Reconstruct the verified integer pre-Greek donors, apply the same repair and
Greek construction as a cold import, then patch only changed source GLIFs and
their layout sidecars. Existing source projects, default Regular, feature/name
metadata and tracked topology overrides are preserved and verified.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import unicodedata

from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools.varLib.instancer import instantiateVariableFont

import build
from condense import Policy
from greek_positioning import extend_greek_mark_anchors
import greekstyles
from master_grid import graded, normalize_monospace, quantize, quantize_anchors, write_outlines
import mathletters
from migrate_sources import apply_anchor_repairs
from migrate_sign_widths import (digest, outline_value, native_names, check_patched_glifs,
                                 verify_unaffected, verify_unaffected_math, verify_gpos)
import pipeline
from source_patch import patch_ufoz
from zero import NativeZeroSources

ROOT = Path(__file__).resolve().parents[1]


def old_ttf(style, weight, width, grade):
    folder = 'master-grid-0.500-signs' if width == 62.5 else 'master-grid-0.500'
    return ROOT / 'build' / folder / style / f'{style}-{weight}-{width}-{grade}.ttf'


def raw_anchors():
    path = ROOT / 'build/normal-anchor-comparison.json'
    data = json.loads(path.read_text())
    if data['status'] != 'passed' or len(data['anchors']) != 8:
        raise RuntimeError('All eight original integer donors require successful source comparison evidence')
    for row in data['anchors']:
        if row['status'] != 'passed' or row['point_stream_mismatches'] or row['missing_glyphs']:
            raise RuntimeError('An original anchor failed its exact source comparison')
        for key in ('raw_ttf', 'ufoz'):
            if digest(row[key]) != row[key + '_sha256']:
                raise RuntimeError(f'Preserved original donor changed: {row[key]}')
    return data


def prepare(baseline, candidate):
    manifest = json.loads((baseline / 'preparation.json').read_text())
    before = pipeline.prepared_source_hashes(baseline)
    if before != manifest['source_files'] or candidate.exists():
        raise RuntimeError('Preserve the validated baseline and use a new migration candidate')
    raw_anchors()
    hashes = {}
    for style in ('Roman', 'Italic'):
        wide = json.loads((baseline / f'migration-{style}.json').read_text())
        narrow = json.loads((baseline / f'sign-width-{style}.json').read_text())
        if wide['status'] != 'passed' or narrow['status'] != 'passed':
            raise RuntimeError('Previous source migrations are incomplete')
        wide_rows = {item['master']: item['ttf_sha256'] for item in wide['masters']}
        hashes[style] = {f'{style}-{weight}-100-{grade}': wide_rows[f'{style}-{weight}-100-{grade}']
                         for weight in build.WEIGHTS for grade in (0, build.GRAD_MIN, build.GRAD_MAX)}
        hashes[style].update({item['master']: item['ttf_sha256_after'] for item in narrow['masters']})
        if len(hashes[style]) != 24:
            raise RuntimeError('Previous migration must provide exactly24 verified master TTFs/style')
    shutil.copytree(baseline, candidate)
    state = {'baseline': str(baseline.resolve()), 'source_files': before,
             'previous_inputs': pipeline.effective_preparation_inputs(manifest), 'target_inputs': pipeline.signature(),
             'tracked_overrides_sha256': pipeline.source_digest(ROOT / 'sources/overrides'),
             'driver_sha256': digest(__file__), 'patch_utility_sha256': digest(ROOT / 'sources/source_patch.py'),
             'shared_validation_sha256': digest(ROOT / 'sources/migrate_sign_widths.py'),
             'anchor_repair_loader_sha256': digest(ROOT / 'sources/migrate_sources.py'),
             'raw_anchor_evidence_sha256': digest(ROOT / 'build/normal-anchor-comparison.json'),
             'old_ttf_hashes': hashes}
    (candidate / 'math-letter-baseline.json').write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    print('Validated source project preserved; third migration candidate prepared.', flush=True)


def check_state(candidate):
    state = json.loads((candidate / 'math-letter-baseline.json').read_text())
    if state['target_inputs'] != pipeline.signature():
        raise RuntimeError('Font generator changed during mathematical-letter migration')
    if pipeline.prepared_source_hashes(Path(state['baseline'])) != state['source_files']:
        raise RuntimeError('Validated prior source project changed during migration')
    if pipeline.source_digest(ROOT / 'sources/overrides') != state['tracked_overrides_sha256']:
        raise RuntimeError('Tracked drawing overrides changed during migration')
    if digest(ROOT / 'build/normal-anchor-comparison.json') != state['raw_anchor_evidence_sha256']:
        raise RuntimeError('Original integer-donor comparison evidence changed during migration')
    for filename, key in (('migrate_math_letters.py', 'driver_sha256'), ('source_patch.py', 'patch_utility_sha256'),
                          ('migrate_sign_widths.py', 'shared_validation_sha256'),
                          ('migrate_sources.py', 'anchor_repair_loader_sha256')):
        if digest(ROOT / 'sources' / filename) != state[key]:
            raise RuntimeError('Migration or validation utility changed during the run')
    return state


def component_parents(reference, names):
    names = set(names)
    while True:
        added = {name for name in reference.getGlyphOrder() if reference['glyf'][name].isComposite()
                 and any(component.glyphName in names for component in reference['glyf'][name].components)} - names
        if not added:
            return names
        names.update(added)


def descendants(reference, names):
    names = set(names)
    edges = mathletters.semantic_edges(reference)
    while True:
        added = {target for source, target in edges if source in names} - names
        if not added:
            return names
        names.update(added)


def greek_dependencies(reference, donor_names):
    """Include every styled body borrowing a changed donor and its accents."""
    cmap = reference.getBestCmap()
    chancery = greekstyles.single_mapping(reference, 'ss01')
    names = set()
    for spec in greekstyles.FEATURES.values():
        style = spec['style']
        for character in greekstyles.BASE_CHARACTERS:
            if ord(character) not in cmap or character not in greekstyles.SHARED:
                continue
            codepoint = greekstyles.latin_codepoint(greekstyles.SHARED[character], style)
            donor = cmap.get(codepoint) if codepoint else None
            if donor and style == 'chancery':
                donor = chancery.get(donor, donor)
            if donor in donor_names:
                names.add(f'uni{ord(character):04X}.anodyne.grk.{style}')
        for character in greekstyles.ACCENTED_CHARACTERS:
            base = unicodedata.normalize('NFD', character)[0]
            if f'uni{ord(base):04X}.anodyne.grk.{style}' in names:
                names.add(f'uni{ord(character):04X}.anodyne.grk.{style}')
    return names


def condensed_subset(normal, names, native, policy, narrow, zero_sources):
    """Use the cold grid's zero-first precedence even for forced math names.

    Sans mathematical digit aliases make ordinary zero reachable from the math
    alphabet graph. Such membership must never replace the explicit native zero
    model with a generic condensed interpretation.
    """
    result = {}
    for weight in build.WEIGHTS:
        result[weight] = {}
        for name in names:
            special = zero_sources.condensed(name, weight)
            drawing = special if special is not None else (
                build.read(narrow[weight], name) if name in native
                else policy.draw(name, normal[weight][name], weight))
            result[weight][name] = quantize(drawing)
    return result


def reconstruct(style):
    data = raw_anchors()
    fonts = {}
    for row in data['anchors']:
        if row['style'] != style:
            continue
        weight = row['weight']
        font = TTFont(row['raw_ttf'])
        apply_anchor_repairs(font, ROOT / 'sources/overrides' / style / f'{style}-{weight}-100-0.ufo')
        fonts[weight] = font
    native_file = ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if style == 'Italic' else 'NotoSans[wdth,wght].ttf')
    noto = {w: instantiateVariableFont(TTFont(native_file), {'wdth': 100, 'wght': w}) for w in build.WEIGHTS}
    narrow = {w: instantiateVariableFont(TTFont(native_file), {'wdth': 62.5, 'wght': w}) for w in build.WEIGHTS}
    zero = NativeZeroSources(noto, narrow, TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf'), style == 'Italic',
                            TTFont(ROOT / 'src/noto/NotoSans[wdth,wght].ttf') if style == 'Italic' else None)
    temporary_reference, bold = fonts[400], fonts[700]
    zero.restore_fonts(temporary_reference, bold)
    normal = {w: {name: build.read(font, name) for name in font.getGlyphOrder()} for w, font in fonts.items()}
    for weight, replacements in zero.normal_outlines().items():
        normal[weight].update(replacements)
    quantize_anchors(normal)
    repair = mathletters.apply_to_normal_anchors(normal, temporary_reference, noto, notoC=narrow)
    quantize_anchors(normal)
    greek = greekstyles.apply_to_normal_anchors(normal, temporary_reference, bold, noto, narrow)
    quantize_anchors(normal)
    normalize_monospace(normal, temporary_reference)
    quantize_anchors(normal)
    reference = TTFont(old_ttf(style, 400, 100, 0))
    if temporary_reference.getGlyphOrder() != reference.getGlyphOrder():
        raise RuntimeError('Reconstruction changed the final glyph order')
    for name in reference.getGlyphOrder():
        if outline_value(normal[400][name]) != outline_value(build.read(reference, name)):
            raise RuntimeError(f'{style}: reconstructed default Regular changed: {name}')
    weight_parents = component_parents(reference, repair.repaired_weight_names)
    greek_changed = greek_dependencies(reference, weight_parents)
    wide_affected = component_parents(reference, weight_parents | greek_changed)
    narrow_affected = component_parents(reference, descendants(reference, repair.affected_names) | greek_changed)
    for weight in build.WEIGHTS:
        with TTFont(old_ttf(style, weight, 100, 0)) as previous:
            unexpected = [name for name, drawing in normal[weight].items()
                          if name not in wide_affected and outline_value(drawing) != outline_value(build.read(previous, name))]
            if unexpected:
                raise RuntimeError(f'{style} {weight}: unrelated reconstructed normal donors changed: {unexpected[:20]}')
    native = native_names(reference, noto[400]) - set(repair.forced_width_names)
    policy = Policy(reference, noto, narrow)
    condensed = condensed_subset(normal, narrow_affected, native, policy, narrow, zero)
    print(f'{style}: default Regular exact; {len(repair.repaired_weight_names)} weight repairs, {len(repair.forced_width_names)} forced width nodes, {len(greek_changed)} dependent Greek bodies/accents.', flush=True)
    return reference, normal, condensed, noto, narrow, repair, wide_affected, narrow_affected, greek_changed


def motion_preflight(style, reference, normal, condensed, wide_affected, narrow_affected):
    samples = []
    for weight, width, grade in ((400, 100, 0), (900, 100, 0), (400, 62.5, 0), (400, 100, 150)):
        font = TTFont(old_ttf(style, weight, width, grade))
        affected = wide_affected if width == 100 else narrow_affected
        anchors = normal if width == 100 else condensed
        drawings = {name: anchors[weight][name] for name in affected} if grade == 0 else dict(graded({w: {name: anchors[w][name] for name in affected} for w in build.WEIGHTS}, weight, grade))
        write_outlines(font, drawings)
        samples.append(font)
    names = mathletters.semantic_names(reference) | {g for g in reference.getGlyphOrder() if '.anodyne.grk.' in g}
    glyphsets = [font.getGlyphSet() for font in samples]
    frozen = {'weight': [], 'width': [], 'grade': []}
    for name in sorted(names):
        areas = []
        for glyphset in glyphsets:
            pen = AreaPen(glyphset)
            glyphset[name].draw(pen)
            areas.append(pen.value)
        for index, axis in enumerate(frozen, 1):
            if abs(areas[index] - areas[0]) < 1:
                frozen[axis].append(name)
    for font in samples:
        font.close()
    if any(frozen.values()):
        raise RuntimeError(f'{style}: full mathematical alphabet preflight still freezes axes: {frozen}')
    return {'status': 'passed', 'semantic_and_greek_glyphs': len(names), 'frozen': frozen,
            'locations': ['400/100/0', '900/100/0', '400/62.5/0', '400/100/150']}


def migrate_style(style, candidate, new_ttfs):
    state = check_state(candidate)
    baseline = Path(state['baseline'])
    report_path = candidate / f'math-letter-{style}.json'
    if report_path.exists():
        raise RuntimeError('A style report already exists; inspect it before repeating migration')
    for weight in build.WEIGHTS:
        for width in (100, 62.5):
            for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
                name = f'{style}-{weight}-{width}-{grade}'
                if digest(old_ttf(style, weight, width, grade)) != state['old_ttf_hashes'][style][name]:
                    raise RuntimeError(f'Preserved prior master TTF changed: {name}')
    reference, normal, condensed, noto, narrow, repair, wide, thin, greek_changed = reconstruct(style)
    motion = motion_preflight(style, reference, normal, condensed, wide, thin)
    print(style, 'complete alphabet/Greek weight-width-grade preflight passed.', flush=True)
    results, paths = [], []
    for width, anchors, affected, native in ((100, normal, wide, noto), (62.5, condensed, thin, narrow)):
        subset = {w: {name: anchors[w][name] for name in affected} for w in build.WEIGHTS}
        for weight in build.WEIGHTS:
            for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
                name = f'{style}-{weight}-{width}-{grade}'
                source_ttf = old_ttf(style, weight, width, grade)
                before, font = TTFont(source_ttf), TTFont(source_ttf)
                drawings = subset[weight] if grade == 0 else dict(graded(subset, weight, grade))
                write_outlines(font, drawings)
                changed = sorted(g for g in affected if outline_value(build.read(before, g)) != outline_value(build.read(font, g)))
                source, destination = baseline / style / (name + '.ufoz'), candidate / style / (name + '.ufoz')
                if weight == 400 and width == 100 and grade == 0:
                    if changed:
                        raise RuntimeError('Default Regular geometry changed after its exact reconstruction check')
                    paths.append(source_ttf)
                    results.append({'master': name, 'default_regular_preserved_byte_exact': True,
                                    'source_sha256_before': digest(source), 'source_sha256_after': digest(destination),
                                    'changed_geometry_glyphs': [], 'changed_zip_members': []})
                    before.close(); font.close()
                    continue
                font['GPOS'] = copy.deepcopy(reference['GPOS'])
                scale = 1 if width == 100 else sum(narrow[weight]['hmtx'][g][0] / noto[weight]['hmtx'][g][0] for g in 'nohdeasu') / 8
                build.position_master(font, reference, native[weight], scale)
                build.refresh_math_metrics(font, reference)
                extend_greek_mark_anchors(font)
                reorderGlyphs(font, font.getGlyphOrder())
                font['maxp'].recalc(font)
                glyph_count = verify_unaffected(before, font, affected)
                anchors_count = verify_gpos(before, font, native[weight], affected)
                math_count = verify_unaffected_math(before, font, affected)
                for tag in ('GSUB', 'GDEF'):
                    if before.getTableData(tag) != font.getTableData(tag):
                        raise RuntimeError(f'{name}: {tag} changed outside the intended repair')
                for glyph in affected:
                    if font['hmtx'][glyph][0] != anchors[weight][glyph].adv:
                        raise RuntimeError(f'{name}: glyph advance changes with grade: {glyph}')
                new_ttf = new_ttfs / style / (name + '.ttf')
                new_ttf.parent.mkdir(parents=True, exist_ok=True)
                font.save(new_ttf)
                entries = patch_ufoz(source, destination, font, changed)
                check_patched_glifs(destination, font, affected)
                results.append({'master': name, 'changed_geometry_glyphs': changed,
                                'source_sha256_before': digest(source), 'source_sha256_after': digest(destination),
                                'ttf_sha256': digest(new_ttf), 'changed_zip_members': entries,
                                'unaffected_rendered_glyphs_verified': glyph_count,
                                'unaffected_math_records_verified': math_count,
                                'affected_native_anchors_verified': anchors_count,
                                'other_gpos_fields_exact': True, 'gsub_gdef_byte_exact': True})
                paths.append(new_ttf)
                before.close(); font.close()
                print(f'{name}: {len(changed)} repaired drawings; {glyph_count} unrelated rendered glyphs/advances and layout invariants exact.', flush=True)
    build.validate_master_compatibility(paths)
    check_state(candidate)
    report = {'status': 'passed', 'style': style, 'inputs': pipeline.signature(), 'motion_preflight': motion,
              'method': 'Verified pre-Greek integer donors, canonical static-math repair, complete Greek regeneration and mono normalization; only changed GLIFs/layout sidecars patched.',
              'repaired_weight_names': sorted(repair.repaired_weight_names), 'forced_width_names': sorted(repair.forced_width_names),
              'dependent_greek_bodies_and_accents': sorted(greek_changed), 'repair_calibration': repair.report,
              'wide_affected': sorted(wide), 'condensed_affected': sorted(thin), 'masters': results,
              'default_regular_glyphs_preserved_exact': len(reference.getGlyphOrder()),
              'tracked_overrides_sha256': state['tracked_overrides_sha256']}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(style, 'third source migration passed.', flush=True)


def finalize(candidate):
    state = check_state(candidate)
    reports = [json.loads((candidate / f'math-letter-{style}.json').read_text()) for style in ('Roman', 'Italic')]
    for report in reports:
        if report['status'] != 'passed' or len(report['masters']) != 24 or report['inputs'] != pipeline.signature():
            raise RuntimeError('Both styles require24 successful source corners and current generator inputs')
        for master in report['masters']:
            if digest(candidate / report['style'] / (master['master'] + '.ufoz')) != master['source_sha256_after']:
                raise RuntimeError('A repaired source changed after verification')
    for relative, old_hash in state['source_files'].items():
        if '/math/' in relative or relative.endswith('.designspace') or relative.endswith('-400-100-0.ufoz'):
            if digest(candidate / relative) != old_hash:
                raise RuntimeError(f'Default Regular/reference/designspace changed: {relative}')
    pipeline.record_source_migration(candidate, Path(state['baseline']),
        description='Repair genuinely frozen mathematical letterlikes and descendants using calibrated compatible weight strokes, responsive width references, and complete dependent Greek regeneration. Preserve every default Regular outline/advance, authored varying optics, feature metadata and tracked overrides.',
        verification={'status': 'passed', 'styles': reports, 'default_regular_preserved': True,
                      'tracked_overrides_before': state['tracked_overrides_sha256'],
                      'tracked_overrides_after': pipeline.source_digest(ROOT / 'sources/overrides')},
        evidence_files=[candidate / 'math-letter-baseline.json', candidate / 'math-letter-Roman.json',
                        candidate / 'math-letter-Italic.json', ROOT / 'build/normal-anchor-comparison.json'])
    manifest = json.loads((candidate / 'preparation.json').read_text())
    if pipeline.effective_preparation_inputs(manifest) != pipeline.signature() or manifest['source_files'] != pipeline.prepared_source_hashes(candidate):
        raise RuntimeError('Third source ledger does not match current source/input hashes')
    print('Third migration ledger recorded; previous projects, Regular and tracked overrides preserved.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--style', choices=('Roman', 'Italic'))
    group.add_argument('--finalize', action='store_true')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'build/masters-0.500-signs')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'build/masters-0.500-mathletters')
    parser.add_argument('--new-ttfs', type=Path, default=ROOT / 'build/master-grid-0.500-mathletters')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.baseline, args.candidate)
    elif args.style:
        migrate_style(args.style, args.candidate, args.new_ttfs)
    else:
        finalize(args.candidate)


if __name__ == '__main__':
    main()
