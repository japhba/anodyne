"""Editable compatible masters: UFO outlines/metrics with editable TTX layout data.

The first preparation imports the upstream binaries and normalizes their points.
Subsequent builds consume these UFOs; contour matching is not repeated. UFOZ is
standard zipped UFO, supported by fontmake and ufoLib2. `unpack` makes directory
UFOs for font editors. Layout and MATH tables live as XML inside each UFO's data
directory, so rebuilding never silently drops shaping or mathematical layout.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

from fontTools import varLib
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import flagOverlapSimple, OVERLAP_COMPOUND
from fontTools.ufoLib import UFOFileStructure
from ufoLib2 import Font
from ufo2ft import compileTTF

ROOT = Path(__file__).resolve().parents[1]
TABLE_DATA = 'com.overlyx.anodyne/tables.ttx'
PROVENANCE = 'com.overlyx.anodyne.provenance'


def epoch():
    return int(os.environ.get('SOURCE_DATE_EPOCH', json.loads((ROOT / 'sources/source-lock.json').read_text())['source_date_epoch']))


def normalize_timestamp(font):
    font.recalcTimestamp = False
    font['head'].created = font['head'].modified = epoch() + 2082844800


def deterministic_zip(path):
    # UFOWriter's ordinary archive timestamps reflect the host filesystem.
    import datetime
    stamp = datetime.datetime.fromtimestamp(max(epoch(), 315532800), datetime.timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(path) as archive:
        entries = [(n, archive.read(n)) for n in sorted(archive.namelist()) if not n.endswith('/')]
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries:
            item = zipfile.ZipInfo(name, date_time=stamp)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)


def export_font(font, path, location=None):
    """Export exact quadratic outlines, advances, glyph order and layout XML."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ufo = Font()
    ufo.info.familyName = 'Anodyne'
    ufo.info.styleName = path.stem
    ufo.info.unitsPerEm = font['head'].unitsPerEm
    ufo.info.ascender = font['hhea'].ascent
    ufo.info.descender = font['hhea'].descent
    ufo.info.openTypeHheaLineGap = font['hhea'].lineGap
    ufo.info.italicAngle = font['post'].italicAngle
    ufo.info.xHeight = getattr(font['OS/2'], 'sxHeight', None)
    ufo.info.capHeight = getattr(font['OS/2'], 'sCapHeight', None)
    ufo.glyphOrder = font.getGlyphOrder()
    glyphset = font.getGlyphSet()
    for name in ufo.glyphOrder:
        glyph = ufo.newGlyph(name)
        glyphset[name].drawPoints(glyph.getPointPen())
        glyph.width = font['hmtx'][name][0]
    for codepoint, name in font.getBestCmap().items():
        ufo[name].unicodes.append(codepoint)
    normalize_timestamp(font)
    stream = io.BytesIO()
    font.saveXML(stream, skipTables=['glyf', 'hmtx', 'loca'])
    ufo.data[TABLE_DATA] = stream.getvalue()
    ufo.lib[PROVENANCE] = {
        'location': location or {},
        'sourceLockSHA256': __import__('hashlib').sha256((ROOT / 'sources/source-lock.json').read_bytes()).hexdigest(),
        'origin': 'Compatible bootstrap drawings from pinned upstream inputs; see sources/master-plan.json',
    }
    ufo.save(path, structure=UFOFileStructure.ZIP, overwrite=True)
    ufo.close()
    deterministic_zip(path)


def apply_overrides(ufo, directory):
    """Apply tracked partial UFOs by master name; every changed glyph is explicit."""
    directory = Path(directory)
    if not directory.exists():
        return
    with Font.open(directory) as overrides:
        for name in overrides.keys():
            if name not in ufo:
                raise ValueError(f'Override {directory}: {name} is absent from the compatible master')
            ufo.layers.defaultLayer[name] = copy.deepcopy(overrides[name])


def compile_font(path, overrides=None):
    """Compile edited source geometry, retaining the corresponding layout tables."""
    with Font.open(path, lazy=False) as ufo:
        if overrides is not None:
            apply_overrides(ufo, overrides)
        if TABLE_DATA not in ufo.data:
            raise ValueError(f'{path}: missing editable layout/MATH TTX source')
        # ufo2ft is fontmake's compiler. Disable geometry optimizations: compatible
        # points, contour order and components are the editable source contract.
        geometry = compileTTF(
            ufo, convertCubics=False, reverseDirection=False,
            removeOverlaps=False, flattenComponents=False,
            featureWriters=[], useProductionNames=False,
            dropImpliedOnCurves=False,
        )
        font = TTFont(recalcTimestamp=False)
        font.importXML(io.BytesIO(ufo.data[TABLE_DATA]))
        if font.getGlyphOrder() != geometry.getGlyphOrder():
            raise ValueError(f'{path}: glyph order changed during source compilation')
        for tag in ('glyf', 'hmtx', 'loca', 'maxp', 'hhea'):
            font[tag] = geometry[tag]
        # Preserve overlap flags for safe variable-font rasterization.
        for name in font.getGlyphOrder():
            glyph = font['glyf'][name]
            if glyph.isComposite():
                glyph.components[0].flags |= OVERLAP_COMPOUND
            elif glyph.numberOfContours > 0:
                glyph.flags[0] |= flagOverlapSimple
        normalize_timestamp(font)
        from layout_fixes import apply_layout_fixes
        apply_layout_fixes(font)
        return font


def export_designspace(designspace, folder, math_regular=None, math_bold=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    document = copy.deepcopy(designspace)
    for source in document.sources:
        source.name = source.name or Path(source.path).stem
        destination = folder / f'{source.name}.ufoz'
        print(f'editable master {destination.name}', flush=True)
        export_font(TTFont(source.path), destination, source.location)
        source.font = None
        source.path = str(destination.resolve())
    for name, font in (('Regular', math_regular), ('Bold', math_bold)):
        if font is not None:
            export_font(font, folder / 'math' / f'{name}.ufoz')
    style = 'Italic' if 'Italic' in document.sources[0].name else 'Roman'
    path = folder / f'Anodyne-{style}.designspace'
    document.write(path)
    return path


def compile_designspace(path, overrides_root=ROOT / 'sources/overrides'):
    """Build the release variable font from persisted, optionally edited UFOs."""
    import build
    document = DesignSpaceDocument.fromfile(path)
    style = Path(path).parent.name
    clip_bounds = [0, 0]
    with tempfile.TemporaryDirectory(prefix='anodyne-compile-') as directory:
        for source in document.sources:
            target = Path(directory) / f'{source.name}.ttf'
            font = compile_font(source.path, Path(overrides_root) / style / f'{source.name}.ufo')
            # GLIF edits can change a delimiter variant or assembly part while
            # its editable TTX sidecar still contains the bootstrap extent.
            # Refresh construction geometry; retain explicitly edited MATH
            # scalar values, which the variable-record merger consumes below.
            build.refresh_math_metrics(font)
            font.save(target)
            clip_bounds[0] = min(clip_bounds[0], font['head'].yMin)
            clip_bounds[1] = max(clip_bounds[1], font['head'].yMax)
            source.path = str(target)
            source.font = None
        build.validate_master_compatibility(source.path for source in document.sources)
        variable, model, master_paths = varLib.build(document, exclude=['MVAR'], optimize=True)
        if hasattr(build, 'add_math_variations'):
            build.add_math_variations(variable, model, master_paths)
        from metadata import finalize_metrics
        finalize_metrics(variable, clip_bounds=clip_bounds)
        normalize_timestamp(variable)
        return variable


def load_math_faces(folder):
    folder = Path(folder) / 'math'
    return compile_font(folder / 'Regular.ufoz'), compile_font(folder / 'Bold.ufoz')


def unpack(path):
    """Prefer directory UFOs on future builds, so editor changes are consumed."""
    document = DesignSpaceDocument.fromfile(path)
    for source in document.sources:
        original = Path(source.path)
        if original.suffix != '.ufoz':
            continue
        destination = original.with_suffix('.ufo')
        if destination.exists():
            raise FileExistsError(f'{destination} already exists; refusing to overwrite edits')
        with Font.open(original, lazy=False) as ufo:
            ufo.save(destination, structure=UFOFileStructure.PACKAGE)
        source.path = str(destination)
    document.write(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['unpack'])
    parser.add_argument('designspaces', nargs='+', type=Path)
    args = parser.parse_args()
    for path in args.designspaces:
        unpack(path)


if __name__ == '__main__':
    main()
