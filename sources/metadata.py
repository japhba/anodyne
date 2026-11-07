"""Final metrics and style metadata; does not change source outlines or spacing."""
from __future__ import annotations

import math

from fontTools.otlLib.builder import buildStatTable

WIDTH_LABELS = {'ExtraCondensed': 'XCond', 'SemiCondensed': 'SCond', 'Condensed': 'Cond'}


def compact_width_label(label):
    for full, compact in WIDTH_LABELS.items():
        label = label.replace(full, compact)
    return label


def compact_instance_names(font):
    """Keep legacy Windows family+style combinations within 31 characters."""
    identifiers = {instance.subfamilyNameID for instance in font['fvar'].instances}
    for record in font['name'].names:
        if record.nameID in identifiers:
            text = compact_width_label(record.toUnicode())
            record.string = text.encode(record.getEncoding())


def variation_bounds(font):
    """Conservative glyph envelope over the supported variation space.

    Every gvar support scalar lies in [0, 1]. Summing positive and negative
    coordinate deltas separately therefore bounds all instances, including
    sparse support intersections. IUP deltas lie between explicit deltas.
    Composite envelopes also include varying child shapes and offsets.
    """
    glyf = font['glyf']
    variations = font['gvar'].variations if 'gvar' in font else {}
    cache, active = {}, set()

    def bounds(name):
        if name in cache:
            return cache[name]
        if name in active:
            raise ValueError(f'Cyclic glyph component: {name}')
        active.add(name)
        glyph = glyf[name]
        glyph.recalcBounds(glyf)
        result = None
        if glyph.isComposite():
            shifts = [[0, 0, 0, 0] for _ in glyph.components]
            for variation in variations.get(name, []):
                for index, delta in enumerate(variation.coordinates[:len(shifts)]):
                    if delta is not None:
                        dx, dy = delta
                        shifts[index][0] += min(0, dx)
                        shifts[index][1] += min(0, dy)
                        shifts[index][2] += max(0, dx)
                        shifts[index][3] += max(0, dy)
            for component, shift in zip(glyph.components, shifts):
                child_name, matrix = component.getComponentInfo()
                child = bounds(child_name)
                if child is None:
                    continue
                xx, xy, yx, yy, dx, dy = matrix
                points = [(xx * x + yx * y + dx, xy * x + yy * y + dy)
                          for x in (child[0], child[2]) for y in (child[1], child[3])]
                box = (min(p[0] for p in points) + shift[0], min(p[1] for p in points) + shift[1],
                       max(p[0] for p in points) + shift[2], max(p[1] for p in points) + shift[3])
                if result is None:
                    result = box
                else:
                    result = (min(result[0], box[0]), min(result[1], box[1]),
                              max(result[2], box[2]), max(result[3], box[3]))
        elif glyph.numberOfContours > 0:
            shifts = [0, 0, 0, 0]
            count = len(glyph.coordinates)
            for variation in variations.get(name, []):
                deltas = [p for p in variation.coordinates[:count] if p is not None]
                if not deltas:
                    continue
                shifts[0] += min(0, min(p[0] for p in deltas))
                shifts[1] += min(0, min(p[1] for p in deltas))
                shifts[2] += max(0, max(p[0] for p in deltas))
                shifts[3] += max(0, max(p[1] for p in deltas))
            result = (glyph.xMin + shifts[0], glyph.yMin + shifts[1],
                      glyph.xMax + shifts[2], glyph.yMax + shifts[3])
        active.remove(name)
        cache[name] = result
        return result

    boxes = [box for name in font.getGlyphOrder() if (box := bounds(name)) is not None]
    return (math.floor(min(box[1] for box in boxes)), math.ceil(max(box[3] for box in boxes))) if boxes else (0, 0)


def finalize_metrics(font, clip_bounds=None, reset_clip=False):
    """Keep text line spacing stable while making raster clipping bounds safe."""
    font['maxp'].recalc(font)
    head, os2, hhea = font['head'], font['OS/2'], font['hhea']
    if clip_bounds is None:
        clip_bounds = getattr(font, '_anodyne_clip_bounds', None) if not reset_clip else None
        if clip_bounds is None:
            clip_bounds = variation_bounds(font) if 'fvar' in font else (head.yMin, head.yMax)
    font._anodyne_clip_bounds = tuple(clip_bounds)
    ymin = min(head.yMin, clip_bounds[0])
    ymax = max(head.yMax, clip_bounds[1])
    os2.usWinAscent = min(65535, max(0 if reset_clip else os2.usWinAscent, math.ceil(ymax)))
    os2.usWinDescent = min(65535, max(0 if reset_clip else os2.usWinDescent, math.ceil(-ymin)))
    os2.fsSelection |= 0x80  # OpenType requires typographic line metrics for VFs.
    # Preserve the existing typographic text line height in both metric systems.
    hhea.ascent, hhea.descent, hhea.lineGap = os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap
    angle = font['post'].italicAngle
    hhea.caretSlopeRise = head.unitsPerEm if angle else 1
    hhea.caretSlopeRun = round(math.tan(math.radians(-angle)) * head.unitsPerEm) if angle else 0
    hhea.advanceWidthMax = max(advance for advance, _ in font['hmtx'].metrics.values())
    os2.recalcAvgCharWidth(font)
    for name, attribute in (('x', 'sxHeight'), ('H', 'sCapHeight')):
        if name in font['glyf'] and hasattr(os2, attribute):
            glyph = font['glyf'][name]
            if glyph.numberOfContours != 0:
                setattr(os2, attribute, glyph.yMax)


def static_stat(font, weight, width=100, grade=0, italic=False):
    weights = {100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular',
               500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black'}
    widths = {62.5: 'XCond', 75: 'Cond', 87.5: 'SCond', 100: 'Normal'}
    axes = []
    for tag, name, value, label, normal in (
        ('wght', 'Weight', weight, weights.get(weight, f'Weight {weight:g}'), 400),
        ('wdth', 'Width', width, widths.get(width, f'Width {width:g}'), 100),
        ('GRAD', 'Grade', grade, 'Normal' if grade == 0 else f'Grade {grade:g}', 0),
        ('ital', 'Italic', int(italic), 'Italic' if italic else 'Roman', 0),
    ):
        axes.append(dict(tag=tag, name=name, values=[dict(value=value, name=label, flags=2 if value == normal else 0)]))
    buildStatTable(font, axes, elidedFallbackName='Regular')
