"""Authored Greek families retain semantics, compatible masters and accent bases."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
import unicodedata

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sources'))
import build as font_build
import greekstyles


class GreekStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'src/lisnoti/font-Lisnoti/Lisnoti-ttf/Lisnoti-Regular.ttf'
        if not path.exists():raise unittest.SkipTest('Fetch pinned source faces first')
        cls.font=TTFont(path)
        cls.original_cmap=dict(cls.font.getBestCmap())
        info=cls.font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
        cls.original_accents=dict(zip(info.TopAccentCoverage.glyphs,
                                     (record.Value for record in info.TopAccentAttachment)))
        source=cls.font
        class Glyphs(dict):
            def __missing__(self,name):
                self[name]=font_build.read(source,name)
                return self[name]
        cls.normal={w:Glyphs() for w in (100,400,700,900)}
        cls.model=greekstyles.apply_to_normal_anchors(cls.normal,cls.font)

    def test_all_cases_variants_and_modern_accents_have_styled_glyphs(self):
        self.assertEqual(len(self.model.names),len(greekstyles.CODEPOINTS)*7)
        for tag,mapping in self.model.mappings.items():
            for cp in greekstyles.CODEPOINTS:
                with self.subTest(feature=tag,character=chr(cp)):
                    source=self.original_cmap[cp]
                    self.assertIn(source,mapping)
                    self.assertIn(mapping[source],self.font['glyf'])
        self.assertEqual(self.font.getBestCmap(),self.original_cmap,
                         'Greek styles must not change Unicode characters or invent PUA notation')

    def test_master_structures_and_monospaced_cells_are_consistent(self):
        for name in self.model.names:
            expected=font_build.structure(self.normal[400][name])
            for weight,glyphs in self.normal.items():
                with self.subTest(glyph=name,weight=weight):
                    self.assertEqual(font_build.structure(glyphs[name]),expected)
                    if name.endswith('.monospace'):
                        self.assertEqual(glyphs[name].adv,680)

    def test_modern_accents_combine_styled_bases_and_weighted_accent_components(self):
        for tag,spec in greekstyles.FEATURES.items():
            for character in greekstyles.MODERN_ACCENTS:
                name=self.model.mappings[tag][self.original_cmap[ord(character)]]
                outline=self.normal[400][name]
                self.assertGreaterEqual(len(outline.components),2)
                self.assertTrue(outline.components[0][0].endswith('.'+spec['style']))
                self.assertEqual(outline.adv,self.normal[400][outline.components[0][0]].adv)

    def test_polytonic_accents_and_iota_subscript_keep_the_styled_base(self):
        for tag,spec in greekstyles.FEATURES.items():
            for character in ('ἄ','ἆ','ᾄ','ᾌ','ᾳ','ῇ','ΐ','Ἄ'):
                name=self.model.mappings[tag][self.original_cmap[ord(character)]]
                outline=self.normal[400][name]
                self.assertGreaterEqual(len(outline.components),2)
                self.assertTrue(outline.components[0][0].endswith('.'+spec['style']))
                if '\u0345' in unicodedata.normalize('NFD',character):
                    mark=outline.components[-1]
                    points=[p for c in greekstyles.flatten(self.normal[400][mark[0]],self.normal[400]) for p in c]
                    body=self.normal[400][outline.components[0][0]]
                    bottom=min(p[1] for c in greekstyles.flatten(body,self.normal[400]) for p in c)
                    self.assertLess(max(p[1]+mark[2] for p in points),min(0,bottom))

    def test_existing_mathematical_and_optical_greek_inputs_use_the_selected_family(self):
        optical=greekstyles.optical_alternates(self.font)
        for tag,mapping in self.model.mappings.items():
            base=self.original_cmap[ord('α')]
            styled=self.original_cmap[0x1D6FC]  # mathematical italic alpha
            self.assertEqual(mapping[styled],mapping[base])
            for alternate in optical.get(styled,[]):
                self.assertEqual(mapping[alternate],mapping[base])

    def test_greek_specific_styles_are_distinct_drawings(self):
        source=self.original_cmap[ord('Γ')]
        shapes=[self.normal[400][self.model.mappings[tag][source]] for tag in ('ss08','ss10','ss12','ss13','ss14')]
        self.assertEqual(len({str(font_build.structure(shape)) for shape in shapes}),5)
        source_beta=self.original_cmap[ord('β')]
        source_rho=self.original_cmap[ord('ρ')]
        for tag in greekstyles.FEATURES:
            for base,variant in (('ε','ϵ'),('θ','ϑ'),('φ','ϕ'),('π','ϖ'),('ρ','ϱ'),('κ','ϰ'),('σ','ς')):
                a=self.normal[400][self.model.mappings[tag][self.original_cmap[ord(base)]]]
                b=self.normal[400][self.model.mappings[tag][self.original_cmap[ord(variant)]]]
                self.assertNotEqual(str(a.contours)+str(a.components),str(b.contours)+str(b.components))

    def test_lowercase_homographs_match_the_greek_xheight(self):
        for tag in greekstyles.FEATURES:
            for character in 'γονρυϲ':
                name=self.model.mappings[tag][self.original_cmap[ord(character)]]
                points=[p for c in greekstyles.flatten(self.normal[400][name],self.normal[400]) for p in c]
                self.assertAlmostEqual(max(p[1] for p in points),510)

    def test_math_attachments_follow_source_anchors_upper_ink_and_composite_bases(self):
        info=self.font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
        attachments=dict(zip(info.TopAccentCoverage.glyphs,
                             (record.Value for record in info.TopAccentAttachment)))
        for tag,spec in greekstyles.FEATURES.items():
            mapping=self.model.mappings[tag]
            capital=self.original_cmap[greekstyles.latin_codepoint('A',spec['style'])]
            if spec['style']=='chancery':
                capital=greekstyles.single_mapping(self.font,'ss01').get(capital,capital)
            if capital in self.original_accents:
                self.assertEqual(attachments[mapping[self.original_cmap[ord('Α')]]],
                                 self.original_accents[capital])
            for character in 'ιλρ':
                name=mapping[self.original_cmap[ord(character)]]
                outline=self.normal[400][name]
                if character=='ρ':
                    cp=greekstyles.latin_codepoint('p',spec['style'])
                    donor=self.original_cmap[cp]
                    regular=self.normal[400][donor]
                    height=max(p[1] for c in greekstyles.flatten(regular,self.normal[400]) for p in c)
                    value=self.original_accents.get(donor)
                    if value is not None and spec['style']!='monospace':
                        self.assertEqual(attachments[name],round(value*510/height))
                else:
                    self.assertEqual(attachments[name],round(greekstyles.upper_body_center(outline,self.normal[400])))
            iota=self.normal[400][mapping[self.original_cmap[ord('ι')]]]
            if spec['style']=='monospace':
                self.assertEqual(iota.adv,680)
            else:
                self.assertLess(iota.adv,400)
            for base,accented in (('α','ἄ'),('Α','ᾌ'),('ι','ΐ')):
                self.assertEqual(attachments[mapping[self.original_cmap[ord(base)]]],
                                 attachments[mapping[self.original_cmap[ord(accented)]]])

    def test_new_glyphs_have_math_accent_data_and_binary_tables_compile(self):
        coverage=self.font['MATH'].table.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs
        self.assertTrue(set(self.model.names).issubset(coverage))
        output=BytesIO();self.font.save(output)
        rebuilt=TTFont(BytesIO(output.getvalue()))
        self.assertEqual(len(rebuilt.getGlyphOrder()),len(set(rebuilt.getGlyphOrder())))
        features={r.FeatureTag:r for r in rebuilt['GSUB'].table.FeatureList.FeatureRecord}
        for tag,spec in greekstyles.FEATURES.items():
            label=features[tag].Feature.FeatureParams.UINameID
            self.assertEqual(rebuilt['name'].getDebugName(label),spec['name'])
        shaping=hb.Font(hb.Face(output.getvalue()))
        math_info=rebuilt['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
        attachment=dict(zip(math_info.TopAccentCoverage.glyphs,
                            (record.Value for record in math_info.TopAccentAttachment)))
        for tag in greekstyles.FEATURES:
            for character in 'ιλρ':
                name=self.model.mappings[tag][self.original_cmap[ord(character)]]
                self.assertEqual(shaping.get_math_glyph_top_accent_attachment(rebuilt.getGlyphID(name)),
                                 attachment[name])
            for text in ('ἄ',unicodedata.normalize('NFD','ἄ')):
                buffer=hb.Buffer();buffer.add_str(text);buffer.guess_segment_properties()
                hb.shape(shaping,buffer,{tag:1})
                self.assertTrue(all('.anodyne.grk.' in rebuilt.getGlyphName(g.codepoint)
                                    for g in buffer.glyph_infos),text)


if __name__=='__main__':unittest.main()
