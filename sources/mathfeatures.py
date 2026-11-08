"""Optional mathematical styles, drawn from Anodyne's own glyphs.

The feature choices follow the comparison in mathfonts.json: Noto Sans Math,
Fira Math and XITS offer upright integrals; Lete Sans, KpMath and XCharter offer
slanted inequalities and compact set symbols; STIX Two/XITS offer vertical
negations. Character variants expose the oval empty set and add a lowered-bar
Planck constant. No outlines or metrics are imported from those fonts.

Call add_math_features on both source faces before constructing variable masters.
All derived glyphs therefore participate in weight, width and grade construction.
Integral alternates retain MATH size variants and assemblies, including script
and mirrored glyphs; the existing (already upright) assembly pieces are reused.
"""
from __future__ import annotations

import array
import copy
import math
import unicodedata

from fontTools.pens.basePen import BasePen
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates, flagOverlapSimple
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.otlLib.builder import buildLookup, buildSingleSubstSubtable


FEATURES = {
    'ss02': {'name': 'Upright integrals', 'sample': '∫ ∬ ∭ ∮ ∯ ∰',
             'description': 'Straight integral stems, including display and script sizes.',
             'inspiration': 'Noto Sans Math ss02; Fira Math ss01; XITS ss08'},
    'ss03': {'name': 'Slanted inequalities', 'sample': '≤ ≥ ≰ ≱',
             'description': 'Slant the equality strokes beneath less-than and greater-than signs.',
             'inspiration': 'Lete Sans Math, KpMath and XCharter ss04'},
    'ss04': {'name': 'Compact set symbols', 'sample': '∈ ∉ ∋ ∌ ∖ ∣ ∥',
             'description': 'Smaller membership, set-minus and relation-bar symbols.',
             'inspiration': 'Lete Sans Math, KpMath and XCharter ss05'},
    'ss05': {'name': 'Vertical negation strokes', 'sample': '≠ ∉ ∌ ≮ ≯ ≰ ≱ ⊄ ⊅ ⊈ ⊉',
             'description': 'Use a vertical stroke to negate relations instead of a diagonal slash.',
             'inspiration': 'STIX Two Math and XITS ss09'},
    'cv01': {'name': 'Oval empty set', 'sample': '∅',
             'description': 'Use the oval empty-set symbol instead of the circular default.',
             'inspiration': 'Lete Sans Math and XCharter cv02'},
    'cv02': {'name': 'Lowered-bar hbar', 'sample': 'ℏ',
             'description': 'Place the Planck constant bar closer to the x-height.',
             'inspiration': 'Fira Math ss02; XCharter cv01'},
}

SUFFIX = '.anodyne.'


class _Flat(BasePen):
    """Polylines used only to measure the centre of an integral's straight stem."""
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.contours, self.current = [], []

    def _moveTo(self, p):
        self.current = [p]

    def _lineTo(self, p):
        self.current.append(p)

    def _qCurveToOne(self, control, end):
        start = self.current[-1]
        for i in range(1, 17):
            t, m = i / 16, 1 - i / 16
            self.current.append((m*m*start[0] + 2*m*t*control[0] + t*t*end[0],
                                 m*m*start[1] + 2*m*t*control[1] + t*t*end[1]))

    def _closePath(self):
        self.contours.append(self.current)
        self.current = []

    _endPath = _closePath


def _bounds(font, name):
    glyph = font['glyf'][name]
    glyph.recalcBounds(font['glyf'])
    return glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax


def _coordinates(font, name):
    coords, ends, flags = font['glyf'][name].getCoordinates(font['glyf'])
    return list(coords), list(ends), [f & 1 for f in flags]


def _write(font, name, points, ends, flags, advance):
    glyph = Glyph()
    glyph.numberOfContours = len(ends)
    glyph.coordinates = GlyphCoordinates([(round(x), round(y)) for x, y in points])
    glyph.endPtsOfContours = list(ends)
    glyph.flags = array.array('B', flags)
    if flags:
        glyph.flags[0] |= flagOverlapSimple
    glyph.program = Program()
    glyph.program.fromBytecode(b'')
    if name not in font.getReverseGlyphMap():
        font.setGlyphOrder(font.getGlyphOrder() + [name])
        font['glyf'].glyphOrder = font.getGlyphOrder()
    font['glyf'][name] = glyph
    glyph.recalcBounds(font['glyf'])
    font['hmtx'][name] = (round(advance), glyph.xMin)
    return name


def _transform(font, source, target, transform, *, keep_advance=False, keep_short_contours=False):
    coords, ends, flags = _coordinates(font, source)
    old_x0, _, old_x1, _ = _bounds(font, source)
    points = [transform(x, y) for x, y in coords]
    if keep_short_contours:
        ys = [y for _, y in coords]
        height = max(ys)-min(ys)
        start = 0
        for end in ends:
            contour = coords[start:end+1]
            if max(y for _, y in contour)-min(y for _, y in contour) < height*.65:
                # Keep contour-integral rings round and decorative strokes in
                # their original orientation while the tall stems become upright.
                points[start:end+1] = contour
            start = end+1
    # Preserve side bearings when narrowing a glyph, rather than centring the old
    # slanted advance around the new ink. This also keeps integral families compact.
    shift = old_x0 - min(x for x, _ in points)
    points = [(x + shift, y) for x, y in points]
    advance = font['hmtx'][source][0]
    if not keep_advance:
        advance += max(x for x, _ in points) - old_x1
    _write(font, target, points, ends, flags, advance)
    return shift


def _stroke(font):
    plus = font.getBestCmap()[0x2B]
    coords, _, _ = _coordinates(font, plus)
    xs = sorted(set(x for x, _ in coords))
    return max(12, xs[len(xs)//2] - xs[len(xs)//2 - 1])


def _negate(font, source, target, *, vertical, stroke):
    points, ends, flags = _coordinates(font, source)
    x0, y0, x1, y1 = _bounds(font, source)
    cx, cy = (x0 + x1)/2, (y0 + y1)/2
    height = max(y1-y0 + 80, 350)
    half = stroke/2
    if vertical:
        rect = [(cx-half, cy-height/2), (cx-half, cy+height/2),
                (cx+half, cy+height/2), (cx+half, cy-height/2)]
    else:
        slope = .32
        rect = [(cx-half-slope*height/2, cy-height/2),
                (cx-half+slope*height/2, cy+height/2),
                (cx+half+slope*height/2, cy+height/2),
                (cx+half-slope*height/2, cy-height/2)]
    points.extend(rect)
    ends.append(len(points)-1)
    flags.extend([1]*4)
    _write(font, target, points, ends, flags, font['hmtx'][source][0])


def _integral_slope(font, name):
    glyphs = font.getGlyphSet()
    pen = _Flat(glyphs)
    glyphs[name].draw(pen)
    _, y0, _, y1 = _bounds(font, name)

    def centre(y):
        xs = []
        for contour in pen.contours:
            if max(p[1] for p in contour)-min(p[1] for p in contour) < (y1-y0)*.65:
                continue
            for a, b in zip(contour, contour[1:] + contour[:1]):
                if min(a[1], b[1]) <= y < max(a[1], b[1]):
                    xs.append(a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        return sum(xs)/len(xs) if xs else None

    low, high = y0 + (y1-y0)*.36, y0 + (y1-y0)*.64
    a, b = centre(low), centre(high)
    if a is None or b is None:
        return .2
    return max(-.5, min(.5, (b-a)/(high-low)))


def _single_substitutions(font, tags):
    gsub = font['GSUB'].table
    indices = {i for f in gsub.FeatureList.FeatureRecord if f.FeatureTag in tags
               for i in f.Feature.LookupListIndex}
    result = {}
    for i in sorted(indices):
        lookup = gsub.LookupList.Lookup[i]
        for sub in lookup.SubTable:
            if lookup.LookupType == 7:
                sub = sub.ExtSubTable
            result.update(getattr(sub, 'mapping', {}))
    return result


def _copy_math_info(font, mapping, *, upright=False):
    """Keep alternate glyphs usable as accents/scripts and mathematical operators."""
    info = font['MATH'].table.MathGlyphInfo
    pairs = list(mapping.items() if isinstance(mapping, dict) else mapping)
    for attr, cov_attr, records_attr, count_attr in (
        ('MathItalicsCorrectionInfo', 'Coverage', 'ItalicsCorrection', 'ItalicsCorrectionCount'),
        ('MathTopAccentAttachment', 'TopAccentCoverage', 'TopAccentAttachment', 'TopAccentAttachmentCount'),
        ('MathKernInfo', 'MathKernCoverage', 'MathKernInfoRecords', 'MathKernCount'),
    ):
        table = getattr(info, attr)
        if table is None:
            continue
        coverage = getattr(table, cov_attr)
        records = dict(zip(coverage.glyphs, getattr(table, records_attr)))
        for source, target in pairs:
            if source in records and target not in records:
                value = copy.deepcopy(records[source])
                if upright and attr == 'MathItalicsCorrectionInfo':
                    value.Value = 0
                    value.DeviceTable = None
                elif attr == 'MathTopAccentAttachment':
                    x0, _, x1, _ = _bounds(font, target)
                    value.Value = round((x0+x1)/2)
                    value.DeviceTable = None
                records[target] = value
        order = font.getReverseGlyphMap()
        names = sorted(records, key=order.__getitem__)
        coverage.glyphs = names
        setattr(table, records_attr, [records[n] for n in names])
        setattr(table, count_attr, len(names))
    if info.ExtendedShapeCoverage:
        extended = set(info.ExtendedShapeCoverage.glyphs)
        extended.update(dst for src, dst in pairs if src in extended)
        info.ExtendedShapeCoverage.glyphs = sorted(extended, key=font.getReverseGlyphMap().__getitem__)


def _upright_integrals(font):
    cmap = font.getBestCmap()
    sources = {name for cp, name in cmap.items() if 'INTEGRAL' in unicodedata.name(chr(cp), '')}
    variants = font['MATH'].table.MathVariants
    constructions = {}
    if variants.VertGlyphCoverage:
        constructions = dict(zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction))
    sources.update(v.VariantGlyph for source in list(sources) if source in constructions
                   for v in constructions[source].MathGlyphVariantRecord)
    extra = _single_substitutions(font, {'ssty', 'rtlm'})
    while True:
        old = len(sources)
        sources.update(dst for src, dst in extra.items() if src in sources)
        if len(sources) == old:
            break
    mapping = {}
    for name in sorted(sources, key=font.getReverseGlyphMap().__getitem__):
        target = name + SUFFIX + 'upright'
        slope = _integral_slope(font, name)
        axis = font['MATH'].table.MathConstants.AxisHeight.Value
        _transform(font, name, target, lambda x, y: (x-slope*(y-axis), y), keep_short_contours=True)
        mapping[name] = target
    additions = {}
    for source, target in mapping.items():
        if source not in constructions:
            continue
        construction = copy.deepcopy(constructions[source])
        for record in construction.MathGlyphVariantRecord:
            record.VariantGlyph = mapping.get(record.VariantGlyph, record.VariantGlyph)
        # Noto/Lisnoti's integral assemblies have straight stems already. Sharing
        # those parts avoids shearing the extender and opening gaps at joins.
        if construction.GlyphAssembly:
            construction.GlyphAssembly.ItalicsCorrection.Value = 0
            construction.GlyphAssembly.ItalicsCorrection.DeviceTable = None
        additions[target] = construction
    constructions.update(additions)
    names = sorted(constructions, key=font.getReverseGlyphMap().__getitem__)
    variants.VertGlyphCoverage.glyphs = names
    variants.VertGlyphConstruction = [constructions[n] for n in names]
    variants.VertGlyphCount = len(names)
    _copy_math_info(font, mapping, upright=True)
    return mapping


def _register(font, tag, mapping, metadata=None):
    """Append a named single-substitution feature without replacing existing layout."""
    if not mapping:
        raise ValueError(f'{tag}: no glyph substitutions were created')
    gsub = font['GSUB'].table
    if any(record.FeatureTag == tag for record in gsub.FeatureList.FeatureRecord):
        raise ValueError(f'{tag} already exists; refusing to overwrite an upstream feature')
    lookup = buildLookup([buildSingleSubstSubtable(mapping)])
    gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    record = ot.FeatureRecord()
    record.FeatureTag = tag
    record.Feature = ot.Feature()
    def add_name(text):
        # Sample strings contain mathematical Unicode; MacRoman cannot encode
        # them. Windows Unicode names are sufficient for feature parameters.
        return font['name'].addName(text, platforms=((3, 1, 0x409),))
    metadata = FEATURES[tag] if metadata is None else metadata
    name_id = add_name(metadata['name'])
    if tag.startswith('ss'):
        params = ot.FeatureParamsStylisticSet()
        params.Version, params.UINameID = 0, name_id
    else:
        params = ot.FeatureParamsCharacterVariants()
        params.Format = 0
        params.FeatUILabelNameID = name_id
        params.FeatUITooltipTextNameID = add_name(metadata['description'])
        params.SampleTextNameID = add_name(metadata['sample'])
        params.NumNamedParameters, params.FirstParamUILabelNameID = 0, 0
        params.Character = [ord(c) for c in metadata['sample'] if c != ' ']
        params.CharCount = len(params.Character)
    record.Feature.FeatureParams = params
    record.Feature.LookupListIndex = [len(gsub.LookupList.Lookup)-1]
    record.Feature.LookupCount = 1
    records = gsub.FeatureList.FeatureRecord
    records.append(record)
    index = len(records)-1
    systems = [lang for sr in gsub.ScriptList.ScriptRecord
               for lang in [sr.Script.DefaultLangSys] + [x.LangSys for x in sr.Script.LangSysRecord]
               if lang is not None]
    for lang in systems:
        lang.FeatureIndex.append(index)
        lang.FeatureCount = len(lang.FeatureIndex)
    permutation = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    remap = {old: new for new, old in enumerate(permutation)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in permutation]
    gsub.FeatureList.FeatureCount = len(records)
    for lang in systems:
        lang.FeatureIndex = sorted(remap[i] for i in lang.FeatureIndex)
        if lang.ReqFeatureIndex != 0xFFFF:
            lang.ReqFeatureIndex = remap[lang.ReqFeatureIndex]


def add_math_features(font):
    """Add six independent, named feature families and return their substitution counts."""
    cmap = font.getBestCmap()
    stroke = _stroke(font)
    mappings = {'ss02': _upright_integrals(font)}
    copies = []

    slant = {}
    for source, target in ((0x2264, 0x2A7D), (0x2265, 0x2A7E)):
        slant[cmap[source]] = cmap[target]
    for negative, positive in ((0x2270, 0x2A7D), (0x2271, 0x2A7E)):
        target = cmap[negative] + SUFFIX + 'slanted'
        _negate(font, cmap[positive], target, vertical=False, stroke=stroke)
        slant[cmap[negative]] = target
        copies.append((cmap[negative], target))
    mappings['ss03'] = slant

    compact = {cmap[0x2208]: cmap[0x220A], cmap[0x220B]: cmap[0x220D]}
    for negative, small in ((0x2209, 0x220A), (0x220C, 0x220D)):
        target = cmap[negative] + SUFFIX + 'compact'
        _negate(font, cmap[small], target, vertical=False, stroke=stroke*.85)
        compact[cmap[negative]] = target
        copies.append((cmap[negative], target))
    axis = font['MATH'].table.MathConstants.AxisHeight.Value
    for cp in (0x2216, 0x2223, 0x2225):
        source = cmap[cp]
        target = source + SUFFIX + 'compact'
        sx = .76 if cp == 0x2216 else 1
        _transform(font, source, target, lambda x, y: (x*sx, axis+(y-axis)*.76), keep_advance=cp != 0x2216)
        compact[source] = target
        copies.append((source, target))
    mappings['ss04'] = compact

    vertical = {}
    for negative, positive in ((0x2260, 0x3D), (0x2209, 0x2208), (0x220C, 0x220B),
                               (0x226E, 0x3C), (0x226F, 0x3E), (0x2270, 0x2264),
                               (0x2271, 0x2265), (0x2284, 0x2282), (0x2285, 0x2283),
                               (0x2288, 0x2286), (0x2289, 0x2287)):
        target = cmap[negative] + SUFFIX + 'vertical'
        _negate(font, cmap[positive], target, vertical=True, stroke=stroke)
        vertical[cmap[negative]] = target
        # Make the combined settings work in the same order as their independent
        # lookups: first select compact/slanted glyphs, then change their stroke.
        selected = compact.get(cmap[negative]) or slant.get(cmap[negative])
        positive_selected = compact.get(cmap[positive]) or slant.get(cmap[positive])
        if selected and positive_selected:
            combined = selected + '.vertical'
            _negate(font, positive_selected, combined, vertical=True, stroke=stroke*.85 if cmap[negative] in compact else stroke)
            vertical[selected] = combined
            copies.append((cmap[negative], combined))
        copies.append((cmap[negative], target))
    mappings['ss05'] = vertical

    oval = 'emptyset.uv001'
    if oval not in font['glyf']:
        raise ValueError('Lisnoti oval empty-set variation is absent')
    mappings['cv01'] = {cmap[0x2205]: oval}

    # The default hbar has a high horizontal crossbar. The alternative places a
    # short bar across mathematical italic h at the x-height, a common quantum
    # mechanics form; the letter's original outline and slant are retained.
    source = cmap[0x210E]
    target = cmap[0x210F] + SUFFIX + 'lowbar'
    points, ends, flags = _coordinates(font, source)
    xheight = font['OS/2'].sxHeight
    x0, _, x1, _ = _bounds(font, source)
    width = (x1-x0)*.49
    centre = x0 + (x1-x0)*.29
    yy = xheight + stroke*.6
    points.extend([(centre-width/2, yy-stroke*.45), (centre-width/2, yy+stroke*.45),
                   (centre+width/2, yy+stroke*.45), (centre+width/2, yy-stroke*.45)])
    ends.append(len(points)-1)
    flags.extend([1]*4)
    _write(font, target, points, ends, flags, font['hmtx'][source][0])
    mappings['cv02'] = {cmap[0x210F]: target}
    copies.append((cmap[0x210F], target))
    _copy_math_info(font, copies)
    for tag, mapping in mappings.items():
        _register(font, tag, mapping)
    return {tag: len(mapping) for tag, mapping in mappings.items()}
