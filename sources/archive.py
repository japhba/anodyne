#!/usr/bin/env python3
"""Bundle editable font sources together with their tests and demo source."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

import masters
import pipeline

ROOT = Path(__file__).resolve().parents[1]


def create_archive(folder, destination):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    pipeline.source_archive(folder, destination)
    # The font-only compatibility API remains in pipeline.py. The canonical
    # source release additionally carries everything needed to verify the
    # rebuilt fonts and regenerate/test the self-hosted demo.
    extras = []
    for name in ('tests', 'assets', 'images', '.github'):
        extras.extend(p for p in (ROOT / name).rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts)
    extras.extend(ROOT / name for name in ('index.html', 'mathfonts.json', 'package.json', 'package-lock.json'))
    with zipfile.ZipFile(destination, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
        included = set(archive.namelist())
        for path in sorted(extras):
            name = str(path.relative_to(ROOT))
            if name not in included:
                archive.write(path, name)
                included.add(name)
        archive.writestr('VERIFY-SOURCES.txt',
            'Build and verify the included editable sources:\n'
            '  make build MASTERS=masters\n'
            '  make check FONTS=build/dist/fonts\n'
            '  make qa FONTS=build/dist/fonts\n'
            '\nThe source-generator fixture tests skip if the optional pinned src/ cache is absent.\n'
            'All compiled-font regression tests run on the staged distribution.\n'
            '\nTo test the demo, first make release MASTERS=masters, then npm ci,\n'
            'npx playwright install chromium, npm run test:browser, npm run test:math-browser,\n'
            'npm run test:greek-converter and npm run test:greek-browser.\n')
    masters.deterministic_zip(destination)


def create_binary_archive(fonts, destination):
    fonts, destination = Path(fonts).resolve(), Path(destination).resolve()
    if len(list(fonts.glob('*/*.ttf'))) != 6:
        raise ValueError('The distribution must contain two variable and four static TTFs')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(fonts.rglob('*')):
            if path.is_file():
                archive.write(path, str(Path('fonts') / path.relative_to(fonts)))
        for path in (ROOT / 'OFL.txt', ROOT / 'README.md'):
            archive.write(path, path.name)
        if (fonts.parent / 'build-info.json').exists():
            archive.write(fonts.parent / 'build-info.json', 'build-info.json')
        for path in sorted((ROOT / 'build/compiled').glob('Anodyne-*.cache.json')):
            archive.write(path, str(Path('build-provenance') / path.name))
        for name in ('qa.json', 'layout-migration-proof.json', 'ssty-audit-after.json',
                     'tests.log', 'reproducibility.json', 'proofs/formula-checks.json'):
            path = ROOT / 'build' / name
            if path.is_file():
                archive.write(path, str(Path('validation') / name))
        for path in sorted((ROOT / 'build/fontbakery').glob('*.json')):
            archive.write(path, str(Path('validation/fontbakery') / path.name))
        archive.write(ROOT / 'sources/QA-NOTES.md', 'validation/QA-NOTES.md')
        for name in ('specimen.png', 'specimen-dark.png', 'specimen.svg', 'specimen-dark.svg',
                     'specimen.json', 'specimen-dark.json',
                     'text-settings.png', 'text-settings.svg', 'text-settings.json',
                     'math.png', 'math.pdf', 'math.svg', 'math-source.json',
                     'greek-math-styles.png', 'greek-math-styles.svg', 'greek-math-styles.pdf',
                     'greek-math-styles.json',
                     'math-features.svg', 'math-variations.svg'):
            path = ROOT / 'images' / name
            if path.is_file():
                archive.write(path, str(Path('images') / name))
        for path in sorted((ROOT / 'build/proofs').glob('*/proof.pdf')):
            archive.write(path, str(Path('proofs') / path.parent.name / path.name))
    masters.deterministic_zip(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--masters', type=Path, default=ROOT / 'build/masters')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--binary', action='store_true', help='package the font distribution instead of sources')
    parser.add_argument('--fonts', type=Path, default=ROOT / 'build/dist/fonts')
    args = parser.parse_args()
    if args.binary:
        from build import VERSION
        output = args.output or ROOT / 'build/dist' / f'Anodyne-{VERSION}.zip'
        create_binary_archive(args.fonts, output)
        print('Font archive:', output)
        return
    if not (args.masters / 'preparation.json').is_file():
        parser.error('prepare compatible sources first')
    output = args.output or ROOT / 'build/dist/Anodyne-sources.zip'
    create_archive(args.masters, output)
    print('Source archive:', output)


if __name__ == '__main__':
    main()
