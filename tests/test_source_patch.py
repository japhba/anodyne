"""Incremental UFO edits preserve every unrelated compressed source record."""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources'))
import build
import masters
from source_patch import replace_zip_members, patch_ufoz
from test_core_engineering import font_master


def local_record(archive, name):
    info = archive.getinfo(name)
    archive.fp.seek(info.header_offset)
    header = archive.fp.read(30)
    filename, extra = struct.unpack('<HH', header[26:30])
    return header + archive.fp.read(filename+extra+info.compress_size)


class SourcePatchTests(unittest.TestCase):
    def test_replacement_preserves_compressed_records_and_has_no_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            original, changed, repeated = [Path(temporary)/name for name in ('old.zip','new.zip','repeat.zip')]
            with zipfile.ZipFile(original,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('unchanged.txt','same source\n'*1000)
                archive.writestr('changed.txt','old')
                archive.comment = b'preserved source note'
            for output in (changed, repeated):
                replace_zip_members(original, output, {'changed.txt':b'new source'})
            self.assertEqual(changed.read_bytes(), repeated.read_bytes())
            with zipfile.ZipFile(original) as old, zipfile.ZipFile(changed) as new:
                self.assertEqual(local_record(old,'unchanged.txt'),local_record(new,'unchanged.txt'))
                self.assertEqual(new.read('changed.txt'),b'new source')
                self.assertEqual(new.comment,old.comment)
                self.assertEqual(len(new.namelist()),2)
                self.assertIsNone(new.testzip())

    def test_patched_glif_and_layout_compile_to_the_corrected_font(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            ttf=directory/'base.ttf'
            font_master(ttf,30,300,-40)
            font=TTFont(ttf)
            original,output=directory/'base.ufoz',directory/'patched.ufoz'
            masters.export_font(copy.deepcopy(font),original)
            drawing=build.read(font,'H')
            drawing.contours=[[(x+29,y,on) for x,y,on in c] for c in drawing.contours]
            drawing.adv=520
            build.write(font,'H',drawing)
            font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment[0].Value=322
            changed=patch_ufoz(original,output,font,{'H'})
            self.assertEqual(len(changed),2)
            with zipfile.ZipFile(original) as old,zipfile.ZipFile(output) as new:
                self.assertEqual(set(old.namelist()),set(new.namelist()))
                for name in old.namelist():
                    if name not in changed:
                        self.assertEqual(local_record(old,name),local_record(new,name),name)
            rebuilt=masters.compile_font(output)
            self.assertEqual(list(rebuilt['glyf']['H'].coordinates),list(font['glyf']['H'].coordinates))
            self.assertEqual(rebuilt['hmtx']['H'],font['hmtx']['H'])
            self.assertEqual(rebuilt['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment[0].Value,322)
            self.assertEqual(rebuilt.getTableData('GPOS'),font.getTableData('GPOS'))


if __name__ == '__main__':
    unittest.main()
