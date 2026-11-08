#!/usr/bin/env python3
"""Migrate verified integer anchors through the canonical 0.500 master grid.

This is an explicit source migration, not a fresh upstream contour matching
pass. Its evidence retains hashes of the original sources and the eight raw
anchor fonts already compared against those sources. Run each style separately
before ``--finalize``. Original sources and tracked overrides are backed up;
unknown edited override glyphs are never discarded.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from fontTools.pens.ttGlyphPen import TTGlyphPointPen
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from ufoLib2 import Font

import build
import greekstyles
import masters
from master_grid import build_grid, quantize, quantize_anchors
import pipeline
from zero import NativeZeroSources

ROOT = Path(__file__).resolve().parents[1]
REPAIRS = {'uni093F0930094D0902.01', 'uni0919094D092F', 'uni2638'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def point_stream(glyph):
    pen = RecordingPointPen()
    glyph.drawPoints(pen)
    result = []
    for operation, args, kwargs in pen.value:
        if operation == 'addPoint':
            result.append((operation, args[0], args[1] if len(args) > 1 else kwargs.get('segmentType')))
        elif operation == 'addComponent':
            result.append((operation, args[0], args[1]))
        else:
            result.append((operation,))
    return result


def verified_inputs(baseline_path, comparison_path):
    baseline = json.loads(baseline_path.read_text())
    original = Path(baseline['source_root'])
    if pipeline.prepared_source_hashes(original) != baseline['prepared_manifest']['source_files']:
        raise RuntimeError('Original prepared sources changed after the preserved migration baseline')
    if pipeline.source_digest(ROOT / 'sources/overrides') != baseline['override_sha256']:
        raise RuntimeError('Tracked overrides changed after the preserved baseline; inspect edits before migrating')
    comparison = json.loads(comparison_path.read_text())
    if comparison['status'] != 'passed' or len(comparison['anchors']) != 8:
        raise RuntimeError('All eight anchors require exact persisted-source comparison evidence')
    for anchor in comparison['anchors']:
        if anchor['status'] != 'passed' or anchor['point_stream_mismatches'] or anchor['missing_glyphs']:
            raise RuntimeError('An anchor failed its original-source comparison')
        for key in ('raw_ttf', 'ufoz'):
            if digest(anchor[key]) != anchor[key + '_sha256']:
                raise RuntimeError(f'Previously verified {key} changed: {anchor[key]}')
    return baseline, comparison


def apply_anchor_repairs(font, path):
    with Font.open(path, lazy=False) as overrides:
        if set(overrides.keys()) != REPAIRS:
            raise RuntimeError(f'{path}: additional edited override glyphs require explicit migration')
        for name in REPAIRS:
            pen = TTGlyphPointPen(font.getGlyphSet())
            overrides[name].drawPoints(pen)
            font['glyf'][name] = pen.glyph()
            font['hmtx'][name] = round(overrides[name].width), 0


def migrate_style(style, candidate, ttf_root, override_candidate, baseline_path, comparison_path):
    baseline, comparison = verified_inputs(baseline_path, comparison_path)
    started_inputs = pipeline.signature()
    if (candidate / style).exists():
        raise RuntimeError(f'{candidate / style} exists; preserve or remove the incomplete candidate explicitly')
    if not override_candidate.exists():
        shutil.copytree(ROOT / 'sources/overrides', override_candidate)
    normal_fonts = {}
    for anchor in comparison['anchors']:
        if anchor['style'] != style:
            continue
        weight = anchor['weight']
        font = TTFont(anchor['raw_ttf'])
        apply_anchor_repairs(font, ROOT / 'sources/overrides' / style / f'{style}-{weight}-100-0.ufo')
        normal_fonts[weight] = font
    italic = style == 'Italic'
    native_path = ROOT / 'src/noto' / ('NotoSans-Italic[wdth,wght].ttf' if italic else 'NotoSans[wdth,wght].ttf')
    noto = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 100, 'wght': w}) for w in build.WEIGHTS}
    noto_c = {w: instantiateVariableFont(TTFont(native_path), {'wdth': 62.5, 'wght': w}) for w in build.WEIGHTS}
    zero = NativeZeroSources(noto, noto_c, TTFont(ROOT / 'src/noto/NotoSansMath-Regular.ttf'), italic,
                            TTFont(ROOT / 'src/noto/NotoSans[wdth,wght].ttf') if italic else None)
    regular, bold = normal_fonts[400], normal_fonts[700]
    zero.restore_fonts(regular, bold)
    normal = {w: {name: build.read(font, name) for name in font.getGlyphOrder()} for w, font in normal_fonts.items()}
    for weight, drawings in zero.normal_outlines().items():
        normal[weight].update(drawings)
    quantize_anchors(normal)
    import mathletters
    repaired_math = mathletters.apply_to_normal_anchors(normal, regular, noto, notoC=noto_c)
    quantize_anchors(normal)
    greek = greekstyles.apply_to_normal_anchors(normal, regular, bold, noto, noto_c)
    ttf_folder = ttf_root / style
    ttf_folder.mkdir(parents=True, exist_ok=True)
    build_grid(normal, regular, bold, noto, noto_c, italic, str(ttf_folder),
               masters_dir=str(candidate), prepare_only=True, zero_sources=zero,
               forced_width_names=repaired_math.forced_width_names)
    del normal_fonts, normal
    results = []
    for path in sorted(ttf_folder.glob(f'{style}-*.ttf')):
        source_path = candidate / style / (path.stem + '.ufoz')
        override_path = override_candidate / style / (path.stem + '.ufo')
        with TTFont(path) as font, Font.open(source_path, lazy=False) as source, Font.open(override_path, lazy=False) as overrides:
            if set(overrides.keys()) != REPAIRS:
                raise RuntimeError(f'{override_path}: refusing to replace unknown edited glyphs')
            glyphs = font.getGlyphSet()
            _, weight, width, grade = re.fullmatch(r'(Roman|Italic)-(\d+)-(\d+(?:\.\d+)?)-(-?\d+)', path.stem).groups()
            if int(grade) == 0:
                for name in zero.names:
                    actual = build.read(font, name)
                    expected = quantize(zero.outline(name, int(weight), float(width)))
                    if (actual.contours, actual.components, actual.adv) != (expected.contours, expected.components, expected.adv):
                        raise RuntimeError(f'{path.stem}: native zero master differs from its pinned upstream drawing: {name}')
            # Rebase the existing three mechanical topology repairs on the new
            # common grid so they cannot restore obsolete condensed drawings.
            for name in REPAIRS:
                original_lib = copy.deepcopy(overrides[name].lib)
                del overrides[name]
                target = overrides.newGlyph(name)
                glyphs[name].drawPoints(target.getPointPen())
                target.width = font['hmtx'][name][0]
                target.unicodes = list(source[name].unicodes)
                target.lib.update(original_lib)
                target.lib['com.overlyx.anodyne.gridMigration'] = '0.500 shared integer-anchor width/grade derivation; original topology repair retained.'
            overrides.save(override_path, overwrite=True)
            if source.glyphOrder != font.getGlyphOrder():
                raise RuntimeError(f'{path.stem}: source glyph order changed during export')
            selected = set(zero.names) | REPAIRS | set(greek.names)
            for name in selected:
                if point_stream(source[name]) != point_stream(glyphs[name]) or source[name].width != font['hmtx'][name][0]:
                    raise RuntimeError(f'{path.stem}: exported source geometry differs for {name}')
            for name in REPAIRS:
                if point_stream(overrides[name]) != point_stream(source[name]):
                    raise RuntimeError(f'{path.stem}: tracked repair differs from the new canonical drawing')
            results.append({'master': path.stem, 'ttf_sha256': digest(path), 'source_sha256': digest(source_path),
                            'override_sha256': pipeline.source_digest(override_path),
                            'glyphs': len(font.getGlyphOrder()), 'verified_exported_glyphs': len(selected)})
    if len(results) != 24 or pipeline.signature() != started_inputs:
        raise RuntimeError('Incomplete grid or generator changed during migration; preserve candidate for inspection')
    report = {'status': 'passed', 'style': style, 'inputs': started_inputs,
              'method': 'Verified persisted integer normal anchors, explicit three topology repairs, native Noto zeros, new Greek styles, shared canonical width/grade grid.',
              'composite_origin_correction': 'Raw compatible coordinates retained; final LSBs recalculated in a second pass after all children. Original stale-LSB translations remain listed in the anchor evidence.',
              'monospace_metrics': 'All mathematical mono Latin/Greek/digits share 680 units before width derivation; native dotted mono zero ink retained and centered.',
              'baseline_sha256': digest(baseline_path), 'anchor_comparison_sha256': digest(comparison_path),
              'greek_glyphs_added': len(greek.names), 'masters': results}
    (candidate / f'migration-{style}.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'{style}: 24 source masters exported and verified; original sources remain unchanged.', flush=True)


def validate_advance_clamp_audit(path, reports, candidate):
    """Accept only the proven no-op clamp of these nonnegative input advances.

    Actual style reports retain their original generator signatures. This is a
    narrow exception for one literal source correction, with complete advance
    records, exact normal-outline reconstruction and unchanged source hashes.
    It is deliberately not a general generator-signature override.
    """
    audit = json.loads(path.read_text())
    before, after = audit['input_signature_before'], audit['input_signature_after']
    if audit.get('kind') != 'nonnegative-advance-clamp' or audit.get('status') != 'passed':
        raise RuntimeError('Only a successful nonnegative-advance clamp audit is accepted')
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    if changed != {'master_grid.py'} or after != pipeline.signature() or any(report['inputs'] != before for report in reports):
        raise RuntimeError('Clamp audit does not describe the exact single-field signature change')
    old_path = Path(audit['old_master_grid_source'])
    old, new = old_path.read_bytes(), (ROOT / 'sources/master_grid.py').read_bytes()
    previous = b'        round(outline.adv))\n'
    corrected = b'        max(0, round(outline.adv)))\n'
    if old.count(previous) != 1 or old.replace(previous, corrected, 1) != new:
        raise RuntimeError('Master-grid change contains more than the approved advance clamp')
    if hashlib.sha256(old).hexdigest() != before['master_grid.py'] or hashlib.sha256(new).hexdigest() != after['master_grid.py']:
        raise RuntimeError('Clamped source bytes differ from the recorded generator fingerprints')
    if pipeline.prepared_source_hashes(candidate) != audit['candidate_source_files']:
        raise RuntimeError('Candidate geometry/layout source checksums changed after the domain audit')
    script = Path(audit['audit_script_file'])
    records_path = Path(audit['advance_records_file'])
    if digest(script) != audit['audit_script_sha256'] or digest(records_path) != audit['advance_records_sha256']:
        raise RuntimeError('Advance-domain evidence changed after its audit')
    required_stages = {'verified raw integer anchors plus the original three explicit repairs',
                       'raw native text and derived math optical zero replacements',
                       'raw newly generated Greek drawings before final grid quantization',
                       'complete normal inputs to the master grid'}
    records = json.loads(records_path.read_text())
    expected = {(style, stage) for style in ('Roman', 'Italic') for stage in required_stages}
    if {(row['style'], row['stage']) for row in records} != expected or len(records) != len(expected):
        raise RuntimeError('Advance-domain evidence does not cover every actual input family/style')
    summaries = {(row['style'], row['stage']): row for row in audit['domain_checks']}
    for row in records:
        data = row['records']
        summary = summaries[row['style'], row['stage']]
        if (not data or {item[0] for item in data} != set(build.WEIGHTS)
                or any(not isinstance(item[2], (int, float)) or not math.isfinite(item[2]) or item[2] < 0 for item in data)):
            raise RuntimeError('Advance-domain evidence contains missing, invalid or negative input advances')
        if (len(data) != summary['glyph_advances_checked'] or summary['negative_advances']
                or min(item[2] for item in data) != summary['minimum_advance']
                or hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest() != summary['advance_records_sha256']):
            raise RuntimeError('Advance-domain summary differs from its complete checked records')
    reconstructions = {row['style']: row for row in audit['normal_reconstructions']}
    for report in reports:
        style = report['style']
        reconstruction = reconstructions[style]
        expected_count = 4 * report['masters'][0]['glyphs']
        full_inputs = summaries[style, 'complete normal inputs to the master grid']
        if (reconstruction['status'] != 'passed' or reconstruction['normal_master_glyphs_compared'] != expected_count
                or full_inputs['glyph_advances_checked'] != expected_count
                or digest(candidate / f'migration-{style}.json') != audit['style_report_sha256'][style]):
            raise RuntimeError('Audit does not reproduce every actual normal master or preserve its original report')
    return audit, [path, records_path, old_path, script]


def finalize(candidate, override_candidate, baseline_path, comparison_path, advance_clamp_audit=None):
    verified_inputs(baseline_path, comparison_path)
    reports = [json.loads((candidate / f'migration-{style}.json').read_text()) for style in ('Roman', 'Italic')]
    correction, correction_evidence = None, []
    if advance_clamp_audit is not None:
        correction, correction_evidence = validate_advance_clamp_audit(advance_clamp_audit, reports, candidate)
    for report in reports:
        if (report['status'] != 'passed' or len(report['masters']) != 24
                or (report['inputs'] != pipeline.signature() and correction is None)):
            raise RuntimeError('Style verification is incomplete or generator inputs changed')
        for item in report['masters']:
            path = candidate / report['style'] / (item['master'] + '.ufoz')
            if digest(path) != item['source_sha256']:
                raise RuntimeError(f'Verified candidate source changed: {path}')
            override_path = override_candidate / report['style'] / (item['master'] + '.ufo')
            if pipeline.source_digest(override_path) != item['override_sha256']:
                raise RuntimeError(f'Verified candidate override changed: {override_path}')
    overrides = ROOT / 'sources/overrides'
    backup = ROOT / 'build/overrides-before-0.500'
    if backup.exists():
        raise RuntimeError(f'Backup already exists: {backup}; preserve and resolve it explicitly')
    manifest = json.loads((override_candidate / 'manifest.json').read_text())
    manifest['entries'][0]['grid_migration'] = '0.500: all 48 drawings regenerated from the same integer anchors with the shared calibrated condensed/grade grid; the three original topology repairs and their provenance remain.'
    (override_candidate / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    overrides.rename(backup)
    try:
        override_candidate.rename(overrides)
        pipeline.record_source_migration(candidate, baseline_path,
            description='0.500 native Noto zero/figure restoration, calibrated condensation, fixed math mono cells, new Greek style families, and final composite origin correction, derived from verified persisted integer normal anchors.',
            verification={'status': 'passed', 'styles': reports, 'original_override_backup': str(backup),
                          'preserved_anchor_evidence': str(comparison_path),
                          'cold_generator_correction': correction},
            evidence_files=[comparison_path, candidate / 'migration-Roman.json', candidate / 'migration-Italic.json'] + correction_evidence)
    except BaseException:
        if overrides.exists():
            overrides.rename(override_candidate)
        backup.rename(overrides)
        raise
    print(f'Migration recorded in {candidate / "preparation.json"}; prior overrides preserved at {backup}.', flush=True)
    print('Original build/masters is preserved. Build/validate this candidate before installing it as the canonical source folder.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--style', choices=('Roman', 'Italic'))
    parser.add_argument('--finalize', action='store_true')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'build/masters-0.500')
    parser.add_argument('--ttfs', type=Path, default=ROOT / 'build/master-grid-0.500')
    parser.add_argument('--overrides', type=Path, default=ROOT / 'build/overrides-0.500')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'build/source-migration-baseline-0.400.json')
    parser.add_argument('--comparison', type=Path, default=ROOT / 'build/normal-anchor-comparison.json')
    parser.add_argument('--advance-clamp-audit', type=Path,
                        help='Exact no-op correction audit; actual style report inputs remain unchanged')
    args = parser.parse_args()
    if args.finalize == bool(args.style):
        parser.error('Choose either --style or --finalize')
    if args.finalize:
        finalize(args.candidate, args.overrides, args.baseline, args.comparison, args.advance_clamp_audit)
    else:
        migrate_style(args.style, args.candidate, args.ttfs, args.overrides, args.baseline, args.comparison)


if __name__ == '__main__':
    main()
