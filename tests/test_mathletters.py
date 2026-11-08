"""Frozen mathematical letters gain real stroke motion without moving their text."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sources'))
from build import Outline, bbox, sane, structure, write
import mathletters


def rectangle(x0,y0,x1,y1,reverse=False):
    points=[(x0,y0,True),(x0,y1,True),(x1,y1,True),(x1,y0,True)]
    return list(reversed(points))if reverse else points


def ring(stroke=50,shift=0,advance=500):
    return Outline([rectangle(50+shift,0,400+shift,700),
                    rectangle(50+stroke+shift,stroke,400-stroke+shift,700-stroke,True)],adv=advance)


def font(drawings,cmap):
    builder=FontBuilder(1000,isTTF=True)
    names=['.notdef']+list(drawings)
    builder.setupGlyphOrder(names)
    glyphs={}
    for name in names:
        pen=TTGlyphPen(None)
        for contour in drawings.get(name,Outline()).contours:
            pen.moveTo(contour[0][:2])
            for point in contour[1:]:pen.lineTo(point[:2])
            pen.closePath()
        glyphs[name]=pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name:(round(drawings.get(name,Outline(adv=500)).adv),0)for name in names})
    builder.setupHorizontalHeader(ascent=900,descent=-250)
    builder.setupCharacterMap(cmap)
    builder.setupNameTable({'familyName':'Math test','styleName':'Regular','uniqueFontIdentifier':'Math test','fullName':'Math test','psName':'MathTest'})
    builder.setupOS2(sTypoAscender=900,sTypoDescender=-250,usWinAscent=900,usWinDescent=250)
    builder.setupPost();builder.setupMaxp()
    return builder.font


class StaticMathLetterTests(unittest.TestCase):
    def fixture(self):
        normal={}
        widths={100:18,400:50,700:75,900:95}
        for weight,width in widths.items():
            shift=-12 if weight>=700 else 0
            normal[weight]={'legacy':ring(50,shift,480+weight/100),
                            'legacy.dtls':ring(35),
                            'optical':ring(width),
                            'peer':ring(width),
                            'A':ring(50)}
        reference=font(normal[400],{0x210D:'legacy',0x1D538:'peer',0x41:'A'})
        addOpenTypeFeaturesFromString(reference,'feature dtls {sub legacy by legacy.dtls;}dtls; feature ssty {sub legacy by optical;}ssty;')
        noto={weight:font({'l':Outline([rectangle(20,0,20+width,700)],adv=200),
                          'legacy':ring(50)}, {ord('l'):'l',0x210D:'legacy'})
              for weight,width in widths.items()}
        return normal,reference,noto,{400:noto[400]}

    def test_scope_includes_historical_letters_and_unencoded_descendants(self):
        _,reference,_,_=self.fixture()
        self.assertEqual(mathletters.semantic_codepoints(reference),{0x210D,0x1D538})
        self.assertEqual(mathletters.semantic_names(reference),{'legacy','legacy.dtls','optical','peer'})

    def test_preserves_regular_advances_and_working_optical_designs(self):
        normal,reference,noto,condensed=self.fixture();before=deepcopy(normal)
        model=mathletters.apply_to_normal_anchors(normal,reference,noto,condensed)
        self.assertEqual(model.repaired_weight_names,{'legacy','legacy.dtls'})
        self.assertTrue({'legacy','legacy.dtls','optical'}<=model.forced_width_names)
        for weight in normal:
            self.assertEqual(normal[weight]['legacy'].adv,before[weight]['legacy'].adv)
            for name in('A','optical','peer'):
                self.assertEqual(normal[weight][name].contours,before[weight][name].contours)
            for name in model.repaired_weight_names:
                self.assertEqual(structure(normal[weight][name]),structure(before[weight][name]))
                self.assertTrue(sane(before[400][name],normal[weight][name]))
        self.assertEqual(normal[400]['legacy'].contours,before[400]['legacy'].contours)
        self.assertEqual(normal[400]['legacy.dtls'].contours,before[400]['legacy.dtls'].contours)

    def test_ink_thickens_and_thins_with_a_stable_vertical_envelope(self):
        normal,reference,noto,condensed=self.fixture()
        mathletters.apply_to_normal_anchors(normal,reference,noto,condensed)
        areas=[mathletters._area(normal[w]['legacy'])for w in(100,400,700,900)]
        self.assertEqual(areas,sorted(areas))
        self.assertEqual(len(set(areas)),4)
        for weight in normal:
            box=bbox(normal[weight]['legacy'].contours)
            self.assertAlmostEqual(box[1],0);self.assertAlmostEqual(box[3],700)
        repeat=mathletters.apply_to_normal_anchors(normal,reference,noto,condensed)
        self.assertEqual(repeat.repaired_weight_names,set())

    def test_frozen_composites_fail_before_creating_incompatible_masters(self):
        normal,reference,noto,condensed=self.fixture()
        for weight in normal:
            normal[weight]['legacy.dtls']=Outline(components=[('A',0,0,None)],adv=500)
        with self.assertRaisesRegex(ValueError,'component-level repair'):
            mathletters.apply_to_normal_anchors(normal,reference,noto,condensed)

    def test_native_component_response_preserves_working_wrappers(self):
        # The native parent records are identical. Only the nested child has
        # width deltas, as in Noto's lining/superior/inferior figure aliases.
        wide = font({'child':ring(50),'wrapper':Outline(),'alias':Outline(),
                     'frozen':ring(40),'frozen.wrapper':Outline()}, {})
        narrow = font({'child':Outline([rectangle(70,0,330,700),
                                        rectangle(120,50,280,650,True)],adv=400),
                       'wrapper':Outline(),'alias':Outline(),
                       'frozen':ring(40),'frozen.wrapper':Outline()}, {})
        for item in (wide,narrow):
            write(item,'wrapper',Outline(components=[('child',10,25,None)],adv=500))
            write(item,'alias',Outline(components=[('wrapper',3,-200,[[.7,0],[0,.7]])],adv=350))
            write(item,'frozen.wrapper',Outline(components=[('frozen',10,25,None)],adv=500))
        self.assertFalse(mathletters.native_width_static(wide,narrow,'wrapper'))
        self.assertFalse(mathletters.native_width_static(wide,narrow,'alias'))
        self.assertTrue(mathletters.native_width_static(wide,narrow,'frozen.wrapper'))

    def test_forced_width_graph_excludes_responsive_native_aliases(self):
        widths={100:18,400:50,700:75,900:95}
        normal={weight:{'child':ring(stroke),
                        'wrapper':Outline(components=[('child',0,0,None)],adv=500),
                        'alias':Outline(components=[('wrapper',0,-200,[[.7,0],[0,.7]])],adv=350),
                        'frozen':ring(stroke)}
                for weight,stroke in widths.items()}
        reference=font(normal[400],{0x1D7E5:'wrapper',0x1D7F7:'frozen'})
        addOpenTypeFeaturesFromString(reference,'feature ssty {sub wrapper by alias;}ssty;')
        noto={}
        for weight,stroke in widths.items():
            noto[weight]=font({'l':Outline([rectangle(20,0,20+stroke,700)],adv=200),
                               'child':ring(stroke),'wrapper':Outline(),'alias':Outline(),
                               'frozen':ring(stroke)}, {})
        narrow=font({'child':Outline([rectangle(70,0,330,700),
                                      rectangle(120,50,280,650,True)],adv=400),
                     'wrapper':Outline(),'alias':Outline(),'frozen':ring(50)}, {})
        for item in (*noto.values(),narrow):
            write(item,'wrapper',normal[400]['wrapper'])
            write(item,'alias',normal[400]['alias'])
        model=mathletters.apply_to_normal_anchors(normal,reference,noto,{400:narrow})
        self.assertEqual(model.repaired_weight_names,set())
        self.assertEqual(model.forced_width_names,{'frozen'})

    def test_sum_width_reference_marks_varying_import_and_all_descendants_dirty(self):
        # Imported double-struck summation differs from Native Noto. Its own
        # weight designs work, and Native's different drawing responds to width;
        # the explicit semantic Sigma reference still requires regenerated
        # imported condensed masters, including both levels of descendants.
        widths={100:18,400:50,700:75,900:95}
        targets=('sum','sum.rtlm','sum.s01','sum.rtlm.s01')
        normal={weight:{name:ring(width,advance=889)for name in targets}
                for weight,width in widths.items()}
        reference=font(normal[400],{0x2140:'sum'})
        addOpenTypeFeaturesFromString(reference,
            'feature rtlm {sub sum by sum.rtlm;}rtlm; '
            'feature ssty {sub sum by sum.s01; sub sum.rtlm by sum.rtlm.s01;}ssty;')
        noto={weight:font({'l':Outline([rectangle(20,0,20+width,700)],adv=200),
                          'sum':Outline([rectangle(70,-40,320,650),
                                         rectangle(70+width,-40+width,320-width,650-width,True)],adv=620)},
                         {ord('l'):'l',0x2140:'sum'})
              for weight,width in widths.items()}
        condensed={400:font({'l':Outline([rectangle(20,0,60,700)],adv=160),
                             'sum':Outline([rectangle(80,0,310,600)],adv=480)},
                            {ord('l'):'l',0x2140:'sum'})}
        before=deepcopy(normal)
        model=mathletters.apply_to_normal_anchors(normal,reference,noto,condensed)
        self.assertEqual(model.repaired_weight_names,set())
        self.assertTrue(set(targets)<=model.forced_width_names)
        for weight in normal:
            for name in targets:
                self.assertEqual(normal[weight][name].contours,before[weight][name].contours)
                self.assertEqual(normal[weight][name].adv,before[weight][name].adv)


if __name__=='__main__':unittest.main()
