#!/usr/bin/env python3
"""Create a math-capable static Anodyne face at any supported axis location."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

import build
from masters import normalize_timestamp

ROOT = Path(__file__).resolve().parents[1]


def number(value):
    return f'{value:g}'


def instance_name(weight, width, grade, italic=False):
    # Distinct PostScript names allow several axis instances in one TeX document.
    values = '-'.join(f'{tag}{number(value).replace("-", "m").replace(".", "p")}'
                      for tag, value in (('w', weight), ('wd', width), ('g', grade)))
    return f'Anodyne-{values}' + ('-Italic' if italic else '')


def create_instance(source=None, weight=400, width=100, grade=0, italic=False, output=None):
    """Return an independent static font; optionally save it to `output`."""
    if source is None:
        filename = 'Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf'
        source = ROOT / 'fonts/variable' / filename
    variable = copy.deepcopy(source) if isinstance(source, TTFont) else TTFont(source)
    italic = bool(italic or variable['head'].macStyle & 2 or variable['post'].italicAngle)
    if 'fvar' not in variable:
        raise ValueError('A variable Anodyne source is required')
    values = {'wght': float(weight), 'wdth': float(width), 'GRAD': float(grade)}
    axes = {axis.axisTag: axis for axis in variable['fvar'].axes}
    for tag, value in values.items():
        axis = axes[tag]
        if not math.isfinite(value) or not axis.minValue <= value <= axis.maxValue:
            raise ValueError(f'{tag} must be between {axis.minValue:g} and {axis.maxValue:g}')
    font = instantiateVariableFont(variable, values, inplace=True, updateFontNames=False)
    font.flavor = None  # A WOFF2 input still produces the promised desktop TTF.
    build.refresh_math_metrics(font)
    if 'STAT' in font:
        del font['STAT']
    ps_name = instance_name(weight, width, grade, italic)
    style = 'Bold Italic' if weight >= 700 and italic else 'Bold' if weight >= 700 else 'Italic' if italic else 'Regular'
    family = f'Anodyne w{number(weight)} wd{number(width)} g{number(grade)}'
    build.set_names(font, style, ps_name.removeprefix('Anodyne-'), False)
    for name_id, value in ((1, family), (2, style), (3, f'{build.VERSION};OLYX;{ps_name}'),
                           (4, family + (' Italic' if italic else '')), (6, ps_name),
                           (16, family), (17, style)):
        for platform, encoding, language in ((3, 1, 0x409), (1, 0, 0)):
            font['name'].setName(value, name_id, platform, encoding, language)
    font['OS/2'].usWeightClass = round(weight)
    font['OS/2'].usWidthClass = min(((62.5, 2), (75, 3), (87.5, 4), (100, 5)), key=lambda x: abs(x[0] - width))[1]
    font['OS/2'].fsSelection = (font['OS/2'].fsSelection & ~0x61) | (0x20 if weight >= 700 else 0) | (0x1 if italic else 0) | (0x40 if weight < 700 and not italic else 0)
    font['head'].macStyle = (1 if weight >= 700 else 0) | (2 if italic else 0)
    from metadata import static_stat
    static_stat(font, weight, width, grade, italic)
    normalize_timestamp(font)
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        font.save(output)
    return font


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='variable TTF or WOFF2 source; defaults to the distributed face')
    parser.add_argument('--weight', type=float, default=400)
    parser.add_argument('--width', type=float, default=100)
    parser.add_argument('--grade', type=float, default=0)
    parser.add_argument('--italic', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / 'build/instances' / f'{instance_name(args.weight, args.width, args.grade, args.italic)}.ttf'
    font = create_instance(args.source, args.weight, args.width, args.grade, args.italic, output)
    print(json.dumps({'path': str(output), 'family': font['name'].getDebugName(1),
                      'postscript_name': font['name'].getDebugName(6)}))


if __name__ == '__main__':
    main()
