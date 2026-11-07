#!/usr/bin/env python3
"""Draw feature/axis proofs and typeset final-geometry math instances with LuaLaTeX."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import shutil
import subprocess

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

from build import VERSION
from instance import create_instance

ROOT = Path(__file__).resolve().parents[1]
FEATURES = [
    ('ss02', 'Upright integrals', '∫∮∭'),
    ('ss03', 'Slanted inequalities', '≤≥'),
    ('ss04', 'Compact set symbols', '∈∉∋∖∣∥'),
    ('ss05', 'Vertical negations', '≠∉⊄'),
    ('cv01', 'Oval empty set', '∅'),
    ('cv02', 'Lowered-bar hbar', 'ℏ'),
]
LOCATIONS = [
    ('Regular', 400, 100, 0),
    ('ThinLightGrade', 100, 100, -100),
    ('BlackDarkGrade', 900, 100, 150),
    ('ExtraCondensed', 400, 62.5, 0),
    ('DarkGrade', 400, 100, 150),
    ('CondensedBold', 700, 75, 0),
]


def glyph_run(tt, font, text, x, y, scale, features=None, color='#152f35'):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features or {})
    names = tt.getGlyphOrder()
    gs = tt.getGlyphSet(location=dict(zip((axis.axisTag for axis in tt['fvar'].axes), font.get_var_coords_design())))
    paths, cursor = [], 0
    for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
        pen = SVGPathPen(gs)
        gs[names[info.codepoint]].draw(pen)
        paths.append(f'<path d="{pen.getCommands()}" transform="translate({x + (cursor + position.x_offset) * scale:g},{y - position.y_offset * scale:g}) scale({scale},-{scale})" fill="{color}"/>')
        cursor += position.x_advance
    return '\n'.join(paths)


def svg_proofs(font_path, output):
    tt = TTFont(font_path)
    font = hb.Font(hb.Face(font_path.read_bytes()))
    font.set_variations({'wght': 400, 'wdth': 100, 'GRAD': 0})
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="900" viewBox="0 0 1040 900">',
             '<rect width="1040" height="900" fill="#fafaf8"/>',
             '<style>text{font-family:sans-serif;fill:#34454b}.tag{font-size:15px}.title{font-size:21px}</style>',
             f'<text x="32" y="38" font-size="28">Anodyne {VERSION} · mathematical choices</text>',
             '<text x="400" y="74" class="tag">Default</text><text x="700" y="74" class="tag">Alternate</text>']
    for index, (tag, label, chars) in enumerate(FEATURES):
        top = 98 + index * 128
        lines.append(f'<line x1="32" y1="{top}" x2="1008" y2="{top}" stroke="#d7dddc"/>')
        lines.append(f'<text x="32" y="{top+46}" class="title">{html.escape(label)}</text>')
        lines.append(f'<text x="32" y="{top+75}" class="tag">{tag}</text>')
        lines.append(glyph_run(tt, font, chars, 400, top + 93, .076, color='#7c8587'))
        lines.append(glyph_run(tt, font, chars, 700, top + 93, .076, {tag: 1}))
    lines.append('</svg>')
    (output / 'features.svg').write_text('\n'.join(lines))
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="920" viewBox="0 0 1300 920">',
             '<rect width="1300" height="920" fill="#fafaf8"/>',
             '<style>text{font-family:sans-serif;fill:#34454b}</style>',
             f'<text x="30" y="42" font-size="29">Anodyne {VERSION} · weight, width and grade in maths</text>']
    for index, (label, weight, width, grade) in enumerate(LOCATIONS):
        y = 117 + index * 130
        font.set_variations({'wght': weight, 'wdth': width, 'GRAD': grade})
        lines.append(f'<text x="30" y="{y}" font-size="20">{label}</text>')
        lines.append(f'<text x="30" y="{y+28}" font-size="15">wght {weight} · wdth {width} · GRAD {grade}</text>')
        lines.append(glyph_run(tt, font, 'Hox 𝑥𝑦𝛼𝛽 ∑∫√≤∅ℏ', 325, y + 47, .064))
    lines.append('</svg>')
    (output / 'variations.svg').write_text('\n'.join(lines))
    tt.close()


def static_instance(source, destination, label, weight, width, grade):
    create_instance(source, weight=weight, width=width, grade=grade, output=destination)


FORMULAS = r'''
\[
\sum_{k=1}^{n}\frac{\alpha_k x^{2k}}{\sqrt{1+\beta_k^2}}
\leq\int_{-\infty}^{\infty}\left|\frac{\partial\Phi}{\partial t}\right|\,\mathrm{d}t
\]
\[
\left\{\left[\begin{matrix} a_1 & b_1 \\ a_2 & b_2 \\ a_3 & b_3 \end{matrix}\right]
\prod_{i=1}^{m}\lambda_i\right\}^{1/m}
\quad \sqrt[3]{\hbar+\varepsilon}\quad \hat{x}+\widehat{xyz}+\overbrace{a+b+c}^{n}
\]
\[
\left(\frac{\frac{x+1}{y+2}}{\frac{z+3}{w+4}}\right)
\quad\left\{\begin{matrix}1\\2\\3\\4\\5\\6\\7\\8\end{matrix}\right\}
\quad f^{a^b}_{i_j}+\int\!f'(x)\,\mathrm{d}x
\]
\[
A\cap B=\varnothing\quad A\cup B\subset C\quad x\notin A\quad a\nmid b\quad a\nparallel b
\]
\[
\mathcal{ABC}\quad\mathbb{RNC}\quad\mathfrak{g}\quad \symbf{\alpha\beta x}\quad\symbfsf{ABCxyz}
\]
'''


def formula_pdf(font_path, output, label, weight, width, grade):
    folder = output / label
    folder.mkdir(parents=True, exist_ok=True)
    instance = folder / 'proof-font.ttf'
    static_instance(font_path, instance, label, weight, width, grade)
    tex = '\n'.join([
        r'\documentclass[border=12pt]{standalone}',
        r'\usepackage{amsmath}', r'\usepackage{unicode-math}',
        r'\tracinglostchars=3',
        r'\setmainfont{proof-font.ttf}[Path=./]',
        r'\setmathfont{proof-font.ttf}[Path=./]',
        r'\begin{document}\begin{minipage}{470pt}',
        f'Anodyne {VERSION}: {label} (weight {weight}, width {width}, grade {grade})',
        FORMULAS,
        r'\end{minipage}\end{document}',
    ])
    (folder / 'proof.tex').write_text(tex)
    environment = __import__('os').environ.copy()
    environment['TEXMFVAR'] = str(output / 'texmfvar')
    run = subprocess.run(['lualatex', '-interaction=nonstopmode', '-halt-on-error', 'proof.tex'],
                         cwd=folder, env=environment, capture_output=True, text=True)
    (folder / 'run.log').write_text(run.stdout + run.stderr)
    if run.returncode or not (folder / 'proof.pdf').exists():
        raise RuntimeError(f'LuaLaTeX failed for {label}; see {folder / "run.log"}')
    log = (folder / 'proof.log').read_text(errors='replace')
    if 'Missing character:' in log:
        raise RuntimeError(f'missing glyphs in {label}; see {folder / "proof.log"}')
    subprocess.run(['pdftoppm', '-png', '-singlefile', '-scale-to', '1600',
                    str(folder / 'proof.pdf'), str(folder / 'proof')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return {'label': label, 'wght': weight, 'wdth': width, 'GRAD': grade,
            'pdf': str(folder / 'proof.pdf'), 'missing_glyphs': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, default=ROOT / 'fonts')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/proofs')
    parser.add_argument('--svg-only', action='store_true')
    parser.add_argument('--only', help='one of ' + ', '.join(p[0] for p in LOCATIONS))
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    source = args.fonts / 'variable/Anodyne[GRAD,wdth,wght].ttf'
    svg_proofs(source, args.out)
    if not args.svg_only:
        if not shutil.which('lualatex'):
            parser.error('lualatex is required, or use --svg-only')
        results = []
        for location in LOCATIONS:
            if args.only and args.only != location[0]:
                continue
            print('typesetting', location[0], flush=True)
            results.append(formula_pdf(source, args.out, *location))
        (args.out / 'formula-checks.json').write_text(json.dumps(results, indent=2) + '\n')
    print('Proofs:', args.out)


if __name__ == '__main__':
    main()
