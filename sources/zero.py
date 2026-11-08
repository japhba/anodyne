"""Restore Noto zero drawings and figure selection without changing other digits.

Text, old-style, proportional, fraction, superior and inferior zeros use Noto
Sans's actual variable masters. Roman math optical zeros retain Noto Sans Math's
exact default drawings and follow compatible Noto Sans superior/old-style zero
variation deltas. No italic Noto Sans Math exists: italic optical zeros are
derived from the corresponding Noto Sans Italic drawings, retaining their slant.
"""
from __future__ import annotations

import copy
import math

from fontTools.otlLib.builder import buildLookup, buildSingleSubstSubtable
from fontTools.ttLib.tables import otTables as ot

TEXT_NAMES = ('zero', 'zero.tosf', 'zero.osf', 'zero.lf', 'zero.slash',
              'zero.dnom', 'zero.numr', 'zero.osf.slash', 'uni2070', 'uni2080')
OPTICAL_SOURCES = {'zero.ssty1': 'uni2070', 'zero.ssty2': 'zero.osf'}
FIGURE_FEATURES = ('lnum', 'pnum', 'tnum', 'onum', 'case', 'zero')


def _bounds(outline):
    points = [p for contour in outline.contours for p in contour]
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def _correspondence(source, target):
    """Align Noto variation sample positions without fitting the target drawing.

    The old-style zero and second optical zero have one differently placed
    on-curve point. Their variation samples can still correspond by position:
    only coordinate deltas are transferred; the target's native curve flags
    and exact default geometry always remain intact.
    """
    import build
    source_box, target_box = _bounds(source), _bounds(target)
    remaining = set(range(len(source.contours)))
    result = []
    for destination in target.contours:
        flags = [point[2] for point in destination]
        candidates = []
        for contour_index in remaining:
            contour = source.contours[contour_index]
            if len(contour) != len(destination) or build.area(contour) * build.area(destination) <= 0:
                continue
            for rotation in range(len(contour)):
                indices = [(rotation + i) % len(contour) for i in range(len(contour))]
                flags_match = [contour[i][2] for i in indices] == flags
                error = sum(sum(((contour[i][axis] - source_box[axis]) / (source_box[axis + 2] - source_box[axis])
                                 - (point[axis] - target_box[axis]) / (target_box[axis + 2] - target_box[axis])) ** 2
                                for axis in (0, 1)) for i, point in zip(indices, destination))
                candidates.append((not flags_match, error, contour_index, indices))
        if not candidates:
            raise ValueError('Pinned Noto zero optical contour correspondence changed')
        _, _, contour_index, indices = min(candidates)
        remaining.remove(contour_index)
        result.append((contour_index, indices))
    if remaining:
        raise ValueError('Pinned Noto zero optical contour count changed')
    return result


class NativeZeroSources:
    def __init__(self, noto, condensed, noto_math, italic=False, roman_reference=None):
        import build
        self.noto, self.noto_c, self.math, self.italic = noto, condensed, noto_math, italic
        self.text_names = tuple(name for name in TEXT_NAMES if name in noto[400].getGlyphOrder())
        self.names = self.text_names + tuple(OPTICAL_SOURCES)
        self.roman = roman_reference if italic else noto[400]
        if self.roman is None:
            raise ValueError('Italic zero restoration needs the pinned Roman Noto reference')
        self.models = {}
        for target_name, source_name in OPTICAL_SOURCES.items():
            raw = build.read(noto_math, target_name)
            source = build.read(self.roman, source_name)
            correspondence = _correspondence(source, raw)
            old_box, new_box = _bounds(source), _bounds(raw)
            sx = (new_box[2] - new_box[0]) / (old_box[2] - old_box[0])
            sy = (new_box[3] - new_box[1]) / (old_box[3] - old_box[1])
            self.models[target_name] = {'source': source_name, 'raw': raw,
                'source_default': source, 'correspondence': correspondence,
                'sx': sx, 'sy': sy, 'source_y0': old_box[1], 'target_y0': new_box[1]}
            if italic:
                model = self.models[target_name]
                native = build.read(noto[400], source_name)
                model['italic_default'] = native
                model['italic_advance'] = noto[400]['hmtx']['zero'][0] * raw.adv / noto_math['hmtx']['zero'][0]
                model['shear'] = math.tan(math.radians(-noto[400]['post'].italicAngle))
                projected = self._italic_project(model, native)
                box = _bounds(projected)
                model['italic_dx'] = model['italic_advance'] / 2 - (box[0] + box[2]) / 2

    def _italic_project(self, model, source):
        import build
        shear, sx, sy = model['shear'], model['sx'], model['sy']
        def point(p):
            x, y, on = p
            target_y = (y - model['source_y0']) * sy + model['target_y0']
            target_x = (x - shear * y) * sx + shear * target_y + model.get('italic_dx', 0)
            return target_x, target_y, on
        advance = model['italic_advance'] * source.adv / model['italic_default'].adv
        return build.Outline([[point(p) for p in c] for c in source.contours], adv=advance)

    def outline(self, name, weight, width=100):
        import build
        font = (self.noto if width == 100 else self.noto_c)[weight]
        if name in self.text_names:
            return build.read(font, name)
        model = self.models[name]
        source = build.read(font, model['source'])
        if self.italic:
            return self._italic_project(model, source)
        default, raw = model['source_default'], model['raw']
        contours = []
        for destination, (index, indices) in zip(raw.contours, model['correspondence']):
            contours.append([(point[0] + (source.contours[index][i][0] - default.contours[index][i][0]) * model['sx'],
                              point[1] + (source.contours[index][i][1] - default.contours[index][i][1]) * model['sy'], point[2])
                             for point, i in zip(destination, indices)])
        advance = raw.adv + (source.adv - default.adv) * raw.adv / default.adv
        return build.Outline(contours, adv=advance)

    def normal_outlines(self):
        return {weight: {name: self.outline(name, weight) for name in self.names} for weight in self.noto}

    def condensed(self, name, weight):
        return self.outline(name, weight, 62.5) if name in self.names else None

    def restore_fonts(self, regular, bold, layout=True):
        import build
        for font, weight in ((regular, 400), (bold, 700)):
            order = font.getGlyphOrder()
            for name in self.names:
                if name not in order:
                    order.append(name)
            font.setGlyphOrder(order)
            font['glyf'].glyphOrder = order
            for name in self.names:
                build.write(font, name, self.outline(name, weight))
            # Superior/inferior and figure variants may reference a zero whose
            # drawing appears later in the glyph order. Refresh their final LSBs.
            for name in self.names:
                glyph = font['glyf'][name]
                glyph.recalcBounds(font['glyf'])
                advance, _ = font['hmtx'][name]
                font['hmtx'][name] = advance, glyph.xMin if glyph.numberOfContours else 0
            if layout:
                self.restore_layout(font)
            self.restore_math_info(font)

    def restore_layout(self, font):
        """Restore native zero substitutions in native lookup execution order.

        Combining ``onum`` and ``zero`` is meaningful: Noto first selects the
        old-style zero and then its explicitly requested slash. Keeping only
        each feature's isolated mapping is insufficient if appended lookups run
        in a different order. Zero-only lookups therefore follow Noto's order;
        mappings for the other digits retain their existing feature behavior.
        """
        import build
        names = set(self.names)
        gsub = font['GSUB'].table
        native_gsub = self.noto[400]['GSUB'].table
        tags = sorted(FIGURE_FEATURES, key=lambda tag: min(
            index for record in native_gsub.FeatureList.FeatureRecord if record.FeatureTag == tag
            for index in record.Feature.LookupListIndex))
        zero_maps = {}
        for tag in tags:
            current = build.single_subst_map(font, tag)
            retained = {source: target for source, target in current.items()
                        if source not in names and target not in names}
            native = build.single_subst_map(self.noto[400], tag)
            zero_maps[tag] = {source: target for source, target in native.items()
                             if (source in names or target in names)
                             and source in font.getReverseGlyphMap() and target in font.getReverseGlyphMap()}
            records = [record for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == tag]
            if not records:
                if not zero_maps[tag]:
                    continue
                build.add_feature(font, tag, zero_maps[tag])
                records = [record for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == tag]
            indices = []
            if retained:
                indices.append(len(gsub.LookupList.Lookup))
                gsub.LookupList.Lookup.append(buildLookup([buildSingleSubstSubtable(retained)]))
            for record in records:
                record.Feature.LookupListIndex = list(indices)
                record.Feature.LookupCount = len(indices)
        for tag in tags:
            if not zero_maps[tag]:
                continue
            index = len(gsub.LookupList.Lookup)
            gsub.LookupList.Lookup.append(buildLookup([buildSingleSubstSubtable(zero_maps[tag])]))
            for record in gsub.FeatureList.FeatureRecord:
                if record.FeatureTag == tag:
                    record.Feature.LookupListIndex.append(index)
                    record.Feature.LookupCount = len(record.Feature.LookupListIndex)
        gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    def restore_math_info(self, font):
        """Remove wide dotted-zero measurements and use the restored drawings."""
        if 'MATH' not in font:
            return
        import build
        aliases = {'zero': 'zero', 'zero.ssty1': 'zero.ssty1',
                   'zero.ssty2': 'zero.ssty2', 'zero.slash': 'zero.uv001'}
        target, source = font['MATH'].table.MathGlyphInfo, self.math['MATH'].table.MathGlyphInfo
        specs = [('MathTopAccentAttachment', 'TopAccentCoverage', 'TopAccentAttachment', 'TopAccentAttachmentCount'),
                 ('MathItalicsCorrectionInfo', 'Coverage', 'ItalicsCorrection', 'ItalicsCorrectionCount'),
                 ('MathKernInfo', 'MathKernCoverage', 'MathKernInfoRecords', 'MathKernCount')]
        for container, coverage, values, count in specs:
            native = getattr(source, container)
            original = getattr(target, container)
            native_values = dict(zip(getattr(native, coverage).glyphs, getattr(native, values))) if native else {}
            if original is None and not any(name in native_values for name in aliases.values()):
                continue
            if original is None:
                original = type(native)()
                setattr(original, coverage, ot.Coverage())
                getattr(original, coverage).glyphs = []
                setattr(original, values, [])
                setattr(target, container, original)
            existing = dict(zip(getattr(original, coverage).glyphs, getattr(original, values)))
            for name, raw_name in aliases.items():
                existing.pop(name, None)
                if raw_name not in native_values:
                    continue
                record = copy.deepcopy(native_values[raw_name])
                if isinstance(record, ot.MathValueRecord):
                    raw_box = _bounds(build.read(self.math, raw_name))
                    new_box = _bounds(build.read(font, name))
                    if container == 'MathTopAccentAttachment':
                        record.Value = round(new_box[0] + (record.Value - raw_box[0]) * (new_box[2] - new_box[0]) / (raw_box[2] - raw_box[0]))
                    else:
                        record.Value = max(0, round(record.Value * (new_box[2] - new_box[0]) / (raw_box[2] - raw_box[0])))
                    record.DeviceTable = None
                existing[name] = record
            ordered = sorted(existing, key=font.getGlyphID)
            getattr(original, coverage).glyphs = ordered
            setattr(original, values, [existing[name] for name in ordered])
            setattr(original, count, len(ordered))
