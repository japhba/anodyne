"""Browser math adapters for large operators that bypass OpenType GSUB.

Chromium selects large/stretchy operator glyphs from cmap before consulting
MATH. A small feature-specific variable font lets native MathML select the
upright integral and its proper display variants without changing Unicode.
"""
from __future__ import annotations

import copy
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

from masters import normalize_timestamp
from metadata import finalize_metrics


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


def feature_font(source, tag):
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
    options = subset.Options()
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.notdef_outline = True
    options.hinting = False
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=codepoints)
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
    for tag, suffix, family in (('ss02', 'upright', 'Upright'), ('ss01', 'chancery', 'Chancery')):
        for italic in (False, True):
            name = 'Anodyne-Italic[GRAD,wdth,wght].ttf' if italic else 'Anodyne[GRAD,wdth,wght].ttf'
            filename = f'anodyne-math-{suffix}' + ('-italic' if italic else '') + '.woff2'
            with TTFont(Path(flat) / name) as source:
                font = feature_font(source, tag)
                font.flavor = 'woff2'
                font.save(destination / filename)
            css.append(f'@font-face {{ font-family: "Anodyne Math {family}"; '
                       f'font-style: {"italic" if italic else "normal"}; '
                       'font-weight: 100 900; font-stretch: 62.5% 100%; font-display: swap; '
                       f'src: url("./{filename}") format("woff2"); }}')
    return css
