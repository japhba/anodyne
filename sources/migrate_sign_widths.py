#!/usr/bin/env python3
"""Incrementally derive coherent condensed math signs from saved normal anchors.

The previous complete source project stays unchanged. Only non-native sign
family glyphs in condensed masters and their positioning/math sidecars are
rewritten; normal-width sources, references and tracked drawing overrides stay
byte-identical. A second preparation ledger entry records the actual migration.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import plistlib
import shutil
from types import SimpleNamespace
import zipfile

from fontTools.pens.recordingPen import RecordingPointPen, DecomposingRecordingPointPen
from fontTools.misc.xmlWriter import XMLWriter
from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools.ufoLib.glifLib import readGlyphFromString
from fontTools.varLib.instancer import instantiateVariableFont

import build
from condense import Policy
from greek_positioning import extend_greek_mark_anchors
from master_grid import graded, quantize, write_outlines
import pipeline
from source_patch import patch_ufoz

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized_points(value):
    result = []
    for operation, args, kwargs in value:
        if operation == 'addPoint':
            result.append((operation, args[0], args[1] if len(args) > 1 else kwargs.get('segmentType')))
        elif operation == 'addComponent':
            result.append((operation, args[0], args[1]))
        else:
            result.append((operation,))
    return result


def outline_value(outline):
    return outline.contours, outline.components, outline.adv


def native_names(reference, native):
    available = set(native.getGlyphOrder())
    result = set()
    for name in reference.getGlyphOrder():
        if name not in available:
            continue
        a, b = build.read(reference, name), build.read(native, name)
        if build.structure(a) == build.structure(b) and a.contours == b.contours and a.components == b.components:
            result.add(name)
    return result


def prepare(baseline, candidate):
    manifest = json.loads((baseline / 'preparation.json').read_text())
    sources = pipeline.prepared_source_hashes(baseline)
    if sources != manifest['source_files']:
        raise RuntimeError('Previous validated source project has unrecorded edits')
    if candidate.exists():
        raise RuntimeError('Use a new source candidate; do not overwrite a previous migration')
    signatures = pipeline.signature()
    source_ttf_hashes = {}
    for style in ('Roman', 'Italic'):
        report = json.loads((baseline / f'migration-{style}.json').read_text())
        if report['status'] != 'passed' or len(report['masters']) != 24:
            raise RuntimeError('Missing successful first-migration source report')
        source_ttf_hashes[style] = {item['master']: item['ttf_sha256'] for item in report['masters']}
    shutil.copytree(baseline, candidate)
    state = {'baseline': str(baseline.resolve()), 'source_files': sources,
             'previous_inputs': pipeline.effective_preparation_inputs(manifest), 'target_inputs': signatures,
             'tracked_overrides_sha256': pipeline.source_digest(ROOT / 'sources/overrides'),
             'patch_utility_sha256': digest(Path(__file__).with_name('source_patch.py')),
             'migration_driver_sha256': digest(__file__),
             'source_ttf_hashes': source_ttf_hashes}
    (candidate / 'sign-width-baseline.json').write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    print('Previous source project copied; originals and tracked overrides remain unchanged.', flush=True)


def check_state(candidate):
    state = json.loads((candidate / 'sign-width-baseline.json').read_text())
    if state['target_inputs'] != pipeline.signature():
        raise RuntimeError('Generator changed during the sign-width migration')
    if pipeline.prepared_source_hashes(Path(state['baseline'])) != state['source_files']:
        raise RuntimeError('Previous source project changed during migration')
    if pipeline.source_digest(ROOT / 'sources/overrides') != state['tracked_overrides_sha256']:
        raise RuntimeError('Tracked overrides changed during migration')
    if (digest(Path(__file__).with_name('source_patch.py')) != state['patch_utility_sha256']
            or digest(__file__) != state['migration_driver_sha256']):
        raise RuntimeError('Source patch/migration utility changed during the migration')
    return state


def check_patched_glifs(path, font, names):
    glyphs = font.getGlyphSet()
    with zipfile.ZipFile(path) as archive:
        contents_path = next(name for name in archive.namelist() if name.endswith('/glyphs/contents.plist'))
        contents = plistlib.loads(archive.read(contents_path))
        directory = contents_path.removesuffix('contents.plist')
        for name in names:
            pen, expected = RecordingPointPen(), RecordingPointPen()
            metadata = SimpleNamespace()
            readGlyphFromString(archive.read(directory + contents[name]), metadata, pen)
            glyphs[name].drawPoints(expected)
            if normalized_points(pen.value) != normalized_points(expected.value) or metadata.width != font['hmtx'][name][0]:
                raise RuntimeError(f'{path.name}: patched GLIF differs from its corrected TTF: {name}')


def verify_unaffected(before, after, affected):
    if before.getGlyphOrder() != after.getGlyphOrder():
        raise RuntimeError('Incremental correction changed glyph order')
    old_glyphs, new_glyphs = before.getGlyphSet(), after.getGlyphSet()
    checked = 0
    for name in before.getGlyphOrder():
        if name in affected:
            continue
        if outline_value(build.read(before, name)) != outline_value(build.read(after, name)):
            raise RuntimeError(f'Unrelated outline/advance changed: {name}')
        old_pen = DecomposingRecordingPointPen(old_glyphs)
        new_pen = DecomposingRecordingPointPen(new_glyphs)
        old_glyphs[name].drawPoints(old_pen)
        new_glyphs[name].drawPoints(new_pen)
        if normalized_points(old_pen.value) != normalized_points(new_pen.value):
            raise RuntimeError(f'Unrelated rendered glyph changed through a component: {name}')
        checked += 1
    return checked


def math_owner(font, path):
    info = font['MATH'].table.MathGlyphInfo
    if path[:3] == ('MathGlyphInfo', 'MathItalicsCorrectionInfo', 'ItalicsCorrection'):
        return info.MathItalicsCorrectionInfo.Coverage.glyphs[path[3]]
    if path[:3] == ('MathGlyphInfo', 'MathTopAccentAttachment', 'TopAccentAttachment'):
        return info.MathTopAccentAttachment.TopAccentCoverage.glyphs[path[3]]
    if path[:3] == ('MathGlyphInfo', 'MathKernInfo', 'MathKernInfoRecords'):
        return info.MathKernInfo.MathKernCoverage.glyphs[path[3]]
    if len(path) > 2 and path[0] == 'MathVariants' and path[1] in ('VertGlyphConstruction', 'HorizGlyphConstruction'):
        return getattr(font['MATH'].table.MathVariants, path[1].replace('GlyphConstruction', 'GlyphCoverage')).glyphs[path[2]]
    return None


def verify_unaffected_math(before, after, affected):
    left = dict(build._math_records(before['MATH'].table))
    right = dict(build._math_records(after['MATH'].table))
    if set(left) != set(right):
        raise RuntimeError('Incremental math correction changed the MATH record structure')
    checked = 0
    for path, record in left.items():
        owner = math_owner(before, path)
        if owner != math_owner(after, path):
            raise RuntimeError('Incremental math correction changed a coverage assignment')
        if owner in affected:
            continue
        new = right[path]
        old_device, new_device = getattr(record, 'DeviceTable', None), getattr(new, 'DeviceTable', None)
        if (record.Value != new.Value or (vars(old_device) if old_device else None) != (vars(new_device) if new_device else None)):
            raise RuntimeError(f'Unrelated MATH record changed: {path}: {record.Value} -> {new.Value}')
        checked += 1
    for name, value in vars(before['MATH'].table.MathConstants).items():
        if isinstance(value, int) and value != getattr(after['MATH'].table.MathConstants, name):
            raise RuntimeError(f'Unrelated MATH constant changed: {name}')
    old_variants, new_variants = before['MATH'].table.MathVariants, after['MATH'].table.MathVariants
    if old_variants is None or new_variants is None:
        if old_variants is not None or new_variants is not None:
            raise RuntimeError('Unrelated MATH construction table changed')
        return checked
    for direction in ('Vert', 'Horiz'):
        coverage = getattr(old_variants, direction + 'GlyphCoverage')
        if coverage is None:
            continue
        for base, old, new in zip(coverage.glyphs, getattr(old_variants, direction + 'GlyphConstruction'), getattr(new_variants, direction + 'GlyphConstruction')):
            relatives = {base} | {record.VariantGlyph for record in old.MathGlyphVariantRecord}
            if old.GlyphAssembly:
                relatives.update(part.glyph for part in old.GlyphAssembly.PartRecords)
            if relatives & affected:
                continue
            if [(r.VariantGlyph, r.AdvanceMeasurement) for r in old.MathGlyphVariantRecord] != [(r.VariantGlyph, r.AdvanceMeasurement) for r in new.MathGlyphVariantRecord]:
                raise RuntimeError(f'Unrelated MATH variants changed: {base}')
            if bool(old.GlyphAssembly) != bool(new.GlyphAssembly):
                raise RuntimeError(f'Unrelated MATH assembly changed: {base}')
            if old.GlyphAssembly and [(p.glyph, p.StartConnectorLength, p.EndConnectorLength, p.FullAdvance, p.PartFlags) for p in old.GlyphAssembly.PartRecords] != [(p.glyph, p.StartConnectorLength, p.EndConnectorLength, p.FullAdvance, p.PartFlags) for p in new.GlyphAssembly.PartRecords]:
                raise RuntimeError(f'Unrelated MATH assembly measurements changed: {base}')
    return checked


def verify_gpos(before, after, native, affected):
    """Keep every pair/mark field exact except remapped affected-base X/Y.

    Extension positioning wrappers are transparent and can change when the
    table is packed. Every allowed anchor coordinate is independently derived
    from the native master and the corrected final glyph bounds.
    """
    def subtable(table):
        return getattr(table, 'ExtSubTable', table)

    expected_count = 0
    for index, lookup in enumerate(native['GPOS'].table.LookupList.Lookup):
        target = after['GPOS'].table.LookupList.Lookup[index]
        for raw, positioned in zip(lookup.SubTable, target.SubTable):
            raw, positioned = subtable(raw), subtable(positioned)
            if raw.__class__.__name__ != 'MarkBasePos':
                continue
            originals = dict(zip(raw.BaseCoverage.glyphs, raw.BaseArray.BaseRecord))
            targets = dict(zip(positioned.BaseCoverage.glyphs, positioned.BaseArray.BaseRecord))
            for name in affected & originals.keys():
                for old, new in zip(originals[name].BaseAnchor, targets[name].BaseAnchor):
                    expected = copy.deepcopy(old)
                    build._map_anchor(expected, build._glyph_bounds(native, name), build._glyph_bounds(after, name))
                    if expected is not None:
                        if new is None or (expected.XCoordinate, expected.YCoordinate) != (new.XCoordinate, new.YCoordinate):
                            raise RuntimeError(f'Affected sign anchor differs from the native-master geometry remap: {name}')
                        expected_count += 1

    def canonical(font):
        table = copy.deepcopy(font['GPOS'].table)
        for lookup in table.LookupList.Lookup:
            if lookup.LookupType == 9:
                kinds = {record.ExtensionLookupType for record in lookup.SubTable}
                if len(kinds) != 1:
                    raise RuntimeError('Mixed extension positioning lookup types')
                lookup.LookupType = kinds.pop()
                lookup.SubTable = [record.ExtSubTable for record in lookup.SubTable]
            for record in lookup.SubTable:
                if record.__class__.__name__ != 'MarkBasePos':
                    continue
                for name, base in zip(record.BaseCoverage.glyphs, record.BaseArray.BaseRecord):
                    if name in affected:
                        for anchor in base.BaseAnchor:
                            if anchor is not None:
                                anchor.XCoordinate = anchor.YCoordinate = 0
        stream = io.BytesIO()
        table.toXML(XMLWriter(stream), font)
        return stream.getvalue()

    if canonical(before) != canonical(after):
        raise RuntimeError('Unrelated GPOS field changed; only affected MarkBase X/Y remaps are permitted')
    return expected_count


def migrate_style(style, candidate, old_ttfs, new_ttfs):
    state = check_state(candidate)
    baseline = Path(state['baseline'])
    report_path = candidate / f'sign-width-{style}.json'
    if report_path.exists():
        raise RuntimeError('Style migration already has a report; inspect it before running again')
    for name, expected in state['source_ttf_hashes'][style].items():
        if digest(old_ttfs / style / (name + '.ttf')) != expected:
            raise RuntimeError(f'Preserved source TTF changed: {name}')
    reference = TTFont(old_ttfs / style / f'{style}-400-100-0.ttf')
    native_path = ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if style == 'Italic' else 'NotoSans[wdth,wght].ttf')
    normal_native = {w: instantiateVariableFont(TTFont(native_path), {'wght': w, 'wdth': 100}) for w in build.WEIGHTS}
    narrow_native = {w: instantiateVariableFont(TTFont(native_path), {'wght': w, 'wdth': 62.5}) for w in build.WEIGHTS}
    policy = Policy(reference, normal_native, narrow_native)
    native = native_names(reference, normal_native[400])
    affected = set(policy.affected_math_signs) - native
    # A native parent of a changed component would require separate review.
    for name in native:
        glyph = reference['glyf'][name]
        if glyph.isComposite() and any(c.glyphName in affected for c in glyph.components):
            raise RuntimeError(f'Native sign parent requires explicit source review: {name}')
    if affected & {'uni093F0930094D0902.01', 'uni0919094D092F', 'uni2638'}:
        raise RuntimeError('Sign migration unexpectedly intersects the tracked topology repairs')
    normal = {}
    for weight in build.WEIGHTS:
        with TTFont(old_ttfs / style / f'{style}-{weight}-100-0.ttf') as font:
            normal[weight] = {name: build.read(font, name) for name in affected}
    condensed = {weight: {name: quantize(policy.draw(name, drawing, weight)) for name, drawing in drawings.items()}
                 for weight, drawings in normal.items()}
    print(f'{style}: {len(affected)} affected derived glyphs; {len(policy.math_signs)} share math-sign spacing; {len(policy.affected_math_signs & native)} native related glyphs retained exactly.', flush=True)
    results, paths = [], []
    for weight in build.WEIGHTS:
        for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
            name = f'{style}-{weight}-62.5-{grade}'
            old_path = old_ttfs / style / (name + '.ttf')
            destination = new_ttfs / style / (name + '.ttf')
            destination.parent.mkdir(parents=True, exist_ok=True)
            before, font = TTFont(old_path), TTFont(old_path)
            drawings = condensed[weight] if grade == 0 else dict(graded(condensed, weight, grade))
            write_outlines(font, drawings)
            # Appended Lisnoti math kerns are scaled in place. Always start
            # from the untouched normal-width table, never the prior condensed
            # table, or a second migration would scale those advances twice.
            font['GPOS'] = copy.deepcopy(reference['GPOS'])
            scale = sum(narrow_native[weight]['hmtx'][g][0] / normal_native[weight]['hmtx'][g][0] for g in 'nohdeasu') / 8
            build.position_master(font, reference, narrow_native[weight], scale)
            build.refresh_math_metrics(font, reference)
            extend_greek_mark_anchors(font)
            reorderGlyphs(font, font.getGlyphOrder())
            font['maxp'].recalc(font)
            checked = verify_unaffected(before, font, affected)
            gpos_checked = verify_gpos(before, font, narrow_native[weight], affected)
            for tag in ('GDEF', 'GSUB'):
                if before.getTableData(tag) != font.getTableData(tag):
                    raise RuntimeError(f'{name}: unrelated {tag} changed during sign-only correction')
            math_checked = verify_unaffected_math(before, font, affected)
            changed = sorted(g for g in affected if outline_value(build.read(before, g)) != outline_value(build.read(font, g)))
            for glyph in affected:
                if font['hmtx'][glyph][0] != condensed[weight][glyph].adv:
                    raise RuntimeError(f'{name}: sign advance changes with grade: {glyph}')
            font.save(destination)
            source = baseline / style / (name + '.ufoz')
            patched = candidate / style / (name + '.ufoz')
            entries = patch_ufoz(source, patched, font, changed)
            check_patched_glifs(patched, font, affected)
            results.append({'master': name, 'changed_geometry_glyphs': changed,
                            'unaffected_rendered_glyphs_verified': checked,
                            'unaffected_math_records_verified': math_checked,
                            'gpos_affected_anchors_independently_verified': gpos_checked,
                            'all_other_gpos_fields_semantically_identical': True,
                            'gdef_gsub_byte_identical': True,
                            'source_sha256_before': digest(source), 'source_sha256_after': digest(patched),
                            'ttf_sha256_before': digest(old_path), 'ttf_sha256_after': digest(destination),
                            'changed_zip_members': entries})
            paths.append(destination)
            before.close(); font.close()
            print(f'{name}: {len(changed)} changed glyphs, {checked} unrelated rendered glyphs/advances unchanged; source ZIP verified.', flush=True)
    paths.extend(old_ttfs / style / f'{style}-{weight}-100-{grade}.ttf'
                 for weight in build.WEIGHTS for grade in (0, build.GRAD_MIN, build.GRAD_MAX))
    build.validate_master_compatibility(paths)
    check_state(candidate)
    for relative, expected in state['source_files'].items():
        if not relative.startswith(style + '/') or '-62.5-' in relative:
            continue
        if digest(candidate / relative) != expected:
            raise RuntimeError(f'Wide/reference/designspace source changed: {relative}')
    report = {'status': 'passed', 'style': style, 'inputs': pipeline.signature(),
              'method': 'Derive only condensed non-native arithmetic/relation sign-family anchors from the existing integer normal masters, then their grade corners; reset GPOS/MATH from the same normal400 reference and patch only changed GLIF/layout ZIP members.',
              'family_members': sorted(policy.math_signs), 'redrawn_members': sorted(affected),
              'native_members_preserved': sorted(policy.affected_math_signs & native),
              'tracked_overrides_sha256': state['tracked_overrides_sha256'], 'masters': results}
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(style, 'incremental sign source migration verified.', flush=True)


def finalize(candidate):
    state = check_state(candidate)
    reports = [json.loads((candidate / f'sign-width-{style}.json').read_text()) for style in ('Roman', 'Italic')]
    for report in reports:
        if report['status'] != 'passed' or report['inputs'] != pipeline.signature() or len(report['masters']) != 12:
            raise RuntimeError('Both incremental sign migrations require complete successful reports')
        for item in report['masters']:
            if digest(candidate / report['style'] / (item['master'] + '.ufoz')) != item['source_sha256_after']:
                raise RuntimeError('Patched source changed after validation')
    for path, expected in state['source_files'].items():
        if '-62.5-' not in path and digest(candidate / path) != expected:
            raise RuntimeError(f'Non-condensed source changed: {path}')
    pipeline.record_source_migration(candidate, Path(state['baseline']),
        description='Coherent condensed arithmetic/relation sign widths use the Native Noto plus reference instead of its anomalous minus HVAR widths or the lowercase fallback. Only affected condensed GLIFs and their positioning/MATH sidecars are rewritten; normal sources and tracked topology overrides remain exact.',
        verification={'status': 'passed', 'styles': reports, 'wide_sources_and_references_unchanged': True,
                      'tracked_overrides_sha256_before': state['tracked_overrides_sha256'],
                      'tracked_overrides_sha256_after': pipeline.source_digest(ROOT / 'sources/overrides')},
        evidence_files=[candidate / 'sign-width-baseline.json', candidate / 'sign-width-Roman.json', candidate / 'sign-width-Italic.json'])
    manifest = json.loads((candidate / 'preparation.json').read_text())
    if pipeline.effective_preparation_inputs(manifest) != pipeline.signature() or manifest['source_files'] != pipeline.prepared_source_hashes(candidate):
        raise RuntimeError('Final sign-width migration ledger does not match current inputs/sources')
    print('Second source migration ledger recorded and verified; prior project and tracked overrides preserved.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--style', choices=('Roman', 'Italic'))
    group.add_argument('--finalize', action='store_true')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'build/masters-0.500')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'build/masters-0.500-signs')
    parser.add_argument('--old-ttfs', type=Path, default=ROOT / 'build/master-grid-0.500')
    parser.add_argument('--new-ttfs', type=Path, default=ROOT / 'build/master-grid-0.500-signs')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.baseline, args.candidate)
    elif args.style:
        migrate_style(args.style, args.candidate, args.old_ttfs, args.new_ttfs)
    else:
        finalize(args.candidate)


if __name__ == '__main__':
    main()
