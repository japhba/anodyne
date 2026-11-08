"""Precisely replace a few GLIFs/layout data in a UFOZ without rewriting others.

Unchanged local ZIP records are copied verbatim; the central directory is
rebuilt with their new offsets. There are no duplicate or orphaned entries.
This is an authoring/migration utility. Normal releases still compile the saved
standard UFO sources through the ordinary compiler.
"""
from __future__ import annotations

import copy
import io
from pathlib import Path
import plistlib
import tempfile
import zipfile

from fontTools.ufoLib.glifLib import writeGlyphToString
from ufoLib2 import Font

import masters


def replace_zip_members(source, destination, replacements):
    """Copy original compressed records; deflate only the replacement members."""
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.zip', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as new:
            new.comment = old.comment
            names = old.namelist()
            if len(set(names)) != len(names):
                raise ValueError('Source ZIP has duplicate members')
            if set(replacements)-set(names):
                raise ValueError('A surgical patch cannot add unrecorded source members')
            physical = sorted(old.infolist(), key=lambda item: item.header_offset)
            ends = {item.header_offset: physical[i+1].header_offset if i+1 < len(physical) else old.start_dir
                    for i, item in enumerate(physical)}
            for name in sorted(names):
                original = old.getinfo(name)
                info = copy.copy(original)
                if name in replacements:
                    new.writestr(info, replacements[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                    continue
                if original.flag_bits & 1:
                    raise ValueError('Encrypted source ZIPs are not supported')
                old.fp.seek(original.header_offset)
                data = old.fp.read(ends[original.header_offset]-original.header_offset)
                # ZipFile exposes no compressed-member copy API. Updating this
                # small documented-by-source state lets its normal close write
                # a complete central directory for the copied local records.
                new.fp.seek(new.start_dir)
                info.header_offset = new.fp.tell()
                new._writecheck(info)
                new._didModify = True
                new.fp.write(data)
                new.filelist.append(info)
                new.NameToInfo[name] = info
                new.start_dir = new.fp.tell()
        with zipfile.ZipFile(temporary) as verified:
            if verified.testzip() is not None or len(verified.namelist()) != len(set(verified.namelist())):
                raise RuntimeError('Patched source ZIP failed integrity checks')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def patch_ufoz(source, destination, font, glyph_names):
    """Update selected geometry/advances and the complete editable layout TTX."""
    source, destination = Path(source), Path(destination)
    with zipfile.ZipFile(source) as archive:
        contents_name = next(name for name in archive.namelist() if name.endswith('/glyphs/contents.plist'))
        contents = plistlib.loads(archive.read(contents_name))
        glyph_directory = contents_name.removesuffix('contents.plist')
        table_name = next(name for name in archive.namelist() if name.endswith('/data/'+masters.TABLE_DATA))
    replacements = {}
    glyphset = font.getGlyphSet()
    with Font.open(source, lazy=True) as ufo:
        for name in sorted(glyph_names):
            if name not in contents:
                raise ValueError(f'{name} is absent from the source glyph order')
            glyph = ufo[name]
            glyph.contours.clear()
            glyph.components.clear()
            glyphset[name].drawPoints(glyph.getPointPen())
            glyph.width = font['hmtx'][name][0]
            replacements[glyph_directory+contents[name]] = writeGlyphToString(
                name, glyphObject=glyph, drawPointsFunc=glyph.drawPoints, formatVersion=2).encode('utf-8')
    masters.normalize_timestamp(font)
    stream = io.BytesIO()
    font.saveXML(stream, skipTables=['glyf', 'hmtx', 'loca'])
    replacements[table_name] = stream.getvalue()
    replace_zip_members(source, destination, replacements)
    return sorted(replacements)
