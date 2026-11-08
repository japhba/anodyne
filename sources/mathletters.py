"""Compatible weight repair for mathematical letters frozen in the text source.

Some Noto Sans Letterlike Symbols have no weight or width deltas. They are
mathematical alphabet members despite their historical Unicode positions.
Preserve their Regular drawings and derive compatible stroke adjustments only
where all imported weight anchors are genuinely identical.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import unicodedata


def semantic_codepoints(reference):
    """The mathematical alphabet scope used by the released-font checks."""
    return {cp for cp in reference.getBestCmap()
            if (0x1D400 <= cp <= 0x1D7FF or 0x1EE00 <= cp <= 0x1EEFF
                or (0x2100 <= cp <= 0x214F
                    and (unicodedata.decomposition(chr(cp)).startswith('<font>')
                         or unicodedata.name(chr(cp), '').startswith(
                             ('SCRIPT ', 'BLACK-LETTER ', 'DOUBLE-STRUCK ')))))}


def semantic_edges(reference):
    edges = []
    if 'GSUB' in reference:
        for lookup in reference['GSUB'].table.LookupList.Lookup:
            for sub in lookup.SubTable:
                sub = getattr(sub, 'ExtSubTable', sub)
                for source, targets in getattr(sub, 'mapping', {}).items():
                    edges.extend((source, target) for target in
                                 (targets if isinstance(targets, list) else [targets]))
                for source, targets in getattr(sub, 'alternates', {}).items():
                    edges.extend((source, target) for target in targets)
    if 'MATH' in reference:
        variants = reference['MATH'].table.MathVariants
        for direction in ('Vert', 'Horiz'):
            coverage = getattr(variants, direction+'GlyphCoverage')
            if coverage:
                for source, construction in zip(coverage.glyphs,
                                               getattr(variants, direction+'GlyphConstruction')):
                    edges.extend((source, record.VariantGlyph)
                                 for record in construction.MathGlyphVariantRecord)
                    if construction.GlyphAssembly:
                        edges.extend((source, part.glyph) for part in construction.GlyphAssembly.PartRecords)
    return [(a, b) for a, b in edges if '.anodyne.grk.' not in b]


def semantic_names(reference):
    """Encoded mathematical letters and their optical/stylistic descendants."""
    cmap = reference.getBestCmap()
    names = {cmap[cp] for cp in semantic_codepoints(reference)}
    edges = semantic_edges(reference)
    while True:
        added = {target for source, target in edges if source in names}-names
        if not added:
            return names
        names.update(added)


@dataclass
class MathLetterRepair:
    repaired_weight_names: set[str]
    forced_width_names: set[str]
    report: list[dict]

    @property
    def affected_names(self):
        return self.repaired_weight_names | self.forced_width_names


def _flat(outline, drawings):
    from build import Outline
    from greekstyles import flatten
    return Outline(flatten(outline, drawings), adv=outline.adv)


def native_width_static(native, condensed, name):
    """Compare actual native ink, including every transformed component.

    A wrapper can retain the same component names and transforms while its
    children respond to width. Inspecting only that wrapper would incorrectly
    replace a working native condensed design with a synthetic one.
    """
    def ink(font):
        glyph = font['glyf'][name]
        coordinates, endpoints, flags = glyph.getCoordinates(font['glyf'])
        return (tuple((x, y, bool(flag & 1))
                      for (x, y), flag in zip(coordinates, flags)), tuple(endpoints))
    return ink(native) == ink(condensed)


def _area(outline):
    from fontTools.pens.areaPen import AreaPen
    pen = AreaPen(None)
    # Outline points use TrueType quadratic on/off-curve flags.
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from array import array
    glyph = Glyph(); glyph.numberOfContours = len(outline.contours)
    glyph.coordinates = GlyphCoordinates([(x, y) for contour in outline.contours for x, y, _ in contour])
    ends = []; count = 0
    for contour in outline.contours:
        count += len(contour); ends.append(count-1)
    glyph.endPtsOfContours = ends
    glyph.flags = array('B', [int(on) for contour in outline.contours for _, _, on in contour])
    glyph.draw(pen, None)
    return abs(pen.value)


def _ink_signature(outline):
    """Ignore native placement/advance motion when testing actual ink design."""
    if not outline.contours:
        return ()
    from build import bbox
    x0, y0, _, _ = bbox(outline.contours)
    return tuple(tuple((round(x-x0, 6), round(y-y0, 6), on) for x, y, on in contour)
                 for contour in outline.contours)


def _family_map(reference, names):
    families = {}
    for cp, name in reference.getBestCmap().items():
        description = unicodedata.name(chr(cp), '')
        if 'SCRIPT' in description:
            families[name] = 'script'
        elif 'FRAKTUR' in description or 'BLACK-LETTER' in description:
            families[name] = 'fraktur'
        elif 'DOUBLE-STRUCK' in description:
            families[name] = 'double-struck'
    edges = semantic_edges(reference)
    while True:
        added = {target: families[source] for source, target in edges
                 if source in families and target not in families and target in names}
        if not added:
            return families
        families.update(added)


def _local_offsets(outline, reference_stem):
    """Measure opposite ink edges along each editable node's local normal.

    A broad-pen hairline and a broad stroke receive different offsets. This
    avoids erasing hairlines by subtracting a text-l-sized constant everywhere.
    Sampling measures curves; the original editable topology remains intact.
    """
    from condense import _polygons
    polygons = _polygons(outline)
    segments = [(a, b) for polygon in polygons for a, b in zip(polygon, polygon[1:]+polygon[:1])]
    result = []
    for contour in outline.contours:
        offsets = []
        for index, q in enumerate(contour):
            previous, following = contour[index-1], contour[(index+1)%len(contour)]
            before = (q[0]-previous[0], q[1]-previous[1])
            after = (following[0]-q[0], following[1]-q[1])
            lb, la = math.hypot(*before), math.hypot(*after)
            vx = before[0]/(lb or 1)+after[0]/(la or 1)
            vy = before[1]/(lb or 1)+after[1]/(la or 1)
            length = math.hypot(vx, vy)
            if not length:
                offsets.append((0, 0, 0, float('inf'))); continue
            # Find the sampled curve beneath an off-curve control point.
            closest = None
            for segment_index, (a, b) in enumerate(segments):
                dx, dy = b[0]-a[0], b[1]-a[1]
                t = max(0, min(1, ((q[0]-a[0])*dx+(q[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
                p = (a[0]+t*dx, a[1]+t*dy)
                distance = (p[0]-q[0])**2+(p[1]-q[1])**2
                if closest is None or distance < closest[0]:
                    closest = (distance, p, dx, dy, segment_index)
            _, p, dx, dy, nearest = closest
            # All correctly wound TrueType ink boundaries have ink on their
            # right: clockwise exteriors and counterclockwise counters. Unit
            # incoming/outgoing tangents give a corner bisector independent of
            # unequal segment lengths; a long stem must not bend its serif.
            nx, ny = -vy/length, vx/length
            # Shoot into the ink and find its opposite edge.
            ix, iy = -nx, -ny
            hits, gaps = [], []
            for segment_index, (a, b) in enumerate(segments):
                if abs(segment_index-nearest) <= 1:
                    continue
                sx, sy = b[0]-a[0], b[1]-a[1]
                denominator = ix*sy-iy*sx
                if abs(denominator) < 1e-8:
                    continue
                ax, ay = a[0]-p[0], a[1]-p[1]
                ray = (ax*sy-ay*sx)/denominator
                part = (ax*iy-ay*ix)/denominator
                if -.0001 <= part <= 1.0001:
                    if ray > 2:
                        hits.append(ray)
                    elif ray < -4:
                        gaps.append(-ray)
            stroke = min(hits) if hits else reference_stem*.3
            stroke = max(4, min(reference_stem*2.5, stroke))
            # Use the editable curve tangent for a smooth control polygon.
            offsets.append((nx, ny, stroke, min(gaps) if gaps else float('inf')))
        # Quadratic control points can sample opposite sides of a tight join.
        # Smooth the measured radius, rather than sending individual nodes in
        # different directions or making a straight stem's corners disagree.
        for _ in range(3):
            widths = [(offsets[i-1][2]+2*value[2]+offsets[(i+1)%len(offsets)][2])/4
                      for i, value in enumerate(offsets)]
            offsets = [(x, y, width, gap) for (x, y, _, gap), width in zip(offsets, widths)]
        result.append(offsets)
    return result


def _weighted(outline, offsets, ratio, shear):
    from build import Outline, bbox, sane
    old_box = bbox(outline.contours)
    strength = 1.0
    while True:
        contours = []
        for contour, normals in zip(outline.contours, offsets):
            points = []
            for (x, y, on), (nx, ny, stroke, clearance) in zip(contour, normals):
                target = max(4, stroke*ratio)
                shift = (target-stroke)*strength/2
                if shift > 0:
                    shift = min(shift, clearance*.38)
                points.append((x+nx*shift, y+ny*shift, on))
            contours.append(points)
        candidate = Outline(contours, adv=outline.adv)
        if sane(outline, candidate) or strength <= 1/128:
            break
        strength *= .75
    if not sane(outline, candidate):
        raise ValueError('Cannot retain mathematical letter contours during weight derivation')
    # Keep the original baseline/ascender envelope and the style's inclination.
    x0, y0, x1, y1 = bbox(candidate.contours)
    vertical = (old_box[3]-old_box[1])/(y1-y0 or 1)
    candidate.contours = [[(x+shear*(old_box[1]+(y-y0)*vertical-y),
                            old_box[1]+(y-y0)*vertical, on)
                           for x, y, on in contour] for contour in candidate.contours]
    return candidate, strength


def apply_to_normal_anchors(normal, reference, noto, notoC=None):
    """Repair frozen mathematical letters before deriving Greek/width/grade.

    The reference's Regular glyphs and all existing non-static weight drawings
    remain unchanged. The returned width set must bypass native Noto copying.
    """
    from build import Outline, bbox, measure_stem, read
    from condense import measured_shear
    names = semantic_names(reference)
    families = _family_map(reference, names)
    cmap = reference.getBestCmap()
    math_i = cmap.get(0x1D43C)
    italic_shear = measured_shear(_flat(normal[400][math_i], normal[400])) if math_i else .212
    # Existing, genuinely varying alphabet peers calibrate optical weight.
    peers = {'script': cmap.get(0x1D49C), 'fraktur': cmap.get(0x1D504),
             'double-struck': cmap.get(0x1D538)}
    stems = {weight: measure_stem(font) for weight, font in noto.items()}
    ratios = {}
    for family, peer in peers.items():
        if peer and peer in normal[400]:
            values = {weight: _area(_flat(drawings[peer], drawings)) for weight, drawings in normal.items()}
            if values[400] and max(values.values())-min(values.values()) > 1:
                ratios[family] = {weight: value/values[400] for weight, value in values.items()}
    repaired, forced, report = set(), set(), []
    for name in sorted(names):
        outlines = {weight: _flat(drawings[name], drawings) for weight, drawings in normal.items()}
        regular = outlines[400]
        if not regular.contours:
            continue
        frozen = all(_ink_signature(outline) == _ink_signature(regular) for outline in outlines.values())
        if frozen:
            if any(drawings[name].components for drawings in normal.values()):
                raise ValueError(f'{name}: static composite requires a compatible component-level repair')
            family = families.get(name)
            # Only actual italic families use the math italic stem inclination;
            # ornate script/fraktur shapes are not reliable shear rulers.
            descriptions = [unicodedata.name(chr(cp), '') for cp, glyph in cmap.items() if glyph == name]
            italic = any('ITALIC' in value for value in descriptions) or 'italic' in name.lower()
            shear = italic_shear if italic else 0.0
            upright = Outline([[(x-shear*y, y, on) for x, y, on in contour]
                               for contour in regular.contours], adv=regular.adv)
            offsets = _local_offsets(upright, stems[400])
            row = {'glyph': name, 'family': family or 'mathematical', 'regular_preserved': True, 'weights': {}}
            for weight in normal:
                if weight == 400:
                    continue
                ratio = ratios.get(family, {}).get(weight, stems[weight]/stems[400])
                if family == 'fraktur' and ratio > 1:
                    # Existing A is an unusually open blackletter drawing.
                    # Applying its full ink-area growth to the compact C/H/J
                    # ornaments fills their joins. Retain the peer progression
                    # with bounded broadening of these inherited letter forms.
                    ratio = 1+(ratio-1)*.6
                candidate, strength = _weighted(upright, offsets, ratio, 0)
                regular_box, original_box = bbox(regular.contours), bbox(outlines[weight].contours)
                dx, dy = original_box[0]-regular_box[0], original_box[1]-regular_box[1]
                candidate.contours = [[(x+shear*y+dx, y+dy, on) for x, y, on in contour]
                                      for contour in candidate.contours]
                candidate.adv = outlines[weight].adv
                normal[weight][name] = candidate
                row['weights'][str(weight)] = {'relative_stroke': ratio, 'bounded_strength': strength}
            repaired.add(name); report.append(row)
        if notoC is not None and name in noto[400]['glyf'] and name in notoC[400]['glyf']:
            if native_width_static(noto[400], notoC[400], name):
                forced.add(name)
    forced.update(repaired)
    # Imported Lisnoti double-struck summation uses an explicit Sigma width
    # reference in Policy. Native Noto can contain a different, responsive
    # drawing with the same glyph name, so native comparison alone cannot mark
    # the imported condensed sources as needing regeneration.
    if 0x2140 in cmap:
        forced.add(cmap[0x2140])
    edges = semantic_edges(reference)
    while True:
        added = {target for source, target in edges if source in forced and target in names}-forced
        if not added:
            break
        forced.update(added)
    return MathLetterRepair(repaired, forced, report)
