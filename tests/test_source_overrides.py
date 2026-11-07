"""Source edits must reach both the outline and the MATH construction data."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
from fontTools.otlLib.builder import buildMathTable
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from ufoLib2 import Font

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sources'))
import build as anodyne
import masters
from test_core_engineering import font_master


class SourceOverrideTests(unittest.TestCase):
    def test_outline_override_refreshes_constructions_and_retains_math_variation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / 'Roman'
            source_root.mkdir()
            document = DesignSpaceDocument()
            axis = AxisDescriptor()
            axis.tag, axis.name = 'wght', 'Weight'
            axis.minimum, axis.default, axis.maximum = 400, 400, 900
            document.addAxis(axis)
            for weight, name, rule, accent, kern in ((400, 'regular', 30, 300, -40), (900, 'black', 90, 150, -80)):
                path = root / f'{name}.ttf'
                font_master(path, rule, accent, kern)
                font = TTFont(path)
                buildMathTable(font, constants={'FractionRuleThickness': rule},
                               topAccentAttachments={'x': accent},
                               vertGlyphVariants={'H': [('H', 700)]},
                               vertGlyphAssembly={'H': ([('H', 1, 100, 100, 700)], 0)})
                ufo = source_root / f'{name}.ufoz'
                masters.export_font(font, ufo)
                source = SourceDescriptor()
                source.name, source.path, source.location = name, str(ufo), {'Weight': weight}
                document.addSource(source)
            designspace = source_root / 'Anodyne-Roman.designspace'
            document.write(designspace)

            overrides_root = root / 'overrides'
            override = overrides_root / 'Roman/regular.ufo'
            override.parent.mkdir(parents=True)
            ufo = Font()
            glyph = ufo.newGlyph('H')
            glyph.width = 500
            pen = glyph.getPen()
            pen.moveTo((50, 0)); pen.lineTo((50, 900))
            pen.lineTo((450, 900)); pen.lineTo((450, 0)); pen.closePath()
            ufo.save(override)

            variable = masters.compile_designspace(designspace, overrides_root)
            construction = variable['MATH'].table.MathVariants.VertGlyphConstruction[0]
            self.assertEqual(construction.MathGlyphVariantRecord[0].AdvanceMeasurement, 900)
            self.assertEqual(construction.GlyphAssembly.PartRecords[0].FullAdvance, 900)
            for weight, extent, rule, accent in ((400, 900, 30, 300), (900, 700, 90, 150)):
                instance = instantiateVariableFont(copy.deepcopy(variable), {'wght': weight})
                anodyne.refresh_math_metrics(instance)
                construction = instance['MATH'].table.MathVariants.VertGlyphConstruction[0]
                self.assertEqual(construction.MathGlyphVariantRecord[0].AdvanceMeasurement, extent)
                self.assertEqual(construction.GlyphAssembly.PartRecords[0].FullAdvance, extent)
                self.assertEqual(instance['MATH'].table.MathConstants.FractionRuleThickness.Value, rule)
                self.assertEqual(instance['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment[0].Value, accent)


if __name__ == '__main__':
    unittest.main()
