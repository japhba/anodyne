"""Calibrated condensed drawings for glyphs without native Noto width masters.

Native Noto glyphs bypass this module. Derived drawings use the corresponding
Noto character's advance ratio, their own measured stroke, and Noto's relative
stroke change. Counter/spacing compression and stroke restoration are solved
together so that compensating a stroke does not inflate the target advance.
These are compatible derived masters, not independently drawn optical masters.
"""
from __future__ import annotations

import math
import statistics
import unicodedata


# Lisnoti deliberately aligns the ordinary arithmetic/relation cells. Noto's
# minus width has a weight/width interaction unlike its plus/equal siblings;
# preserve the shared mathematical rhythm instead of importing that anomaly.
MATH_SIGNS = '+−=<>≤≥×÷±∓≠≈≡'


def _polygons(outline):
    """Sample quadratic contours without changing their editable point topology."""
    from build import pieces
    result = []
    for contour in outline.contours:
        start = next((i for i, point in enumerate(contour) if point[2]), None)
        if start is None:
            a, b = contour[-1], contour[0]
            run = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, True)] + list(contour)
        else:
            run = list(contour[start:]) + list(contour[:start])
        run.append(run[0])
        points = []
        for piece in pieces(run):
            if len(piece) == 2:
                points.append(piece[0])
            else:
                a, b, c = piece
                for index in range(8):
                    t = index / 8
                    points.append(((1-t)**2*a[0] + 2*t*(1-t)*b[0] + t*t*c[0],
                                   (1-t)**2*a[1] + 2*t*(1-t)*b[1] + t*t*c[1]))
        if points:
            result.append(points)
    return result


def measured_stroke(outline, reference_stem):
    """Robust interior horizontal stroke span, excluding dots and horizontal rules.

    The smallest ink span at each of seven interior heights identifies stems
    rather than counters. The median rejects individual bowls/joins. Very low
    glyphs have no useful vertical stem; they must not receive an l-sized offset.
    """
    if not outline.contours:
        return 0.0
    from build import bbox
    x0, y0, x1, y1 = bbox(outline.contours)
    if y1-y0 < .75 * reference_stem and x1-x0 > 2*(y1-y0):
        return 0.0
    polygons = _polygons(outline)
    spans = []
    for fraction in (.2, .3, .4, .5, .6, .7, .8):
        y = y0 + fraction * (y1 - y0)
        crossings = []
        for polygon in polygons:
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                if (a[1] <= y < b[1]) or (b[1] <= y < a[1]):
                    crossings.append(a[0] + (y-a[1]) * (b[0]-a[0]) / (b[1]-a[1]))
        crossings.sort()
        candidates = [b-a for a, b in zip(crossings[::2], crossings[1::2])
                      if .08 * reference_stem <= b-a <= 2 * reference_stem]
        if candidates:
            spans.append(min(candidates))
    return statistics.median(spans) if len(spans) >= 3 else 0.0


def measured_shear(outline):
    """Fit the centre line through the straight middle of an italic I drawing."""
    from build import bbox
    if not outline.contours:
        return 0.0
    _, y0, _, y1 = bbox(outline.contours)
    polygons = _polygons(outline)
    samples = []
    for fraction in (.3, .4, .5, .6, .7):
        y = y0 + fraction*(y1-y0)
        xs = []
        for polygon in polygons:
            for a, b in zip(polygon, polygon[1:]+polygon[:1]):
                if a[1] <= y < b[1] or b[1] <= y < a[1]:
                    xs.append(a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        if xs:
            samples.append((y, (min(xs)+max(xs))/2))
    if len(samples) < 3:
        return 0.0
    cy = statistics.mean(y for y, _ in samples)
    cx = statistics.mean(x for _, x in samples)
    denominator = sum((y-cy)**2 for y, _ in samples)
    slope = sum((y-cy)*(x-cx) for y, x in samples)/denominator if denominator else 0.0
    return slope if abs(slope) <= .5 else 0.0


def condense_outline(outline, width_ratio, stem_ratio, reference_stem, shear=0.0):
    """Condense counters/spacing, retain relative stroke weight and italic shear."""
    from build import Outline, bbox, embolden, sane
    if not 0 < width_ratio <= 1 or not 0 < stem_ratio:
        raise ValueError('Condensation requires positive ratios and cannot expand width')
    target_advance = outline.adv * width_ratio
    if outline.components:
        # Components already use their own condensed drawings. Preserve their
        # vertical offsets and the shear contribution to horizontal placement.
        return Outline(components=[(name, x*width_ratio + (1-width_ratio)*shear*y, y, transform)
                                   for name, x, y, transform in outline.components],
                       adv=target_advance)
    if not outline.contours:
        return Outline(adv=target_advance)
    x0, y0, x1, y1 = bbox(outline.contours)
    width, height = x1-x0, y1-y0
    # Small round dots are punctuation/accents, not little condensed letters.
    # Preserve their round ink and condense their placement and advance only.
    dots = []
    for contour in outline.contours:
        a, b, c, d = bbox([contour])
        dots.append(max(c-a, d-b) <= 2*reference_stem and .8 <= (c-a)/((d-b) or 1) <= 1.25)
    # Test separate contours too, so colons and ellipses retain circular dots.
    # Nested contours are counters (letters), not a collection of solid dots.
    boxes = [bbox([contour]) for contour in outline.contours]
    nested = any(a != b and a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
                 for a in boxes for b in boxes)
    if all(dots) and not nested:
        contours = []
        for contour, box in zip(outline.contours, boxes):
            shift = (width_ratio-1) * (box[0]+box[2]) / 2
            contours.append([(x+shift, y, on) for x, y, on in contour])
        return Outline(contours, adv=target_advance)
    stroke = measured_stroke(outline, reference_stem)
    effective_advance = outline.adv if outline.adv > stroke * 1.1 else width
    # k*(advance-stroke) + target_stroke = target_advance. Keeping the
    # advance target separate prevents stroke compensation undoing condensation.
    scale = width_ratio
    if stroke and effective_advance > stroke * 1.1:
        scale = (effective_advance*width_ratio - stroke*stem_ratio) / (effective_advance-stroke)
        scale = max(.1, min(1.0, scale))
    # Restore strokes in the upright coordinate system; offsetting an already
    # sheared outline changes its centre-line angle at the terminals.
    transformed = Outline([[(scale*(x-shear*y), y, on)
                            for x, y, on in contour] for contour in outline.contours],
                          adv=target_advance)
    offset = max(0.0, (stem_ratio-scale)*stroke/2)
    strength = 1.0
    candidate = embolden(transformed, offset, 0) if offset else transformed
    while not sane(transformed, candidate) and strength > 1/128:
        strength *= .75
        candidate = embolden(transformed, offset*strength, 0)
    if not sane(transformed, candidate):
        candidate = transformed
    # embolden moves the origin by its horizontal offset. Centre the ink's
    # additional extent inside the promised advance instead of growing spacing.
    applied = (candidate.adv-transformed.adv)/2
    candidate.contours = [[(x-applied+shear*y, y, on) for x, y, on in contour]
                          for contour in candidate.contours]
    candidate.adv = target_advance
    return candidate


class Policy:
    """Character-aware Noto width references, shared by cold build and migration."""
    def __init__(self, reference, noto, condensed):
        from build import measure_stem, read
        from mathletters import semantic_names
        self.semantic_math = semantic_names(reference)
        self.noto, self.condensed = noto, condensed
        self.stems = {weight: measure_stem(font) for weight, font in noto.items()}
        self.stem_ratios = {weight: measure_stem(condensed[weight])/stem
                            for weight, stem in self.stems.items()}
        self.fallback = {weight: statistics.mean(condensed[weight]['hmtx'][name][0] /
                                                  font['hmtx'][name][0] for name in 'nohdeasu')
                         for weight, font in noto.items()}
        self.mono_ratios = {weight: condensed[weight]['hmtx']['zero'][0]/font['hmtx']['zero'][0]
                            for weight, font in noto.items()}
        self.math_sign_ratios = {weight: condensed[weight]['hmtx']['plus'][0]/font['hmtx']['plus'][0]
                                 for weight, font in noto.items()}
        default = noto[400]
        cmap = default.getBestCmap()
        reference_cmap = reference.getBestCmap()
        names = set(default.getGlyphOrder())
        self.analogues = {name: name for name in reference.getGlyphOrder() if name in names}
        face_shear = math.tan(math.radians(-reference['post'].italicAngle))
        math_i = reference.getBestCmap().get(0x1D43C)
        math_shear = measured_shear(read(reference, math_i)) if math_i else face_shear
        self.shears = {name: 0.0 for name in reference.getGlyphOrder()}
        self.fixed_widths = set()
        self.math_signs = {reference.getBestCmap()[ord(character)] for character in MATH_SIGNS
                           if ord(character) in reference.getBestCmap()}
        # Mathematical alphabet codepoints carry their own upright/italic style,
        # independently of the surrounding text face.
        for codepoint, name in reference.getBestCmap().items():
            character = chr(codepoint)
            description = unicodedata.name(character, '')
            decomposition = unicodedata.decomposition(character).split()
            if unicodedata.category(character).startswith('L'):
                self.shears[name] = face_shear
            if len(decomposition) == 2 and decomposition[0] == '<font>':
                base = int(decomposition[1], 16)
                if base in cmap:
                    self.analogues[name] = cmap[base]
            elif codepoint in cmap:
                self.analogues[name] = cmap[codepoint]
            if description.startswith(('MATHEMATICAL ', 'SCRIPT ', 'BLACK-LETTER ', 'DOUBLE-STRUCK ')):
                self.shears[name] = math_shear if 'ITALIC' in description else 0.0
            if description.startswith('MATHEMATICAL MONOSPACE '):
                self.fixed_widths.add(name)
        # These unencoded Greek alphabet families have an explicitly authored
        # pen inclination; retain it just as the encoded italic alphabet's.
        for name in reference.getGlyphOrder():
            if '.anodyne.grk.' in name:
                style = name.split('.anodyne.grk.', 1)[1].split('.', 1)[0]
                self.shears[name] = .15 if style in ('script', 'bold-script') else .07 if style == 'chancery' else 0.0
                if style == 'monospace':
                    self.fixed_widths.add(name)
        # These historical mathematical letters lack a useful width master of
        # their own. Use the ordinary letter with the corresponding skeleton;
        # the double-struck summation follows Greek Sigma, including its RTL
        # variant. Keep these choices through optical/stylistic descendants.
        forced_analogues = set()
        for codepoint, choices in ((0x2118, 'P'), (0x2140, 'ΣM')):
            if codepoint in reference_cmap:
                analogue = next((cmap[ord(character)] for character in choices
                                 if ord(character) in cmap), None)
                if analogue:
                    name = reference_cmap[codepoint]
                    self.analogues[name] = analogue
                    forced_analogues.add(name)
        # Carry references into script-sized, alternate and enlarged drawings.
        edges = []
        if 'GSUB' in reference:
            for lookup in reference['GSUB'].table.LookupList.Lookup:
                for subtable in lookup.SubTable:
                    subtable = getattr(subtable, 'ExtSubTable', subtable)
                    for source, targets in getattr(subtable, 'mapping', {}).items():
                        for target in targets if isinstance(targets, list) else [targets]:
                            edges.append((source, target))
                    for source, targets in getattr(subtable, 'alternates', {}).items():
                        edges.extend((source, target) for target in targets)
        if 'MATH' in reference:
            variants = reference['MATH'].table.MathVariants
            for direction in ('Vert', 'Horiz'):
                coverage = getattr(variants, direction+'GlyphCoverage')
                if coverage:
                    for source, construction in zip(coverage.glyphs, getattr(variants, direction+'GlyphConstruction')):
                        edges.extend((source, record.VariantGlyph) for record in construction.MathGlyphVariantRecord)
                        if construction.GlyphAssembly:
                            edges.extend((source, part.glyph) for part in construction.GlyphAssembly.PartRecords)
        responsive = {name: any(font['hmtx'][name][0] > 0 and
                                self.condensed[weight]['hmtx'][name][0] < font['hmtx'][name][0]
                                for weight, font in self.noto.items()) for name in names}
        while True:
            changed = False
            for source, target in edges:
                if source in self.fixed_widths and target not in self.fixed_widths:
                    self.fixed_widths.add(target)
                    changed = True
                if source in forced_analogues and target not in forced_analogues:
                    self.analogues[target] = self.analogues[source]
                    forced_analogues.add(target)
                    if '.anodyne.grk.' not in target:
                        self.shears[target] = self.shears.get(source, 0.0)
                    changed = True
                elif (source in self.semantic_math and target in self.semantic_math
                      and source in self.analogues and target in self.analogues
                      and responsive.get(self.analogues[source], False)
                      and not responsive.get(self.analogues[target], False)):
                    # Native dotless mathematical i/j can be width-static
                    # even when their encoded parents use a responsive i/j.
                    # Keep their cells aligned; retain independently calibrated
                    # references for optical/chancery forms that already vary.
                    self.analogues[target] = self.analogues[source]
                    if '.anodyne.grk.' not in target:
                        self.shears[target] = self.shears.get(source, 0.0)
                    changed = True
                elif target not in self.analogues and source in self.analogues:
                    self.analogues[target] = self.analogues[source]
                    if '.anodyne.grk.' not in target:
                        self.shears[target] = self.shears.get(source, 0.0)
                    changed = True
            if not changed:
                break
        # Compound relations and every optical/stylistic descendant use the
        # shared reference. Letter-shaped parents (the phonetic double-bar esh
        # letters reuse superscript minus) retain their own letter-width policy.
        letter_glyphs = {name for codepoint, name in reference.getBestCmap().items()
                         if unicodedata.category(chr(codepoint)).startswith('L')}
        changed = True
        while changed:
            changed = False
            for source, target in edges:
                if source in self.math_signs and target not in self.math_signs:
                    self.math_signs.add(target)
                    changed = True
            for name in reference.getGlyphOrder():
                glyph = reference['glyf'][name]
                if glyph.isComposite() and name not in letter_glyphs and name not in self.math_signs and any(
                        component.glyphName in self.math_signs for component in glyph.components):
                    self.math_signs.add(name)
                    changed = True
        # Ancestors can change their rendered bounds through a component even
        # when their own spacing/GLIF stays unchanged. Expose that geometry
        # closure separately for source migration and positioning verification.
        self.affected_math_signs = set(self.math_signs)
        changed = True
        while changed:
            changed = False
            for name in reference.getGlyphOrder():
                glyph = reference['glyf'][name]
                if glyph.isComposite() and name not in self.affected_math_signs and any(
                        component.glyphName in self.affected_math_signs for component in glyph.components):
                    self.affected_math_signs.add(name)
                    changed = True

    def width_ratio(self, name, weight):
        if name in self.math_signs:
            return self.math_sign_ratios[weight]
        if name in self.fixed_widths:
            return self.mono_ratios[weight]
        analogue = self.analogues.get(name)
        if analogue:
            advance = self.noto[weight]['hmtx'][analogue][0]
            if advance:
                ratio = min(1.0, self.condensed[weight]['hmtx'][analogue][0]/advance)
                # Some upstream mathematical symbols advertise wdth while
                # retaining the same outlines/advance. They cannot calibrate a
                # responsive derived alphabet, so use Noto's measured fallback.
                if name in self.semantic_math and ratio >= 1-1e-6:
                    return self.fallback[weight]
                return ratio
        return self.fallback[weight]

    def draw(self, name, outline, weight):
        return condense_outline(outline, self.width_ratio(name, weight),
                                self.stem_ratios[weight], self.stems[weight],
                                self.shears.get(name, 0.0))
