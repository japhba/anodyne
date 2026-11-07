#!/usr/bin/env python3
"""Canonical Anodyne source preparation, compilation and distribution build."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources'))
COMPILER_MODULES = ('build.py', 'masters.py', 'metadata.py', 'mathfeatures.py',
                    'delimgen.py', 'mathtune.py', 'pipeline.py', 'instance.py', 'mathweb.py',
                    'layout_fixes.py', 'layout-fixes.json')


def signature():
    files = ['source-lock.json', 'build.py', 'masters.py', 'delimgen.py', 'mathtune.py', 'mathfeatures.py']
    return {name: hashlib.sha256((ROOT / 'sources' / name).read_bytes()).hexdigest()
            for name in files if (ROOT / 'sources' / name).exists()}


def source_digest(path):
    """Identify both packed sources and unpacked editor changes in provenance."""
    path = Path(path)
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    for file in files:
        if path.is_dir():
            digest.update(str(file.relative_to(path)).encode())
            digest.update(b'\0')
        with file.open('rb') as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
    return digest.hexdigest()


def prepared_source_hashes(folder):
    return {str(path.relative_to(folder)): source_digest(path)
            for path in sorted(Path(folder).rglob('*'))
            if path.is_file() and path.suffix in ('.ufoz', '.designspace')}


def run(*args):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def prepare(folder, force=False):
    from fetch_sources import fetch
    manifest = folder / 'preparation.json'
    current = signature()
    previous = json.loads(manifest.read_text()) if manifest.exists() else None
    if previous is not None and previous['inputs'] == current and not force:
        print('Compatible source masters are current; preserving source edits.', flush=True)
        return
    if folder.exists() and any(folder.rglob('*.ufo')):
        raise RuntimeError('Unpacked editable UFOs exist. Back up or move the master folder before re-preparing; source edits will not be overwritten.')
    existing = prepared_source_hashes(folder) if folder.exists() else {}
    if existing:
        if not force:
            raise RuntimeError('Prepared sources already exist and generator inputs changed. Build from the matching generator, or explicitly re-prepare with --force after preserving edits.')
        if previous is None or 'source_files' not in previous:
            raise RuntimeError('Existing prepared sources have no original checksum record. Move or back them up before re-preparing; their edits cannot be verified.')
        if existing != previous['source_files']:
            raise RuntimeError('Prepared sources have been edited. Move or back them up before re-preparing; edited UFOZ/designspace sources will not be overwritten.')
    fetch()
    folder.mkdir(parents=True, exist_ok=True)
    for style in ('roman', 'italic'):
        run(sys.executable, ROOT / 'sources/build.py', '--lisnoti', ROOT / 'src/lisnoti/font-Lisnoti/Lisnoti-ttf',
            '--noto', ROOT / 'src/noto', '--out', ROOT / 'build/bootstrap', '--only', style,
            '--masters', folder, '--prepare-only')
    manifest.write_text(json.dumps({'schema': 1, 'inputs': current,
        'source_files': prepared_source_hashes(folder),
        'description': 'Compatible bootstrap sources. Outlines remain subject to design review; edited UFO sources and tracked overrides are consumed by subsequent builds.'}, indent=2) + '\n')


def write_license(path):
    # Canonical release license is shipped with the editable source archive.
    # Compiling prepared sources must not require the upstream binary cache.
    path.write_text((ROOT / 'OFL.txt').read_text())


def package_math_web(flat, destination):
    """MathML needs MATH and GDEF variation stores: keep complete fonts here."""
    from fontTools.ttLib import TTFont
    import masters
    destination.mkdir(parents=True, exist_ok=True)
    css = ['/* Anodyne Math: full variable outlines and mathematical layout data. */']
    for italic, name in ((False, 'Anodyne[GRAD,wdth,wght].ttf'), (True, 'Anodyne-Italic[GRAD,wdth,wght].ttf')):
        font = TTFont(flat / name)
        font.flavor = 'woff2'
        masters.normalize_timestamp(font)
        output = 'anodyne-math-italic.woff2' if italic else 'anodyne-math.woff2'
        font.save(destination / output)
        css.append('@font-face { font-family: "Anodyne Math"; '
                   f'font-style: {"italic" if italic else "normal"}; font-weight: 100 900; '
                   'font-stretch: 62.5% 100%; font-display: swap; '
                   f'src: url("./{output}") format("woff2"); }}')
    from mathweb import package_feature_fonts
    css.extend(package_feature_fonts(flat, destination))
    (destination / 'anodyne-math.css').write_text('\n'.join(css) + '\n')


def compiler_fingerprint():
    return {name: source_digest(ROOT / 'sources' / name) for name in COMPILER_MODULES
            if (ROOT / 'sources' / name).exists()}


def dependency_versions():
    names = [line.partition('==')[0].strip() for line in (ROOT / 'requirements.lock').read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    return {name: importlib.metadata.version(name) for name in names}


def style_cache_inputs(folder, italic=False):
    from fontTools.designspaceLib import DesignSpaceDocument
    import masters
    style = 'Italic' if italic else 'Roman'
    folder = Path(folder)
    source = folder / style / f'Anodyne-{style}.designspace'
    hashes = {source.name: source_digest(source)}
    for descriptor in DesignSpaceDocument.fromfile(source).sources:
        hashes[descriptor.name] = source_digest(descriptor.path)
    overrides = ROOT / 'sources/overrides' / style
    return {'schema': 1, 'style': style, 'sources': hashes,
            'overrides': source_digest(overrides) if overrides.exists() else None,
            'compiler_sources': compiler_fingerprint(), 'dependencies': dependency_versions(),
            'options': {'exclude': ['MVAR'], 'optimize': True, 'source_date_epoch': masters.epoch(),
                        'python': list(sys.version_info[:3]), 'hash_seed_probe': hash('Anodyne source compilation')}}


def style_cache_key(inputs):
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def valid_style_cache(cache_path, font_path, key):
    try:
        cache = json.loads(Path(cache_path).read_text())
        return (cache['key'] == key and Path(font_path).is_file()
                and source_digest(font_path) == cache['output_sha256'])
    except (OSError, ValueError, KeyError):
        return False


def compile_style(folder, flat, italic=False):
    """Compile one style or reuse a verified final-font cache without preparation."""
    import tempfile
    import build
    import masters
    from fontTools.ttLib import TTFont
    folder, flat = Path(folder), Path(flat)
    flat.mkdir(parents=True, exist_ok=True)
    style = 'Italic' if italic else 'Roman'
    filename = 'Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf'
    output, cache_path = flat / filename, flat / f'Anodyne-{style}.cache.json'
    inputs = style_cache_inputs(folder, italic)
    key = style_cache_key(inputs)
    if valid_style_cache(cache_path, output, key):
        print(f'{style}: using verified compiled-font cache', flush=True)
        return TTFont(output, recalcTimestamp=False)
    print(f'{style}: compiling persisted editable sources', flush=True)
    source = folder / style / f'Anodyne-{style}.designspace'
    variable = masters.compile_designspace(source)
    build.set_names(variable, 'Italic' if italic else 'Regular', 'Italic' if italic else 'Regular', True)
    build.stat(variable, italic)
    masters.normalize_timestamp(variable)
    if style_cache_key(style_cache_inputs(folder, italic)) != key:
        raise RuntimeError('Source/compiler inputs changed while compiling; refusing to cache a mixed build')
    with tempfile.NamedTemporaryFile(dir=flat, suffix='.ttf', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        variable.save(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    cache = {'key': key, 'inputs': inputs, 'output': filename, 'output_sha256': source_digest(output)}
    temporary = cache_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(cache, indent=2, sort_keys=True) + '\n')
    temporary.replace(cache_path)
    print(f'{style}: compiled cache saved to {output}', flush=True)
    return variable


def compile_release(folder, dist):
    import build
    import masters
    from fontTools.designspaceLib import DesignSpaceDocument
    source_hashes = {}
    flat = ROOT / 'build/compiled'
    flat.mkdir(parents=True, exist_ok=True)
    for italic, style in ((False, 'Roman'), (True, 'Italic')):
        source = folder / style / f'Anodyne-{style}.designspace'
        source_hashes[f'{style}/{source.name}'] = source_digest(source)
        for descriptor in DesignSpaceDocument.fromfile(source).sources:
            source_hashes[f'{style}/{descriptor.name}'] = source_digest(descriptor.path)
        variable = compile_style(folder, flat, italic)
        # Use the same variable MATH data for named and arbitrary instances.
        # The instancer folds VariationIndex values and refreshes geometry.
        for weight, name, ps in ((400, 'Italic' if italic else 'Regular', 'Italic' if italic else 'Regular'),
                                 (700, 'Bold Italic' if italic else 'Bold', 'BoldItalic' if italic else 'Bold')):
            build.static(variable, weight, None, str(flat / f'Anodyne-{ps}.ttf'), name, ps)
    write_license(flat / 'OFL.txt')
    distribution = dist / 'fonts'
    for subdir in ('variable', 'static', 'webfonts', 'mathwebfonts'):
        if (distribution / subdir).exists():
            shutil.rmtree(distribution / subdir)
        (distribution / subdir).mkdir(parents=True, exist_ok=True)
    for file in flat.glob('*.ttf'):
        target = 'variable' if '[' in file.name else 'static'
        shutil.copyfile(file, distribution / target / file.name)
    # Reuse one canonical subset/range implementation for OverLyX and this repo.
    served = ROOT / 'build/served'
    build.install(str(flat), str(served))
    for file in (served / 'web').iterdir():
        shutil.copyfile(file, distribution / 'webfonts' / file.name)
    package_math_web(flat, distribution / 'mathwebfonts')
    shutil.copyfile(flat / 'OFL.txt', dist / 'OFL.txt')
    packages = {name: importlib.metadata.version(name) for name in ('fonttools', 'fontmake', 'ufoLib2', 'ufo2ft', 'brotli', 'uharfbuzz')}
    hashes = {str(path.relative_to(dist)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(distribution.rglob('*')) if path.is_file()}
    info = {'version': build.VERSION, 'source_date_epoch': masters.epoch(),
            'source_preparation': json.loads((folder / 'preparation.json').read_text()),
            'compiler_sources': {str(path.relative_to(ROOT)): source_digest(path)
                                 for path in sorted((ROOT / 'sources').rglob('*.py'))
                                 if '__pycache__' not in path.parts},
            'editable_sources': source_hashes,
            'tracked_overrides': source_digest(ROOT / 'sources/overrides'),
            'dependencies': packages, 'files': hashes}
    (dist / 'build-info.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n')


def source_archive(folder, destination):
    """Ship prepared editable sources, generator sources, overrides and licenses."""
    import masters
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = list((ROOT / 'sources').rglob('*')) + list(folder.rglob('*'))
    paths += [ROOT / p for p in ('requirements.in', 'requirements.lock', 'requirements-qa.lock', 'requirements-qa-build.lock', 'Makefile', 'OFL.txt', 'README.md')]
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            name = Path('masters') / path.relative_to(folder) if path.is_relative_to(folder) else path.relative_to(ROOT)
            archive.write(path, str(name))
        archive.writestr('BUILD-SOURCES.txt', 'These are the exact prepared editable sources.\nRebuild from this archive with: make build MASTERS=masters\nTo edit: make edit MASTERS=masters\nSee sources/README.md for source formats, tracked overrides and provenance.\n')
    masters.deterministic_zip(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'build', 'release', 'sources'])
    parser.add_argument('--masters', type=Path, default=ROOT / 'build/masters')
    parser.add_argument('--dist', type=Path, default=ROOT / 'build/dist')
    parser.add_argument('--force', action='store_true', help='refresh generated sources; refuses to overwrite unpacked edits')
    args = parser.parse_args()
    args.masters = args.masters.resolve()
    args.dist = args.dist.resolve()
    lock = json.loads((ROOT / 'sources/source-lock.json').read_text())
    os.environ.setdefault('SOURCE_DATE_EPOCH', str(lock['source_date_epoch']))
    os.environ.setdefault('PYTHONHASHSEED', '0')
    if args.operation == 'sources':
        if not (args.masters / 'preparation.json').exists():
            raise RuntimeError('Run make prepare first')
        source_archive(args.masters, args.dist / 'Anodyne-sources.zip')
        return
    prepare(args.masters, args.force)
    if args.operation == 'prepare':
        return
    compile_release(args.masters, args.dist)
    if args.operation == 'release':
        shutil.copytree(args.dist / 'fonts', ROOT / 'fonts', dirs_exist_ok=True)
        shutil.copyfile(args.dist / 'OFL.txt', ROOT / 'OFL.txt')
        shutil.copyfile(args.dist / 'build-info.json', ROOT / 'fonts/build-info.json')


if __name__ == '__main__':
    main()
