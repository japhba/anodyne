"""Default text drawings and explicit access to the inherited forms.

The native J.salt drawings already have matching weight/width/grade masters and
mark anchors. Make them the Unicode defaults, retaining the descending J in
cv03. Square the tapered upper-left shoulder of t; cv04 restores the original
drawings, including accents and optical sizes. These changes run on each
compiled editable master, before variable-font interpolation.
"""
from __future__ import annotations

import copy

from mathfeatures import _copy_math_info, _register

FEATURES = {
    'cv03': {'name': 'Descending J', 'sample': 'J Ĵ',
             'description': 'Restore the inherited J with a descender instead of the baseline J.'},
    'cv04': {'name': 'Tapered t shoulder', 'sample': 't ţ ť ŧ',
             'description': 'Restore the tapered upper-left t join instead of the square shoulder.'},
}
SUFFIX = '.anodyne.tapered'


def _square_shoulder(font, name):
    """Straighten the two ramps, preserving the stem, crossbar and curved foot.

    Work on the largest contour, the t body in the native, accented and optical
    drawings. Intermediate quadratic points on the old straight ramps are
    retained as collinear points, so every source retains compatible topology.
    """
    glyph = font['glyf'][name]
    if glyph.isComposite() or glyph.numberOfContours <= 0:
        return False
    points = glyph.coordinates
    start = 0
    contours = []
    for end in glyph.endPtsOfContours:
        contours.append((start, list(points[start:end+1])))
        start = end+1
    offset, contour = max(contours, key=lambda item: max(y for x, y in item[1])-min(y for x, y in item[1]))
    top = max(y for x, y in contour)
    # The right arm supplies its top and bottom horizontal crossbar edges.
    horizontal = [(a, b) for a, b in zip(contour, contour[1:]+contour[:1])
                  if a[1] == b[1] and .60*top < a[1] < .90*top
                  and abs(a[0]-b[0]) > font['hmtx'][name][0]*.18]
    if len(horizontal) < 2:
        raise ValueError(f'{name}: cannot identify the native t crossbar')
    bar_top = max(a[1] for a, b in horizontal)
    bar_bottom = min(a[1] for a, b in horizontal)
    # Intersect the straight lower stem at two heights to retain italic shear.
    def left_at(y):
        xs = [a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
              for a, b in zip(contour, contour[1:]+contour[:1])
              if min(a[1], b[1]) <= y < max(a[1], b[1])]
        if len(xs) != 2:
            raise ValueError(f'{name}: ambiguous t stem at {y}')
        return min(xs)
    low, high = top*.40, top*.60
    shear = (left_at(high)-left_at(low))/(high-low)
    intercept = left_at(low)-shear*low
    top_left = min((i for i, (x, y) in enumerate(contour) if y == top),
                   key=lambda i: contour[i][0])
    old_cap = [x for x, y in contour if y == top]
    # Walk backwards from the ascender to the left end of the crossbar.
    run = []
    index = top_left
    for _ in contour:
        run.append(index)
        x, y = contour[index]
        if bar_bottom < y < bar_top and x-shear*y < intercept-5:
            break
        index = (index-1) % len(contour)
    else:
        raise ValueError(f'{name}: cannot identify the tapered t shoulder')
    run.reverse()
    # The first on-curve after the crossbar's left end is the stem junction.
    join = next(i for i in run[1:] if glyph.flags[offset+i] & 1)
    join_position = run.index(join)
    old_join_y = contour[join][1]
    start_x = contour[run[0]][0]-shear*contour[run[0]][1]
    for position, i in enumerate(run):
        x, y = contour[i]
        if position <= join_position:
            fraction = position/join_position
            new_y = bar_top
            new_x = start_x+(intercept-start_x)*fraction
        else:
            new_y = bar_top+(top-bar_top)*(y-old_join_y)/(top-old_join_y)
            new_x = intercept
        points[offset+i] = (round(new_x+shear*new_y), round(new_y))
    glyph.recalcBounds(font['glyf'])
    font['hmtx'][name] = (font['hmtx'][name][0], glyph.xMin)
    new_cap = [points[offset+i][0] for i, (x, y) in enumerate(contour) if y == top]
    return round((min(new_cap)+max(new_cap)-min(old_cap)-max(old_cap))/2)


def _move_upper_marks(font, shifts):
    """Keep accents above the new cap; leave foot and below marks in place."""
    for name, dx in shifts.items():
        glyph = font['glyf'][name]
        if glyph.isComposite():
            for component in glyph.components:
                if component.glyphName not in shifts and component.y > 0:
                    component.x += dx
    for lookup in font['GPOS'].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            sub = getattr(subtable, 'ExtSubTable', subtable)
            if sub.__class__.__name__ != 'MarkBasePos':
                continue
            for name, record in zip(sub.BaseCoverage.glyphs, sub.BaseArray.BaseRecord):
                if name in shifts:
                    record.BaseAnchor = copy.deepcopy(record.BaseAnchor)
                    for anchor in record.BaseAnchor:
                        if anchor is not None and anchor.YCoordinate > 500:
                            anchor.XCoordinate += shifts[name]


def _copy_positioning(font, mapping):
    """Give restored drawings the same kerning classes and mark anchors."""
    order = font.getReverseGlyphMap()
    if 'GDEF' in font:
        for attr in ('GlyphClassDef', 'MarkAttachClassDef'):
            classes = getattr(font['GDEF'].table, attr, None)
            if classes:
                classes.classDefs.update({dst: classes.classDefs[src] for src, dst in mapping.items()
                                          if src in classes.classDefs})
    def extend(coverage, records=None):
        if coverage is None:
            return records
        values = dict(zip(coverage.glyphs, records)) if records is not None else None
        names = set(coverage.glyphs)
        for src, dst in mapping.items():
            if src in names:
                if values is not None:
                    values[dst] = copy.deepcopy(values[src])
                names.add(dst)
        coverage.glyphs = sorted(names, key=order.__getitem__)
        return [values[name] for name in coverage.glyphs] if values is not None else None
    if 'GPOS' not in font:
        return
    for lookup in font['GPOS'].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            sub = getattr(subtable, 'ExtSubTable', subtable)
            for attr in ('ClassDef1', 'ClassDef2'):
                classes = getattr(sub, attr, None)
                if classes:
                    classes.classDefs.update({dst: classes.classDefs[src] for src, dst in mapping.items()
                                              if src in classes.classDefs})
            if sub.__class__.__name__ == 'MarkBasePos':
                sub.BaseArray.BaseRecord = extend(sub.BaseCoverage, sub.BaseArray.BaseRecord)
                sub.BaseArray.BaseCount = len(sub.BaseCoverage.glyphs)
            elif sub.__class__.__name__ == 'PairPos' and sub.Format == 1:
                for pair in sub.PairSet:
                    values = {record.SecondGlyph: record for record in pair.PairValueRecord}
                    for src, dst in mapping.items():
                        if src in values:
                            values[dst] = copy.deepcopy(values[src])
                            values[dst].SecondGlyph = dst
                    pair.PairValueRecord = [values[n] for n in sorted(values, key=order.__getitem__)]
                    pair.PairValueCount = len(pair.PairValueRecord)
                sub.PairSet = extend(sub.Coverage, sub.PairSet)
                sub.PairSetCount = len(sub.PairSet)
            elif sub.__class__.__name__ == 'PairPos':
                extend(sub.Coverage)
            elif sub.__class__.__name__ == 'SinglePos':
                if sub.Format == 1:
                    extend(sub.Coverage)
                else:
                    sub.Value = extend(sub.Coverage, sub.Value)
                    sub.ValueCount = len(sub.Value)


def apply_text_forms(font):
    """Apply to full Anodyne masters; leave small test/reference fonts alone."""
    if 'J.salt' not in font.getGlyphOrder():
        return {}
    if any(r.FeatureTag == 'cv03' for r in font['GSUB'].table.FeatureList.FeatureRecord):
        return {}  # Already processed, including when compiling an exported source.
    defaults = {'J': 'J.salt', 'Jcircumflex': 'Jcircumflex.salt'}
    defaults = {src: dst for src, dst in defaults.items() if dst in font['glyf']}
    for table in font['cmap'].tables:
        if table.isUnicode():
            table.cmap = {cp: defaults.get(name, name) for cp, name in table.cmap.items()}
    # Retain small caps and other ordinary substitutions for the native J.
    # Baseline J has no optical-size donors; using the descending optical J
    # would undo the user's default in superscripts and math scripts.
    gsub = font['GSUB'].table
    optical = {i for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == 'ssty'
               for i in r.Feature.LookupListIndex}
    for i, lookup in enumerate(gsub.LookupList.Lookup):
        if i in optical:
            continue
        for subtable in lookup.SubTable:
            sub = getattr(subtable, 'ExtSubTable', subtable)
            mapping = getattr(sub, 'mapping', {})
            mapping.update({dst: copy.deepcopy(mapping[src]) for src, dst in defaults.items()
                            if src in mapping and dst not in mapping})
    # These native simple drawings share the same anatomical t shoulder.
    bodies = [n for n in ('t', 'tcaron', 'tbar', 't.ssty1', 't.ssty2') if n in font['glyf']]
    affected = set(bodies)
    while True:
        parents = {name for name in font.getGlyphOrder() if font['glyf'][name].isComposite()
                   and any(c.glyphName in affected for c in font['glyf'][name].components)}
        if parents <= affected:
            break
        affected.update(parents)
    mapping = {name: name+SUFFIX for name in font.getGlyphOrder() if name in affected}
    order = list(font.getGlyphOrder())+list(mapping.values())
    for src, dst in mapping.items():
        font['glyf'][dst] = copy.deepcopy(font['glyf'][src])
        font['hmtx'][dst] = font['hmtx'][src]
        glyph = font['glyf'][dst]
        if glyph.isComposite():
            for component in glyph.components:
                component.glyphName = mapping.get(component.glyphName, component.glyphName)
    font.setGlyphOrder(order)
    font['glyf'].glyphOrder = font.getGlyphOrder()
    shifts = {name: _square_shoulder(font, name) for name in bodies}
    while len(shifts) < len(mapping):
        previous = len(shifts)
        for name in mapping:
            glyph = font['glyf'][name]
            if name not in shifts and glyph.isComposite():
                for component in glyph.components:
                    if component.glyphName in shifts:
                        shifts[name] = shifts[component.glyphName]
                        break
        if len(shifts) == previous:
            raise ValueError('An affected t composite has no source cap shift')
    _copy_positioning(font, mapping)
    _move_upper_marks(font, shifts)
    # Composite bounds need refreshing after their t component changes.
    for name in mapping:
        font['glyf'][name].recalcBounds(font['glyf'])
        font['hmtx'][name] = (font['hmtx'][name][0], font['glyf'][name].xMin)
    _copy_math_info(font, mapping)
    accents = font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
    original_accents = (dict(zip(accents.TopAccentCoverage.glyphs, accents.TopAccentAttachment))
                        if accents else {})
    _copy_math_info(font, defaults)
    if accents:
        records = dict(zip(accents.TopAccentCoverage.glyphs, accents.TopAccentAttachment))
        for src, dst in mapping.items():
            if src in original_accents:
                # The alternate is an exact original drawing. Keep its actual
                # authored attachment, rather than the generic ink centre.
                records[dst].Value = original_accents[src].Value
                records[dst].DeviceTable = copy.deepcopy(original_accents[src].DeviceTable)
        for name in shifts:
            if name in original_accents:
                anchor = native_top_anchor(font, name)
                records[name].Value = anchor.XCoordinate
                records[name].DeviceTable = copy.deepcopy(getattr(anchor, 'XDeviceTable', None))
        for src, dst in defaults.items():
            if src in original_accents:
                # Native GPOS already follows the actual weight/width/grade
                # stem. The inherited J MATH record was derived differently,
                # so translating it would carry its narrow-master error over.
                anchor = native_top_anchor(font, dst)
                records[dst].Value = anchor.XCoordinate
                records[dst].DeviceTable = copy.deepcopy(getattr(anchor, 'XDeviceTable', None))
    _register(font, 'cv03', {dst: src for src, dst in defaults.items()}, FEATURES['cv03'])
    _register(font, 'cv04', mapping, FEATURES['cv04'])
    return {'baseline_J': defaults, 'square_t': list(mapping)}


def native_top_anchor(font, name):
    """The authored native above-mark attachment, also used by math accents."""
    mark = font.getBestCmap()[0x0302]
    for lookup in font['GPOS'].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            sub = getattr(subtable, 'ExtSubTable', subtable)
            if (sub.__class__.__name__ == 'MarkBasePos' and name in sub.BaseCoverage.glyphs
                    and mark in sub.MarkCoverage.glyphs):
                index = sub.MarkArray.MarkRecord[sub.MarkCoverage.glyphs.index(mark)].Class
                anchor = sub.BaseArray.BaseRecord[sub.BaseCoverage.glyphs.index(name)].BaseAnchor[index]
                if anchor is not None:
                    return anchor
    raise ValueError(f'{name}: native above-mark anchor is missing')
