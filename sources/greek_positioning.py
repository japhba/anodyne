"""Position combining marks on Greek mathematical alphabet drawings.

Noto's mark lookups cover ordinary Greek. Mathematical Unicode alphabets and
Anodyne's named Greek alternatives need the same mark classes, positioned for
their actual outlines. Run after the native Noto master lookups are copied and
positioned; no outline or character substitution is performed here.
"""
from __future__ import annotations

import copy
import unicodedata

from fontTools.ttLib.tables import otTables as ot


GREEK_FEATURES = {f'ss{index:02d}' for index in range(8, 15)}
# These native symbols have no MarkBase entry. Give them native Greek mark
# conventions, calibrated to their own bounds, before extending math families.
ANCHOR_DONORS = {0x03F5: 0x03B5, 0x03F6: 0x03B5, 0x2202: 0x03B4, 0x2207: 0x0394}
ABOVE_COMBINING_CLASSES = {214, 216, 228, 230, 232, 234}


def is_greek(codepoint):
    return 0x0370 <= codepoint <= 0x03FF or 0x1F00 <= codepoint <= 0x1FFF or codepoint in (0x2202, 0x2207)


def greek_relations(font):
    """Find actual glyph relations, retaining every Greek variant character."""
    cmap = font.getBestCmap()
    relations = {}
    for codepoint, target in sorted(cmap.items()):
        decomposition = unicodedata.decomposition(chr(codepoint)).split()
        if len(decomposition) != 2 or decomposition[0] != '<font>':
            continue
        base = int(decomposition[1], 16)
        if is_greek(base) and base in cmap and target != cmap[base]:
            relations.setdefault(target, cmap[base])
    greek_names = {name for codepoint, name in cmap.items() if is_greek(codepoint)}
    if 'GSUB' in font:
        table = font['GSUB'].table
        for feature in table.FeatureList.FeatureRecord:
            if feature.FeatureTag not in GREEK_FEATURES:
                continue
            for index in feature.Feature.LookupListIndex:
                for subtable in table.LookupList.Lookup[index].SubTable:
                    subtable = getattr(subtable, 'ExtSubTable', subtable)
                    for source, target in getattr(subtable, 'mapping', {}).items():
                        if source in greek_names and source != target:
                            relations.setdefault(target, source)
    return relations


def extend_greek_mark_anchors(font):
    """Add native mark classes at outline-relative Greek/math anchor positions.

    Existing anchors remain authoritative. Missing ordinary Greek mark classes
    use case-matched native alpha anchors, calibrated to that glyph's bounds.
    Newly added BaseRecords are sorted with their coverage by GlyphID, and
    their glyphs are classified as bases in GDEF. Repeated calls are idempotent.
    """
    import build
    if 'GPOS' not in font or not font['GPOS'].table.LookupList:
        return {'added_records': 0, 'updated_records': 0, 'base_glyphs': 0}
    cmap = font.getBestCmap()
    order = font.getReverseGlyphMap()
    bounds = {}
    mark_classes = {}
    for codepoint, name in cmap.items():
        combining = unicodedata.combining(chr(codepoint))
        if combining:
            mark_classes.setdefault(name, set()).add(combining)
    math_accents = {}
    if 'MATH' in font:
        info = font['MATH'].table.MathGlyphInfo
        accents = getattr(info, 'MathTopAccentAttachment', None)
        if accents and accents.TopAccentCoverage:
            math_accents = {name: record.Value for name, record in
                            zip(accents.TopAccentCoverage.glyphs, accents.TopAccentAttachment)}

    def glyph_bounds(name):
        if name not in bounds:
            bounds[name] = build._glyph_bounds(font, name)
        return bounds[name]

    def remap(record, source, target, above_classes, use_math=False):
        old, new = glyph_bounds(source), glyph_bounds(target)
        if old is None or new is None:
            return None
        record = copy.deepcopy(record)
        for index, anchor in enumerate(record.BaseAnchor):
            build._map_anchor(anchor, old, new)
            if anchor is not None and use_math and index in above_classes and target in math_accents:
                # Authored upper-ink attachments also govern typed accents on
                # narrow iota and shared Latin/Greek forms such as lambda/rho.
                anchor.XCoordinate = round(math_accents[target])
        return record

    donors = {cmap[target]: cmap[source] for target, source in ANCHOR_DONORS.items()
              if target in cmap and source in cmap and cmap[target] != cmap[source]}
    relations = greek_relations(font)
    needed = set(relations.values()) | set(donors.values())
    case_donors = {}
    for codepoint, target in sorted(cmap.items()):
        if target not in needed or codepoint in ANCHOR_DONORS or not is_greek(codepoint):
            continue
        category = unicodedata.category(chr(codepoint))
        donor = cmap.get(0x0391 if category in ('Lu', 'Lt') else 0x03B1) if category in ('Lu', 'Ll', 'Lt') else None
        if donor and donor != target:
            case_donors.setdefault(target, donor)
    added, updated, base_names = 0, 0, set()
    for lookup in font['GPOS'].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            subtable = getattr(subtable, 'ExtSubTable', subtable)
            if subtable.__class__.__name__ != 'MarkBasePos':
                continue
            classes = {}
            for name, mark in zip(subtable.MarkCoverage.glyphs, subtable.MarkArray.MarkRecord):
                classes.setdefault(mark.Class, set()).update(mark_classes.get(name, set()))
            above_classes = {index for index, values in classes.items()
                             if values and values.issubset(ABOVE_COMBINING_CLASSES)}
            records = dict(zip(subtable.BaseCoverage.glyphs, subtable.BaseArray.BaseRecord))
            changed = False
            work = [(target, source, False) for target, source in list(case_donors.items()) + list(donors.items())]
            work += [(target, source, True) for target, source in relations.items()]
            for target, source, use_math in work:
                if source not in records:
                    continue
                if target in records and all(anchor is not None for anchor in records[target].BaseAnchor):
                    continue
                record = remap(records[source], source, target, above_classes, use_math)
                if record is None:
                    continue
                if target in records:
                    changed_anchors = 0
                    for index, anchor in enumerate(record.BaseAnchor):
                        if records[target].BaseAnchor[index] is None and anchor is not None:
                            records[target].BaseAnchor[index] = anchor
                            changed_anchors += 1
                    if not changed_anchors:
                        continue
                    updated += 1
                else:
                    records[target] = record
                    added += 1
                base_names.add(target)
                changed = True
            if changed:
                names = sorted(records, key=order.__getitem__)
                subtable.BaseCoverage.glyphs = names
                subtable.BaseArray.BaseRecord = [records[name] for name in names]
                subtable.BaseArray.BaseCount = len(names)
    if base_names and 'GDEF' in font:
        table = font['GDEF'].table
        if table.GlyphClassDef is None:
            table.GlyphClassDef = ot.ClassDef()
            table.GlyphClassDef.classDefs = {}
        table.GlyphClassDef.classDefs.update({name: 1 for name in base_names})
    return {'added_records': added, 'updated_records': updated, 'base_glyphs': len(base_names)}
