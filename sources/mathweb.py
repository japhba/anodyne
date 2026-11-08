"""Browser math adapters for large operators that bypass OpenType GSUB.

Chromium selects large/stretchy operator glyphs from cmap before consulting
MATH. A small feature-specific variable font lets native MathML select the
upright integral and its proper display variants without changing Unicode.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unicodedata

from fontTools import subset
from fontTools.ttLib import TTFont

from masters import normalize_timestamp
from metadata import finalize_metrics

ROOT = Path(__file__).resolve().parents[1]


def adapter_specs():
    greek = json.loads((ROOT / 'assets/greek-math-styles.json').read_text())
    return [
        {'tag': 'ss02', 'suffix': 'upright', 'family': 'Anodyne Math Upright'},
        {'tag': 'ss01', 'suffix': 'chancery', 'family': 'Anodyne Math Chancery'},
    ] + [dict(spec, greek=True) for spec in greek['styles'].values()]


def single_mapping(font, tag):
    mapping = {}
    table = font['GSUB'].table
    for feature in table.FeatureList.FeatureRecord:
        if feature.FeatureTag != tag:
            continue
        for index in feature.Feature.LookupListIndex:
            lookup = table.LookupList.Lookup[index]
            for subtable in lookup.SubTable:
                subtable = getattr(subtable, 'ExtSubTable', subtable)
                mapping.update(getattr(subtable, 'mapping', {}))
    return mapping


def feature_font(source, tag, *, retain_sources=False, retain_combining_marks=False, layout_features=None):
    """Preserve Unicode and MATH while making one feature the default cmap."""
    font = copy.deepcopy(source)
    mapping = single_mapping(font, tag)
    original = dict(font.getBestCmap())
    codepoints = {cp for cp, name in original.items() if name in mapping}
    if not codepoints:
        raise ValueError(f'No Unicode mappings found for {tag} in the built font')
    for table in font['cmap'].tables:
        for cp, name in list(getattr(table, 'cmap', {}).items()):
            if cp in codepoints:
                table.cmap[cp] = mapping[original[cp]]
    if retain_combining_marks:
        # Keep base and combining mark in one shaping font for Greek clusters
        # without a precomposed Unicode form; fallback faces cannot share GPOS.
        codepoints |= {cp for cp in original if unicodedata.category(chr(cp)).startswith('M')}
    options = subset.Options()
    options.layout_features = layout_features or ['*']
    options.name_IDs = ['*']
    options.notdef_outline = True
    options.hinting = False
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints,
                       glyphs={original[cp] for cp in codepoints} if retain_sources else [])
    subsetter.subset(font)
    if 'MATH' not in font:
        raise ValueError(f'The {tag} web font lost mathematical layout data')
    finalize_metrics(font, reset_clip=True)
    normalize_timestamp(font)
    return font


def upright_font(source):
    return feature_font(source, 'ss02')


def write_upright_font(source, destination):
    font = upright_font(source)
    font.flavor = 'woff2'
    font.save(destination)


def package_feature_fonts(flat, destination):
    destination = Path(destination)
    css = []
    for spec in adapter_specs():
        tag, suffix, family = spec['tag'], spec['suffix'], spec['family']
        for italic in (False, True):
            name = 'Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf'
            filename = f'anodyne-math-{suffix}' + ('-italic' if italic else '') + '.woff2'
            with TTFont(Path(flat) / name) as source:
                font = feature_font(source, tag, retain_sources=spec.get('greek', False),
                                    retain_combining_marks=spec.get('greek', False),
                                    layout_features=[tag, 'ssty', 'mark', 'mkmk', 'kern'] if spec.get('greek') else None)
                font.flavor = 'woff2'
                font.save(destination / filename)
            css.append(f'@font-face {{ font-family: "{family}"; '
                       f'font-style: {"italic" if italic else "normal"}; '
                       'font-weight: 100 900; font-stretch: 62.5% 100%; font-display: swap; '
                       f'src: url("./{filename}") format("woff2"); }}')
    return css
