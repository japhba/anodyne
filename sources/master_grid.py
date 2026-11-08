"""One canonical grid derivation for cold imports and edited-source migrations.

Normal-width anchors are quantized before width/grade derivation. This makes a
persisted integer UFO anchor an honest input to the same algorithm as a cold
import, rather than quietly reusing different pre-rounding fitting coordinates.
"""
from __future__ import annotations

import copy
import gc
import os

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor, InstanceDescriptor
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools import varLib


def quantize(outline):
    import build
    return build.Outline(
        [[(round(x), round(y), on) for x, y, on in contour] for contour in outline.contours],
        [(name, round(x), round(y), copy.deepcopy(transform)) for name, x, y, transform in outline.components],
        max(0, round(outline.adv)))


def quantize_anchors(normal):
    """Persist the same integer donor geometry before any derived alphabet."""
    for weight, drawings in normal.items():
        normal[weight] = {name: quantize(outline) for name, outline in drawings.items()}


def write_outlines(font, drawings):
    """Write all children before calculating final composite side bearings."""
    import build
    for name, outline in drawings.items():
        build.write(font, name, outline)
    # A parent's xMin can change when its component is written later in the
    # glyph order. The old one-pass writer left stale hmtx side bearings there.
    for name in drawings:
        glyph = font['glyf'][name]
        glyph.recalcBounds(font['glyf'])
        advance, _ = font['hmtx'][name]
        font['hmtx'][name] = advance, glyph.xMin if glyph.numberOfContours else 0


def monospace_names(reference):
    """Find the semantic mono family, including optical and Greek alternates."""
    names = {name for cp, name in reference.getBestCmap().items()
             if 0x1D670 <= cp <= 0x1D6A3 or 0x1D7F6 <= cp <= 0x1D7FF}
    names.update(name for name in reference.getGlyphOrder() if '.grk.monospace' in name)
    if 'GSUB' not in reference:
        return names
    changed = True
    while changed:
        changed = False
        for lookup in reference['GSUB'].table.LookupList.Lookup:
            for subtable in lookup.SubTable:
                subtable = getattr(subtable, 'ExtSubTable', subtable)
                for source, target in getattr(subtable, 'mapping', {}).items():
                    if source in names and target not in names:
                        names.add(target); changed = True
                for source, targets in getattr(subtable, 'alternates', {}).items():
                    if source in names:
                        added = set(targets) - names
                        names.update(added); changed = changed or bool(added)
    return names


def normalize_monospace(normal, reference, cell=680):
    """Keep every math mono letter/digit in one cell through all weight anchors.

    Noto Math itself uses 680 for Latin letters and 600 for mono digits. We keep
    its ink designs but explicitly unify their metrics. Overwide extrapolated
    Black drawings receive only the horizontal fit needed to retain a small
    inter-character gap. Components are flattened before any variable fit.
    """
    import build
    names = monospace_names(reference)
    report = []
    for weight, drawings in normal.items():
        def flattened(name, stack=()):
            if name in stack:
                raise ValueError(f'Cyclic mono components: {name}')
            outline = drawings[name]
            if not outline.components:
                return outline.copy()
            contours = []
            for component, dx, dy, transform in outline.components:
                child = flattened(component, stack + (name,))
                matrix = transform or ((1, 0), (0, 1))
                contours.extend([[(x * matrix[0][0] + y * matrix[1][0] + dx,
                                    x * matrix[0][1] + y * matrix[1][1] + dy, on)
                                   for x, y, on in contour] for contour in child.contours])
            return build.Outline(contours, adv=outline.adv)
        # Flatten first so a parent never sees a child that was already shifted.
        originals = {name: flattened(name) for name in names}
        for name, outline in originals.items():
            old_advance = outline.adv
            shift = (cell - old_advance) / 2
            scale = 1.0
            if outline.contours:
                left, _, right, _ = build.bbox(outline.contours)
                width = right - left
                if width > cell:
                    scale = (cell - 16) / width
                    origin = (left + right) / 2
                    contours = [[((x - origin) * scale + cell / 2, y, on) for x, y, on in contour]
                                for contour in outline.contours]
                else:
                    # Retain native placement where possible, just correcting
                    # overhangs introduced by an inconsistent former advance.
                    shift = max(shift, -left)
                    shift = min(shift, cell - right)
                    contours = [[(x + shift, y, on) for x, y, on in contour] for contour in outline.contours]
                drawings[name] = build.Outline(contours, adv=cell)
            else:
                drawings[name] = build.Outline(adv=cell)
            report.append({'glyph': name, 'weight': weight, 'old_advance': old_advance,
                           'new_advance': cell, 'horizontal_fit': scale})
    return report


def graded(drawings, weight, grade):
    import build
    target = max(build.WEIGHTS[0], min(build.WEIGHTS[-1], weight + grade))
    lo = max(w for w in build.WEIGHTS if w <= target)
    hi = min(w for w in build.WEIGHTS if w >= target)
    fraction = 0 if lo == hi else (build.mapped_weight(target) - build.mapped_weight(lo)) / (build.mapped_weight(hi) - build.mapped_weight(lo))
    for name, base in drawings[weight].items():
        candidate = drawings[lo][name] if lo == hi else build.lerp(drawings[lo][name], drawings[hi][name], fraction)
        yield name, build.grade_outline(base, candidate)


def build_grid(normal, regular, bold, noto, noto_c, italic, directory,
               masters_dir=None, prepare_only=False, zero_sources=None,
               forced_width_names=()):
    """Derive condensed/grade masters and compile/export the common designspace."""
    import build
    from condense import Policy
    style = 'Italic' if italic else 'Roman'
    order = regular.getGlyphOrder()
    for weight in build.WEIGHTS:
        if set(normal[weight]) != set(order):
            raise ValueError(f'{style} {weight}: normal anchor glyph set differs from the reference')
        normal[weight] = {name: quantize(normal[weight][name]) for name in order}
    mono_report = normalize_monospace(normal, regular)
    for weight in build.WEIGHTS:
        normal[weight] = {name: quantize(normal[weight][name]) for name in order}
    build.log(f'[{style}] normalized {len(mono_report)} math mono anchor cells to 680 units')
    # Rebase measurements once when moving the source Regular onto the integer
    # anchor. Migration inputs already have these measurements at that geometry.
    original = copy.deepcopy(regular)
    write_outlines(regular, normal[400])
    build.refresh_math_metrics(regular, original)
    del original
    policy = Policy(regular, noto, noto_c)
    native_names = set(noto[400].getGlyphOrder())
    native = set()
    for name in order:
        # Static mathematical letterlikes can match Noto at Regular while
        # their repaired weight/width drawings intentionally vary. Copying the
        # unchanged native condensed glyph would discard that variation.
        if name in native_names and name not in forced_width_names:
            source = build.read(noto[400], name)
            drawing = normal[400][name]
            if build.structure(source) == build.structure(drawing) and source.contours == drawing.contours and source.components == drawing.components:
                native.add(name)
    condensed = {weight: {} for weight in build.WEIGHTS}
    for weight in build.WEIGHTS:
        for name in order:
            special = zero_sources.condensed(name, weight) if zero_sources is not None else None
            if special is not None:
                condensed[weight][name] = quantize(special)
            elif name in native:
                condensed[weight][name] = quantize(build.read(noto_c[weight], name))
            else:
                condensed[weight][name] = quantize(policy.draw(name, normal[weight][name], weight))
    build.log(f'[{style}] condensed: {len(native)} native Noto glyphs; other drawings use local calibrated strokes')
    for tag in ('fpgm', 'prep', 'cvt ', 'hdmx', 'LTSH', 'VDMX', 'DSIG', 'STAT'):
        if tag in regular:
            del regular[tag]
    paths = {}
    for width, outlines, positions in ((100, normal, noto), (build.WDTH_MIN, condensed, noto_c)):
        for weight in build.WEIGHTS:
            width_scale = 1 if width == 100 else sum(noto_c[weight]['hmtx'][c][0] / noto[weight]['hmtx'][c][0] for c in 'nohdeasu') / 8
            for grade in (0, build.GRAD_MIN, build.GRAD_MAX):
                font = copy.deepcopy(regular)
                drawings = outlines[weight] if grade == 0 else dict(graded(outlines, weight, grade))
                write_outlines(font, drawings)
                build.position_master(font, regular, positions[weight], width_scale)
                build.refresh_math_metrics(font, regular)
                from greek_positioning import extend_greek_mark_anchors
                extend_greek_mark_anchors(font)
                reorderGlyphs(font, font.getGlyphOrder())
                font['maxp'].recalc(font)
                path = os.path.join(directory, f'{style}-{weight}-{width}-{grade}.ttf')
                font.save(path)
                paths[(weight, width, grade)] = path
                build.log('master', os.path.basename(path))
    build.validate_master_compatibility(paths.values())
    for values in (normal, condensed):
        values.clear()
    gc.collect()
    document = DesignSpaceDocument()
    weight_axis = AxisDescriptor(); weight_axis.tag, weight_axis.name = 'wght', 'Weight'
    weight_axis.minimum, weight_axis.default, weight_axis.maximum = 100, 400, 900
    weight_axis.map = build.WEIGHT_MAP
    width_axis = AxisDescriptor(); width_axis.tag, width_axis.name = 'wdth', 'Width'
    width_axis.minimum, width_axis.default, width_axis.maximum = build.WDTH_MIN, 100, 100
    width_axis.map = build.WDTH_MAP
    grade_axis = AxisDescriptor(); grade_axis.tag, grade_axis.name = 'GRAD', 'Grade'
    grade_axis.minimum, grade_axis.default, grade_axis.maximum = build.GRAD_MIN, 0, build.GRAD_MAX
    document.addAxis(weight_axis); document.addAxis(width_axis); document.addAxis(grade_axis)
    design_weight, design_width = dict(build.WEIGHT_MAP), dict(build.WDTH_MAP)
    for (weight, width, grade), path in paths.items():
        source = SourceDescriptor()
        source.path = path
        source.location = {'Weight': design_weight[weight], 'Width': design_width[width], 'Grade': grade}
        source.copyInfo = source.copyLib = source.copyFeatures = source.copyGroups = (weight, width, grade) == (400, 100, 0)
        document.addSource(source)
    for width, width_name in build.WIDTHS:
        for weight, weight_name in build.INSTANCES:
            instance = InstanceDescriptor(); instance.familyName = build.FAMILY
            parts = [width_name, '' if weight_name == 'Regular' and (width_name or italic) else weight_name, 'Italic' if italic else '']
            instance.styleName = ' '.join(part for part in parts if part) or 'Regular'
            instance.location = {'Weight': design_weight[weight], 'Width': design_width[width], 'Grade': 0}
            document.addInstance(instance)
    if masters_dir:
        import masters
        masters.export_designspace(document, os.path.join(masters_dir, style), math_regular=regular, math_bold=bold)
    if prepare_only:
        return None, regular, bold
    variable, model, master_paths = varLib.build(document, exclude=['MVAR'], optimize=True)
    build.add_math_variations(variable, model, master_paths)
    return variable, regular, bold
