#!/usr/bin/env python3
"""Render the complete mathematical specimen as a high-resolution PNG, SVG and PDF.

python sources/render_specimen.py --fonts fonts --out images

Needs LuaLaTeX (unicode-math and standalone), Poppler and Ghostscript. Font
geometry comes from the named final TTF faces. SOURCE_DATE_EPOCH and suppressed
optional PDF metadata make repeated renders stable in the same toolchain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'sources/specimen/math.tex'
ATTRIBUTION = {
    'source': 'https://tex.stackexchange.com/q/425098',
    'title': 'Which OpenType math fonts are available?',
    'author': 'Henri Menke',
    'original_date': '2018-04-06',
    'source_license': 'https://creativecommons.org/licenses/by-sa/3.0/',
    'adaptation_license': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'overlyx_preview': 'https://github.com/japhba/overlyx/blob/90cd4e50844dbc713d9ce0345900deec242d6ed8/packages/client/src/app/Settings.tsx#L155',
    'changes': 'All mathematical test expressions retained. The explanatory wording and layout are new; added Anodyne structures and style comparisons.',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, directory, environment, log):
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed; see {log}')


def warm_font(path, directory, environment):
    """Cache one face at a time before the specimen loads text/bold/math together."""
    source = ('\\documentclass{article}\\begin{document}'
              '\\font\\specimen={[%s]:mode=base} \\specimen x\\end{document}\n') % path
    (directory / 'warm.tex').write_text(source)
    run(['lualatex', '-interaction=nonstopmode', '-halt-on-error', 'warm.tex'],
        directory, environment, directory / f'warm-{path.stem}.log')


def render(fonts, output, work, dpi=300):
    fonts, output, work = Path(fonts).resolve(), Path(output).resolve(), Path(work).resolve()
    static = fonts / 'static'
    sources = [static / f'Anodyne-{style}.ttf' for style in ('Regular', 'Bold')]
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
    for executable in ('lualatex', 'pdftocairo', 'pdftoppm', 'pdfinfo', 'pdffonts'):
        if not shutil.which(executable):
            raise RuntimeError(f'The specimen renderer requires {executable}')
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with TTFont(sources[0]) as font:
        version = font['name'].getDebugName(5).removeprefix('Version ')
        required = {'ss02', 'ss03', 'ss04', 'ss05', 'cv01', 'cv02', 'ss08'}
        available = {record.FeatureTag for record in font['GSUB'].table.FeatureList.FeatureRecord}
        if missing := required-available:
            raise ValueError('The complete specimen needs the current mathematical features: '+', '.join(sorted(missing)))
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', json.loads((ROOT / 'sources/source-lock.json').read_text())['source_date_epoch']))
    environment = os.environ.copy()
    environment.update(SOURCE_DATE_EPOCH=str(epoch), FORCE_SOURCE_DATE='1',
                       TEXMFVAR=str(ROOT / 'build/mathfonts/texmfvar'))
    text = TEMPLATE.read_text().replace('@@FONT_DIRECTORY@@', str(static)).replace('@@VERSION@@', version)
    (work / 'math.tex').write_text(text)
    for source in sources:
        print('cache', source.name, flush=True)
        warm_font(source, work, environment)
    print('typeset complete specimen', flush=True)
    run(['lualatex', '-interaction=nonstopmode', '-halt-on-error', 'math.tex'], work, environment, work / 'run.log')
    log = (work / 'math.log').read_text(errors='replace')
    if 'Missing character:' in log:
        raise RuntimeError(f'The specimen has missing glyphs; see {work / "math.log"}')
    if 'LaTeX Font Warning:' in log:
        raise RuntimeError(f'The specimen has a font-shape warning or substitution; see {work / "math.log"}')
    if re.search(r'Package fontspec Warning:.*?(?:not available|not found|substitut)', log, re.S):
        raise RuntimeError(f'The specimen could not select a requested font feature; see {work / "math.log"}')
    if 'Overfull \\hbox' in log or 'Overfull \\vbox' in log:
        raise RuntimeError(f'The specimen overflows its page; see {work / "math.log"}')
    pdf = work / 'math.pdf'
    info = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, text=True, check=True).stdout
    if not re.search(r'^Pages:\s+1$', info, re.M):
        raise RuntimeError('The complete specimen must fit on one page')
    font_report = subprocess.run(['pdffonts', str(pdf)], capture_output=True, text=True, check=True).stdout
    embedded_fonts = [line.split()[0].split('+')[-1] for line in font_report.splitlines()[2:] if line.strip()]
    if not embedded_fonts or any(not name.startswith('Anodyne-') for name in embedded_fonts):
        raise RuntimeError('The complete specimen must use Anodyne throughout: '+', '.join(embedded_fonts))
    with tempfile.TemporaryDirectory(prefix='.math-specimen-', dir=output) as temporary:
        stage = Path(temporary)
        shutil.copyfile(pdf, stage / 'math.pdf')
        run(['pdftocairo', '-svg', str(pdf), str(stage / 'math.svg')], work, environment, work / 'svg.log')
        run(['pdftoppm', '-png', '-singlefile', '-r', str(dpi), str(pdf), str(stage / 'math')],
            work, environment, work / 'png.log')
        manifest = {'version': version, 'source_date_epoch': epoch, 'dpi': dpi,
                    'template_sha256': digest(TEMPLATE),
                    'font_sha256': {p.name: digest(p) for p in sources},
                    'embedded_fonts': sorted(set(embedded_fonts)),
                    'attribution': ATTRIBUTION,
                    'outputs': {p.name: digest(p) for p in sorted(stage.iterdir())}}
        (stage / 'math-source.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        for path in stage.iterdir():
            path.replace(output / path.name)
    print('Specimen:', output / 'math.png', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fonts', type=Path, default=ROOT / 'fonts')
    parser.add_argument('--out', type=Path, default=ROOT / 'images')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/math-specimen')
    parser.add_argument('--dpi', type=int, default=300)
    args = parser.parse_args()
    if not 96 <= args.dpi <= 600:
        parser.error('--dpi must be between 96 and 600')
    render(args.fonts, args.out, args.work, args.dpi)


if __name__ == '__main__':
    main()
