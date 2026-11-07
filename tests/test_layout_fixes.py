"""GSUB-only script corrections must equal a fresh editable-source build."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sources'))
from layout_fixes import apply_layout_fixes
import masters


def source_font(path, growth):
    names = ['.notdef', 'u1D62F', 'u1D62F.ssty1', 'u1D62F.ssty2']
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({0x1D62F: 'u1D62F'})
    glyphs = {}
    for index, name in enumerate(names):
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0)); pen.lineTo((50, 500))
        pen.lineTo((100 + growth + index, 500)); pen.lineTo((100 + growth + index, 0)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (400 + growth, 50) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'ScriptLayoutTest', 'styleName': 'Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font,
        'feature ssty { sub u1D62F from [u1D62F.ssty1 u1D62F.ssty2]; } ssty;')
    buildMathTable(builder.font, topAccentAttachments={'u1D62F': 200, 'u1D62F.ssty2': 210})
    builder.save(path)


def designspace(paths):
    document = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.tag, axis.name = 'wght', 'Weight'
    axis.minimum, axis.default, axis.maximum = 400, 400, 900
    document.addAxis(axis)
    for weight, path in zip((400, 900), paths):
        source = SourceDescriptor()
        source.path, source.location = str(path), {'Weight': weight}
        document.addSource(source)
    return document


class LayoutFixTests(unittest.TestCase):
    def test_table_patch_equals_fresh_source_compilation_and_preserves_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, compiled = [], []
            for weight, growth in ((400, 0), (900, 80)):
                source = root / f'{weight}.ttf'
                source_font(source, growth)
                original.append(source)
                ufo = root / f'{weight}.ufoz'
                masters.export_font(TTFont(source), ufo)
                font = masters.compile_font(ufo)
                output = root / f'{weight}-compiled.ttf'
                font.save(output)
                compiled.append(output)
            cached, _, _ = build_variable(designspace(original))
            expected, _, _ = build_variable(designspace(compiled))
            preserved = {tag: cached.getTableData(tag) for tag in ('glyf', 'gvar', 'HVAR', 'MATH', 'hmtx')}
            changes = apply_layout_fixes(cached)
            self.assertEqual(len(changes), 1)
            self.assertEqual(cached.getTableData('GSUB'), expected.getTableData('GSUB'))
            for tag, data in preserved.items():
                self.assertEqual(cached.getTableData(tag), data, tag)
            self.assertEqual(apply_layout_fixes(cached), [])

    def test_unexpected_upstream_target_requires_policy_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'font.ttf'
            source_font(path, 0)
            font = TTFont(path)
            font['GSUB'].table.LookupList.Lookup[0].SubTable[0].alternates['u1D62F'][0] = 'u1D62F'
            with self.assertRaisesRegex(ValueError, 'review layout policy'):
                apply_layout_fixes(font)


if __name__ == '__main__':
    unittest.main()
