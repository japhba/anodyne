#!/usr/bin/env python3
"""Anodyne next to the other OpenType maths fonts.

The fonts are the ones listed in the answers to "Which OpenType math fonts are
available?" (https://tex.stackexchange.com/questions/425098), except those whose
licence is not free. For every font this script

  fetch    downloads the maths font and its text companion into a cache outside
           the repository (CTAN through ftp.fau.de, GitHub, Google Fonts),
  analyse  reads the font with fontTools: glyphs, MATH table, script forms,
           stylistic sets and character variants with their names, alphabets,
           licence (name IDs 13 and 14),
  render   typesets one sample with LuaLaTeX and unicode-math (one LuaLaTeX run
           per font), plus a strip for each stylistic set or character variant
           (default glyphs above, the alternates below), and turns every page
           into a small SVG of glyph outlines in images/mathfonts/,
  svg      (only when asked) converts the PDFs of the last render again,
  page     writes mathfonts.json and the section of index.html between
           <!-- mathfonts:start --> and <!-- mathfonts:end -->.

No font file goes into the repository or the page: only outlines as SVG paths.

    PYTHONPATH=<fontTools + brotli> python3 sources/mathfonts/build.py [step ...] [--only id,id]

Steps default to fetch, analyse, render and page. Environment: MATHFONTS_CACHE
(downloads, LuaLaTeX work files), MATHFONTS_TEXMFVAR (one luaotfload cache for
every run). On a machine with a systemd user manager each LuaLaTeX run gets its
own unit capped at 2 GB (--no-systemd runs it directly); a font's first load,
which costs the most memory, happens in a run of its own. With warm caches the
whole build takes about three minutes.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRATCH = Path('/mnt/HC_Volume_107166861/jan/anodyne-mathfonts')
CACHE = Path(os.environ.get('MATHFONTS_CACHE', SCRATCH / 'cache'))
TEXMFVAR = Path(os.environ.get('MATHFONTS_TEXMFVAR', SCRATCH / 'texmfvar'))
WORK = CACHE / 'work'
OUT = REPO / 'images' / 'mathfonts'
JSON_OUT = REPO / 'mathfonts.json'
INDEX = REPO / 'index.html'

CTAN = 'https://ftp.fau.de/ctan/'
GH = 'https://raw.githubusercontent.com/'
SE = 'https://tex.stackexchange.com/a/'
A1, A2 = '425099', '711737'  # the two answers that list the fonts


def ctan(path):
    return CTAN + path


# ---------------------------------------------------------------------------
# the fonts. math/text: URL (or a path in this repository); bold: the bold
# maths files the same distribution ships (listed, not downloaded);
# opts: fontspec options for \setmathfont as the answer gives them.

FONTS = [
    dict(id='anodyne', name='Anodyne', group='sans',
         math='fonts/static/Anodyne-Regular.ttf', text='fonts/static/Anodyne-Regular.ttf', text_name='Anodyne',
         bold=['Anodyne-Bold.ttf'], home='https://github.com/japhba/anodyne',
         note='Lisnoti with every weight from 100 to 900, a width and a grade axis, and formulas at Computer Modern’s proportions (TeX’s constants, delimiters that grow as Computer Modern’s do); the MATH table is in all four static files.'),
    dict(id='lisnoti', name='Lisnoti', group='sans', answer=A2,
         math=ctan('fonts/lisnoti/Lisnoti-Regular.ttf'), text=ctan('fonts/lisnoti/Lisnoti-Regular.ttf'), text_name='Lisnoti',
         bold=['Lisnoti-Bold.ttf'], home='https://ctan.org/pkg/lisnoti',
         note='Noto Sans with Noto Sans Math’s MATH table, the font Anodyne is forked from.'),
    dict(id='notosansmath', name='Noto Sans Math', group='sans', answer=A1,
         math=GH + 'notofonts/notofonts.github.io/main/fonts/NotoSansMath/unhinted/otf/NotoSansMath-Regular.otf',
         text=GH + 'notofonts/notofonts.github.io/main/fonts/NotoSans/unhinted/otf/NotoSans-Regular.otf', text_name='Noto Sans',
         bold=[], home='https://github.com/notofonts/math'),
    dict(id='firamath', name='Fira Math', group='sans', answer=A1,
         math=ctan('fonts/firamath/FiraMath-Regular.otf'), text=ctan('fonts/fira/opentype/FiraSans-Regular.otf'), text_name='Fira Sans',
         bold=[], home='https://ctan.org/pkg/firamath',
         note='The answer sets FiraGO as text; Fira Sans, which FiraGO extends, stands in for it here.'),
    dict(id='letesans', name='Lete Sans Math', group='sans', answer=A1,
         math=ctan('fonts/lete-sans-math/LeteSansMath.otf'), text=GH + 'google/fonts/main/ofl/lato/Lato-Regular.ttf', text_name='Lato',
         bold=['LeteSansMath-Bold.otf'], home='https://ctan.org/pkg/lete-sans-math'),
    dict(id='newcmsans', name='New Computer Modern Sans Math', group='sans', answer=A1,
         math=ctan('fonts/newcomputermodern/otf/NewCMSansMath-Regular.otf'), text=ctan('fonts/newcomputermodern/otf/NewCMSans10-Regular.otf'),
         text_name='New Computer Modern Sans', bold=[], home='https://ctan.org/pkg/newcomputermodern'),
    dict(id='kpsans', name='KpMath Sans', group='sans', answer=A1,
         math=ctan('fonts/kpfonts-otf/fonts/KpMathSans-Regular.otf'), text=ctan('fonts/kpfonts-otf/fonts/KpSans-Regular.otf'), text_name='KpSans',
         bold=['KpMathSans-Bold.otf'], home='https://ctan.org/pkg/kpfonts-otf'),
    dict(id='plexmath', name='IBM Plex Math', group='sans', answer=A2,
         math=ctan('fonts/plex/opentype/IBMPlexMath-Regular.otf'), text=ctan('fonts/plex/opentype/IBMPlexSerif-Regular.otf'), text_name='IBM Plex Serif',
         bold=[], home='https://github.com/IBM/plex'),
    dict(id='arsenalmath', name='Arsenal Math', group='sans', answer=A2,
         math=ctan('fonts/arsenal-math/otf/ArsenalMath-Sans.otf'), text=GH + 'google/fonts/main/ofl/arsenal/Arsenal-Regular.ttf', text_name='Arsenal',
         bold=['ArsenalMath-SansBold.otf'], home='https://ctan.org/pkg/arsenal-math'),
    dict(id='luciole', name='Luciole Math', group='sans', answer=A2,
         math=ctan('fonts/luciole/Luciole-Math.otf'), text=ctan('fonts/luciole/Luciole-Regular.ttf'), text_name='Luciole',
         bold=['Luciole-Math-Bold.otf'], home='https://www.luciole-vision.com/en/math.html'),
    dict(id='pennstander', name='Pennstander Math', group='sans', answer=A2,
         math=ctan('fonts/pennstander-otf/fonts/PennstanderMath-Regular.otf'), text=ctan('fonts/pennstander-otf/fonts/Pennstander-Regular.otf'),
         text_name='Pennstander', bold=['8 more weights, Thin to Black'], home='https://github.com/juliusross1/Pennstander'),
    dict(id='neohellenic', name='GFS Neohellenic Math', group='sans', answer=A1,
         math=ctan('fonts/gfsneohellenicmath/GFSNeohellenicMath.otf'), text=ctan('fonts/greek/gfs/gfsneohellenic/opentype/GFSNeohellenic.otf'),
         text_name='GFS Neohellenic', bold=[], home='https://ctan.org/pkg/gfsneohellenicmath',
         licence='SIL Open Font License 1.1', licence_source='the README of its CTAN package; the name table names no licence'),

    dict(id='latinmodern', name='Latin Modern Math', group='serif', answer=A1,
         math=ctan('fonts/lm-math/opentype/latinmodern-math.otf'), text=ctan('fonts/lm/fonts/opentype/public/lm/lmroman10-regular.otf'),
         text_name='Latin Modern Roman', bold=[], home='https://ctan.org/pkg/lm-math',
         note='unicode-math’s default.'),
    dict(id='newcm', name='New Computer Modern Math', group='serif', answer=A1,
         math=ctan('fonts/newcomputermodern/otf/NewCMMath-Book.otf'), text=ctan('fonts/newcomputermodern/otf/NewCM10-Book.otf'),
         text_name='New Computer Modern Book', bold=['NewCMMath-Bold.otf', 'NewCMMath-Regular.otf (lighter)'], home='https://ctan.org/pkg/newcomputermodern',
         note='Shown in the Book weight, fontsetup’s default.'),
    dict(id='mlmodern', name='MLModern Math', group='serif', answer=A2,
         math=ctan('fonts/mlmodern/otf/mlmodern-math.otf'), text=ctan('fonts/mlmodern/otf/mlmroman10-regular.otf'), text_name='MLModern',
         bold=[], home='https://ctan.org/pkg/mlmodern'),
    dict(id='concrete', name='Concrete Math', group='serif', answer=A1,
         math=ctan('fonts/concmath-otf/Concrete-Math.otf'), text=ctan('fonts/cm-unicode/fonts/otf/cmunorm.otf'), text_name='CMU Concrete',
         bold=['Concrete-Math-Bold.otf'], home='https://ctan.org/pkg/concmath-otf'),
    dict(id='eulermath', name='Euler Math', group='serif', answer=A1,
         math=ctan('fonts/euler-math/Euler-Math.otf'), text=ctan('fonts/cm-unicode/fonts/otf/cmunorm.otf'), text_name='CMU Concrete',
         bold=[], home='https://ctan.org/pkg/euler-math'),
    dict(id='neoeuler', name='Neo Euler', group='serif', answer=A1,
         math=GH + 'khaledhosny/euler-otf/master/euler.otf', text=ctan('fonts/cm-unicode/fonts/otf/cmunorm.otf'), text_name='CMU Concrete',
         bold=[], home='https://github.com/khaledhosny/euler-otf', unimath='math-style=upright',
         note='Upright letters only, so set with math-style=upright as in the answer; abandoned in 2010 and incomplete.'),
    dict(id='termes', name='TeX Gyre Termes Math', group='serif', answer=A1,
         math=ctan('fonts/tex-gyre-math/opentype/texgyretermes-math.otf'), text=ctan('fonts/tex-gyre/opentype/texgyretermes-regular.otf'),
         text_name='TeX Gyre Termes', bold=[], home='https://ctan.org/pkg/tex-gyre-math-termes'),
    dict(id='pagella', name='TeX Gyre Pagella Math', group='serif', answer=A1,
         math=ctan('fonts/tex-gyre-math/opentype/texgyrepagella-math.otf'), text=ctan('fonts/tex-gyre/opentype/texgyrepagella-regular.otf'),
         text_name='TeX Gyre Pagella', bold=[], home='https://ctan.org/pkg/tex-gyre-math-pagella'),
    dict(id='bonum', name='TeX Gyre Bonum Math', group='serif', answer=A1,
         math=ctan('fonts/tex-gyre-math/opentype/texgyrebonum-math.otf'), text=ctan('fonts/tex-gyre/opentype/texgyrebonum-regular.otf'),
         text_name='TeX Gyre Bonum', bold=[], home='https://ctan.org/pkg/tex-gyre-math-bonum'),
    dict(id='schola', name='TeX Gyre Schola Math', group='serif', answer=A1,
         math=ctan('fonts/tex-gyre-math/opentype/texgyreschola-math.otf'), text=ctan('fonts/tex-gyre/opentype/texgyreschola-regular.otf'),
         text_name='TeX Gyre Schola', bold=[], home='https://ctan.org/pkg/tex-gyre-math-schola'),
    dict(id='dejavu', name='TeX Gyre DejaVu Math', group='serif', answer=A1,
         math=ctan('fonts/tex-gyre-math/opentype/texgyredejavu-math.otf'), text=ctan('fonts/dejavu/truetype/DejaVuSerif.ttf'), text_name='DejaVu Serif',
         bold=[], home='https://ctan.org/pkg/tex-gyre-math-dejavu', opts='Scale=MatchLowercase',
         note='The DejaVu project ships the same font as DejaVu Math TeX Gyre.'),
    dict(id='stixtwo', name='STIX Two Math', group='serif', answer=A1,
         math=ctan('fonts/stix2-otf/STIXTwoMath-Regular.otf'), text=ctan('fonts/stix2-otf/STIXTwoText-Regular.otf'), text_name='STIX Two Text',
         bold=[], home='https://github.com/stipub/stixfonts'),
    dict(id='stix', name='STIX Math', group='serif', answer=A1,
         math=ctan('fonts/stix/opentype/STIXMath-Regular.otf'), text=ctan('fonts/stix/opentype/STIX-Regular.otf'), text_name='STIX',
         bold=[], home='https://ctan.org/pkg/stix', note='The first STIX release, succeeded by STIX Two.'),
    dict(id='xits', name='XITS Math', group='serif', answer=A1,
         math=ctan('fonts/xits/XITSMath-Regular.otf'), text=ctan('fonts/xits/XITS-Regular.otf'), text_name='XITS',
         bold=['XITSMath-Bold.otf'], home='https://github.com/aliftype/xits'),
    dict(id='libertinus', name='Libertinus Math', group='serif', answer=A1,
         math=ctan('fonts/libertinus-fonts/otf/LibertinusMath-Regular.otf'), text=ctan('fonts/libertinus-fonts/otf/LibertinusSerif-Regular.otf'),
         text_name='Libertinus Serif', bold=[], home='https://github.com/alerque/libertinus'),
    dict(id='asana', name='Asana Math', group='serif', answer=A1,
         math=ctan('fonts/Asana-Math/Asana-Math.otf'), text=ctan('fonts/tex-gyre/opentype/texgyrepagella-regular.otf'), text_name='TeX Gyre Pagella',
         bold=[], home='https://ctan.org/pkg/asana-math', opts='Scale=MatchUppercase'),
    dict(id='garamond', name='Garamond Math', group='serif', answer=A1,
         math=ctan('fonts/garamond-math/Garamond-Math.otf'), text=ctan('fonts/ebgaramond/opentype/EBGaramond-Regular.otf'), text_name='EB Garamond',
         bold=[], home='https://ctan.org/pkg/garamond-math', opts='Scale=MatchUppercase'),
    dict(id='erewhon', name='Erewhon Math', group='serif', answer=A1,
         math=ctan('fonts/erewhon-math/Erewhon-Math.otf'), text=ctan('fonts/erewhon/opentype/Erewhon-Regular.otf'), text_name='Erewhon',
         bold=['Erewhon-Math-Bold.otf'], home='https://ctan.org/pkg/erewhon-math'),
    dict(id='kpmath', name='KpMath', group='serif', answer=A1,
         math=ctan('fonts/kpfonts-otf/fonts/KpMath-Regular.otf'), text=ctan('fonts/kpfonts-otf/fonts/KpRoman-Regular.otf'), text_name='KpRoman',
         bold=['KpMath-Bold.otf', 'KpMath-Semibold.otf', 'KpMath-Light.otf'], home='https://ctan.org/pkg/kpfonts-otf'),
    dict(id='xcharter', name='XCharter Math', group='serif', answer=A1,
         math=ctan('fonts/xcharter-math/XCharter-Math.otf'), text=ctan('fonts/xcharter/opentype/XCharter-Roman.otf'), text_name='XCharter',
         bold=['XCharter-Math-Bold.otf'], home='https://ctan.org/pkg/xcharter-math'),
    dict(id='oldstandard', name='Old Standard Math', group='serif', answer=A2,
         math=ctan('fonts/oldstandard/opentype/OldStandard-Math.otf'), text=ctan('fonts/oldstandard/opentype/OldStandard-Regular.otf'),
         text_name='Old Standard', bold=[], home='https://ctan.org/pkg/oldstandard'),
    dict(id='pl46', name='PL46 Math', group='serif', answer=A2,
         math=ctan('fonts/pl46-fonts/PL46-Math.otf'), text=ctan('fonts/pl46-fonts/PL46-Regular.otf'), text_name='PL46',
         bold=[], home='https://ctan.org/pkg/pl46-fonts'),
    dict(id='berenis', name='Berenis ADF Pro Math', group='serif', answer=A1, nomath=True,
         math='http://arkandis.tuxfamily.org/fonts/Berenis-Pro-20150322.zip#BerenisADFProMath-Regular.otf',
         text=ctan('fonts/berenisadf/opentype/BerenisADFPro-Regular.otf'), text_name='Berenis ADF Pro',
         bold=[], home='http://arkandis.tuxfamily.org/adffonts.html', unimath='math-style=upright',
         note='No MATH table: as in the answer, its letters and symbols sit on Latin Modern Math, which supplies the layout.'),
]

# not shown: the licence does not let us obtain or use the font freely
NOT_SHOWN = [
    dict(name='Cambria Math', answer=A1, licence='Proprietary (Microsoft, from Monotype); ships with Windows and Office'),
    dict(name='Lucida Bright Math', answer=A1, licence='Commercial (Bigelow & Holmes), sold by TUG'),
    dict(name='Minion Math', answer=A1, licence='Commercial (Johannes Küster, typoma)'),
    dict(name='MTPro2 Math', answer=A2, licence='Commercial (PCTeX); the free Lite set is under a proprietary EULA that forbids modifying or passing it on, and the OpenType font is converted from it'),
    dict(name='NagwaTK Math', answer=A2, licence='Creative Commons BY-NC-ND (non-commercial, no derivatives); the download page also sits behind a browser check'),
]

SAMPLE_TEXT = r'Let $f$ be analytic in $G$ except at $a_1,\dots,a_m$. Then'
SAMPLE_MATH = [
    r'\sum_{k=1}^{n} \frac{\alpha_k\,x^{2k}}{\sqrt{1+\beta_k^{2}}}'
    r' \le \int_{-\infty}^{\infty} \left| \frac{\partial\Phi}{\partial t} \right| \mathrm{d}t',
    r"f''(\xi) = \left[ \prod_{i=1}^{m} \lambda_i \right]^{1/m},"
    # 𝒜 ℱ 𝔤 ℂ typed as characters, which is what \mathcal{A}, \mathscr{F}, \mathfrak{g} and
    # \mathbb{C} become: unicode-math's numeric ranges (the grey fallback) reach typed
    # characters, not the alphabet commands
    '\\quad 𝒜,\\ ℱ \\subset 𝔤 \\otimes ℂ^{n}',
]
# the maths characters unicode-math draws from the maths font for this sample; a font
# lacking one in its cmap gets it from Latin Modern Math, in grey (LuaTeX would
# otherwise take unmapped glyphs by name, or leave a gap)
_TEX_STYLE = [0x1D453, 0x1D43A, 0x1D44E, 0x1D45A, 0x1D458, 0x1D45B, 0x1D465, 0x1D461, 0x1D456,  # f G a m k n x t i
              0x1D6FC, 0x1D6FD, 0x1D706, 0x1D709, 0x1D715, 0x03A6]  # alpha beta lambda xi partial Phi
_UPRIGHT = [ord(c) for c in 'fGamknxti'] + [0x03B1, 0x03B2, 0x03BB, 0x03BE, 0x2202, 0x03A6]
_SYMBOLS = [ord(c) for c in '12+=,()[]|/'] + [0x2026, 0x2211, 0x222B, 0x220F, 0x221A, 0x221E, 0x2264, 0x2212,
                                             0x2282, 0x2297, 0x2033, 0x2102, 0x1D49C, 0x2131, 0x1D524]
SAMPLE_CODEPOINTS = {'TeX': _TEX_STYLE + _SYMBOLS, 'upright': _UPRIGHT + _SYMBOLS}
SAMPLE_PT = 13          # text and maths size of the sample
SAMPLE_WIDTH_PT = 320   # every sample is this wide, so all fonts appear at one scale
STRIP_PT = 20           # glyph size in the feature strips
STRIP_MAX = 6           # characters shown per stylistic set
ALPHABET_TOTAL = sum(1 for c in range(0x1D400, 0x1D800) if unicodedata.name(chr(c), ''))


# ---------------------------------------------------------------------------
# fetch

def local_or_cached(spec, fid):
    """Path of a font file: the repository's own, or the cached download."""
    if not re.match(r'https?://', spec):
        return REPO / spec
    url, _, member = spec.partition('#')
    name = member or url.rsplit('/', 1)[1]
    return CACHE / 'fonts' / fid / name


def fetch(font):
    for key in ('math', 'text'):
        spec = font[key]
        dest = local_or_cached(spec, font['id'])
        if dest.exists():
            continue
        url, _, member = spec.partition('#')
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f'  fetch {url}', flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'anodyne-mathfonts/1'})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if member:  # a file inside a zip
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [n for n in z.namelist() if n.endswith('/' + member) or n == member]
                data = z.read(names[0])
        tmp = dest.with_suffix(dest.suffix + '.part')
        tmp.write_bytes(data)
        tmp.rename(dest)


# ---------------------------------------------------------------------------
# analyse

LICENCES = [
    (r'Open Font License|\bOFL\b|scripts\.sil\.org|openfontlicense', 'SIL Open Font License 1.1'),
    (r'GUST Font License|gust\.org\.pl/fonts/licenses', 'GUST Font License'),
    (r'GNU General Public License|copyleft/gpl', 'GNU GPL 2+ with font exception'),
    (r'LaTeX Project Public License|LPPL', 'LaTeX Project Public License'),
    (r'Apache', 'Apache License 2.0'),
    (r'dejavu-fonts\.org/wiki/License|Bitstream Vera', 'Bitstream Vera licence, DejaVu changes public domain'),
    (r'creativecommons\.org/licenses/by/4|CC.BY 4', 'Creative Commons BY 4.0'),
]


def licence_label(text):
    for pat, label in LICENCES:
        if re.search(pat, text or '', re.I):
            return label
    return ''


def name_of(font, nid):
    n = font['name'].getName(nid, 3, 1, 0x409) or font['name'].getName(nid, 1, 0, 0)
    if n is None:
        rec = [r for r in font['name'].names if r.nameID == nid]
        n = rec[0] if rec else None
    return n.toUnicode().strip() if n else ''


def unwrap(lookup):
    for st in lookup.SubTable:
        t = lookup.LookupType
        if t == 7:
            t, st = st.ExtSubTable.LookupType, st.ExtSubTable
        yield t, st


def feature_mapping(gsub, tag):
    """glyph -> first replacement for every single or alternate substitution of a feature."""
    lookups, params = [], None
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == tag:
            lookups += fr.Feature.LookupListIndex
            params = params or fr.Feature.FeatureParams
    mapping, other = {}, 0
    for li in sorted(set(lookups)):
        for t, st in unwrap(gsub.LookupList.Lookup[li]):
            if t == 1:
                for g, a in st.mapping.items():
                    mapping.setdefault(g, a)
            elif t == 3:
                for g, alts in st.alternates.items():
                    if alts:
                        mapping.setdefault(g, alts[0])
            else:
                other += 1
    return {g: a for g, a in mapping.items() if g != a}, params, other


STYLES = ('BOLD', 'ITALIC', 'SCRIPT', 'FRAKTUR', 'DOUBLE-STRUCK', 'SANS-SERIF', 'MONOSPACE')
SYMBOL_KINDS = [
    (r'INTEGRAL', 'integrals'), (r'ARROW|HARPOON', 'arrows'), (r'N-ARY|SUMMATION|PRODUCT', 'big operators'),
    (r'SQUARE ROOT|CUBE ROOT|FOURTH ROOT', 'radicals'), (r'SUBSET|SUPERSET', 'subsets'),
    (r'^NOT |DOES NOT|NEITHER|SOLIDUS', 'negated relations'), (r'PRIME', 'primes'),
    (r'LESS-THAN|GREATER-THAN|SIMILAR|EQUAL|EQUIVALENT|PRECEDES|SUCCEEDS', 'relations'),
    (r'PARENTHESIS|BRACKET|BRACE', 'brackets'), (r'CIRCLED', 'circled operators'), (r'PLANCK', 'Planck constants'),
    (r'PARTIAL', 'partial derivatives'), (r'DIGIT|VULGAR FRACTION|SUPERSCRIPT', 'figures'),
]


def kind_of(cp):
    """A plain-words kind for a character: 'script capitals', 'italic Greek small letters', 'integrals' …"""
    ch = chr(cp)
    name = unicodedata.name(ch, '')
    cat = unicodedata.category(ch)
    words = name.replace('BLACK-LETTER', 'FRAKTUR').split()
    if cat.startswith('L'):
        base = unicodedata.normalize('NFKD', ch)[0]
        styles = [w.lower() for w in STYLES if w in words]
        greek = 0x370 <= ord(base) <= 0x3FF
        case = 'capitals' if 'CAPITAL' in words else 'small letters' if 'SMALL' in words or cat == 'Ll' else 'letters'
        if case == 'letters' and words:
            return ' '.join(styles + [words[0].capitalize() if words[0] != 'MATHEMATICAL' else words[1].capitalize(), 'letters'])
        return ' '.join(styles + (['Greek'] if greek else []) + [case])
    if cat == 'Nd':
        return ' '.join([w.lower() for w in STYLES if w in words] + ['figures'])
    for pat, label in SYMBOL_KINDS:
        if re.search(pat, name):
            return label
    return name.lower()


def pick(cps, n=STRIP_MAX):
    """A few characters from every kind a feature changes: round robin over the kinds,
    the commonest and plainest first, one character per base letter."""
    groups = {}
    for cp in cps:
        groups.setdefault(kind_of(cp), []).append(cp)
    def plain(cp):  # True for letters with accents or marks (named so for the sort: those come last)
        return any(unicodedata.category(c) == 'Mn' for c in unicodedata.normalize('NFKD', chr(cp)))

    def base(cp):  # one character per letter (𝒜 and 𝓐 are both A); symbols count as themselves
        ch = chr(cp)
        if unicodedata.category(ch).startswith('L'):
            return unicodedata.normalize('NFKD', ch)[0], 'CAPITAL' in unicodedata.name(ch, '')
        return ch, False
    order = sorted(groups, key=lambda k: ('bold' in k, all(plain(c) for c in groups[k]) or unicodedata.category(chr(groups[k][0])).startswith('P'),
                                          'italic' not in k and 'small' in k and 'Greek' in k,  # maths sets Greek small letters italic
                                          -len(groups[k]), 'small' in k, min(groups[k])))
    for k in order:
        groups[k].sort(key=lambda cp: (plain(cp), base(cp)[0] if unicodedata.category(chr(cp)).startswith('L') else '', cp))
    out, seen, i = [], set(), 0
    while len(out) < n and any(i < len(groups[k]) for k in order):
        for k in order:
            if i < len(groups[k]) and len(out) < n:
                cp = groups[k][i]
                if base(cp) in seen:
                    continue
                seen.add(base(cp))
                out.append(cp)
        i += 1
    return sorted(out, key=lambda cp: (order.index(kind_of(cp)), groups[kind_of(cp)].index(cp)))


def private(cp):
    return 0xE000 <= cp <= 0xF8FF or cp >= 0xF0000


def describe(cps):
    """What a feature without a name of its own changes, in words."""
    if not cps:
        return ''
    if len(cps) == 1:
        ch = chr(next(iter(cps)))
        m = re.match(r'^(LATIN|GREEK) (SMALL|CAPITAL) LETTER (.+)$', unicodedata.name(ch, ''))
        if m:
            rest = ch if m.group(1) == 'LATIN' and len(m.group(3)) == 1 else m.group(3).lower()
            return ('Greek ' if m.group(1) == 'GREEK' else '') + m.group(2).lower() + ' ' + rest
        return unicodedata.name(ch, '').lower()
    letters = [chr(cp) for cp in cps if unicodedata.category(chr(cp)).startswith('L')]
    bases = {unicodedata.normalize('NFKD', c)[0] for c in letters}
    if len(letters) == len(cps) and len(bases) == 1:
        return f'{bases.pop()} in {len(cps)} alphabets'
    count = {}
    for cp in cps:
        count[kind_of(cp)] = count.get(kind_of(cp), 0) + 1
    top = sorted(count, key=lambda k: ('bold' in k, -count[k], 'small' in k))
    stem = lambda k: re.sub(r' ?(capitals|small letters)$', '', k)
    if len(top) > 1 and top[1] != top[0] and stem(top[0]) == stem(top[1]) and stem(top[0]):
        return stem(top[0]) + ' letters'  # script capitals + script small letters
    if count[top[0]] == 1 and len(top) > 1:  # symbols that share no kind: name two
        return ' and '.join(top[:2]) + (' …' if len(top) > 2 else '')
    return top[0]


def analyse(font):
    from fontTools.ttLib import TTFont
    path = local_or_cached(font['math'], font['id'])
    f = TTFont(path, lazy=False)
    cmap = f.getBestCmap()
    rev = {}
    for cp, g in sorted(cmap.items()):
        rev.setdefault(g, cp)
    order = f.getGlyphOrder()
    gid = {g: i for i, g in enumerate(order)}
    info = dict(
        file=path.name, family=name_of(f, 1), version=name_of(f, 5), glyphs=len(order),
        upem=f['head'].unitsPerEm, copyright=name_of(f, 0), designer=name_of(f, 9), vendor=name_of(f, 8),
        licence_text=name_of(f, 13), licence_url=name_of(f, 14),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size,
    )
    lic = licence_label(info['licence_text'] + ' ' + info['licence_url'])
    info['licence_source'] = 'name IDs 13/14'
    if not lic and licence_label(info['copyright']):
        lic, info['licence_source'] = licence_label(info['copyright']), 'name ID 0 (copyright)'
    if not lic and font.get('licence'):
        lic, info['licence_source'] = font['licence'], font['licence_source']
    info['licence'] = lic
    info['alphabets'] = sum(1 for cp in cmap if 0x1D400 <= cp <= 0x1D7FF and unicodedata.name(chr(cp), ''))
    info['alphabets_total'] = ALPHABET_TOTAL
    # MATH table
    m = None
    if 'MATH' in f:
        t = f['MATH'].table
        v = t.MathVariants
        cons = {'vertical': v.VertGlyphConstruction or [], 'horizontal': v.HorizGlyphConstruction or []}
        variants = sum(sum(1 for r in c.MathGlyphVariantRecord if r.VariantGlyph != base)
                       for kind, cov in (('vertical', v.VertGlyphCoverage), ('horizontal', v.HorizGlyphCoverage)) if cov
                       for base, c in zip(cov.glyphs, cons[kind]))
        assemblies = sum(1 for c in cons['vertical'] + cons['horizontal'] if c.GlyphAssembly)
        gi = t.MathGlyphInfo
        c = t.MathConstants
        m = dict(
            vertical=len(cons['vertical']), horizontal=len(cons['horizontal']), size_variants=variants, assemblies=assemblies,
            italic_corrections=gi.MathItalicsCorrectionInfo.ItalicsCorrectionCount if gi and gi.MathItalicsCorrectionInfo else 0,
            accent_attachments=gi.MathTopAccentAttachment.TopAccentAttachmentCount if gi and gi.MathTopAccentAttachment else 0,
            kerns=gi.MathKernInfo.MathKernCount if gi and gi.MathKernInfo else 0,
            script_scale=[c.ScriptPercentScaleDown, c.ScriptScriptPercentScaleDown],
            display_operator_min_height=c.DisplayOperatorMinHeight,
        )
    info['math'] = m
    # GSUB features
    feats, sets, ssty = [], [], 0
    if 'GSUB' in f and f['GSUB'].table.FeatureList:
        gsub = f['GSUB'].table
        feats = sorted({fr.FeatureTag for fr in gsub.FeatureList.FeatureRecord})
        if 'ssty' in feats:
            ssty = len(feature_mapping(gsub, 'ssty')[0])
        for tag in feats:
            if not re.match(r'^(ss\d\d|cv\d\d|salt)$', tag):
                continue
            mapping, params, other = feature_mapping(gsub, tag)
            # characters of their own: private-use code points count as glyphs without one
            cps = {rev[g]: a for g, a in mapping.items() if g in rev and not private(rev[g])}
            label = ''
            if params is not None:
                nid = getattr(params, 'UINameID', None) or getattr(params, 'FeatUILabelNameID', None)
                if nid:
                    label = name_of(f, nid)
            shown = pick(cps)
            sets.append(dict(
                tag=tag, name=label, changes=len(cps), unencoded=len(mapping) - len(cps), contextual_subtables=other,
                kinds=describe(cps),
                shown=[dict(char=chr(cp), cp=f'U+{cp:04X}', glyph=cmap[cp], alt=cps[cp], gid=gid[cmap[cp]], alt_gid=gid[cps[cp]]) for cp in shown],
            ))
    info['gsub_features'] = feats
    info['ssty'] = ssty
    info['sets'] = sets
    f.close()
    return info


# ---------------------------------------------------------------------------
# render

def tex_path(p):
    return str(p.parent) + '/'


def compress_ranges(cps):
    out, run = [], None
    for cp in sorted(cps):
        if run and cp == run[1] + 1:
            run[1] = cp
        else:
            if run:
                out.append(run)
            run = [cp, cp]
    if run:
        out.append(run)
    return ','.join(f'"{a:X}' if a == b else f'"{a:X}-"{b:X}' for a, b in out)


def unshadowed(path, fid, role):
    """TeX Live ships NAME.fontspec files for some fonts (NewCM10-Book, KpMath-Regular …)
    that fontspec reads whenever a font of that name is loaded, and they name faces we
    did not fetch. A link under another name keeps fontspec to the file we give it."""
    r = subprocess.run(['kpsewhich', path.stem + '.fontspec'], capture_output=True, text=True).stdout.strip()
    if not r:
        return path
    link = WORK / fid / 'fonts' / f'mf-{fid}-{role}{path.suffix.lower()}'
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.is_symlink():
        link.symlink_to(path)
    return link


def font_files(font):
    return (unshadowed(local_or_cached(font['math'], font['id']), font['id'], 'math'),
            unshadowed(local_or_cached(font['text'], font['id']), font['id'], 'text'))


def tex_source(font, info, fallback):
    mpath, tpath = font_files(font)
    lm = CACHE / 'fonts' / 'latinmodern' / 'latinmodern-math.otf'
    opts = ','.join(x for x in (f'Path={tex_path(mpath)}', font.get('opts', '')) if x)
    lines = [
        r'\documentclass[multi=mfpage,border=8pt]{standalone}',
        r'\usepackage{xcolor}',
        r'\usepackage{unicode-math}',
        r'\tracinglostchars=1 \tracingonline=1',
    ]
    if font.get('unimath'):
        lines.append(r'\unimathsetup{%s}' % font['unimath'])
    lines.append(r'\setmainfont{%s}[Path=%s]' % (tpath.name, tex_path(tpath)))
    if font.get('nomath'):
        cps = [cp for cp in sorted(info['cmap']) if cp >= 0x20]
        lines.append(r'\setmathfont{%s}[Path=%s]' % (lm.name, tex_path(lm)))
        lines.append(r'\setmathfont{%s}[%s,range={%s}]' % (mpath.name, opts, compress_ranges(cps)))
    else:
        lines.append(r'\setmathfont{%s}[%s]' % (mpath.name, opts))
    if fallback:
        lines.append(r'\setmathfont{%s}[Path=%s,range={%s},Colour=8C8C8C]' % (lm.name, tex_path(lm), compress_ranges(fallback)))
    lines += [
        r'\font\strip={[%s]:mode=base} at %dpt' % (mpath, STRIP_PT),
        r'\directlua{dofile("mathfonts.lua")}',
        r'\newcommand\G[1]{\directlua{mfglyph(#1)}}',
        r'\newenvironment{mfpage}{}{}',
        r'\begin{document}',
        r'\begin{mfpage}\fontsize{%d}{%d}\selectfont' % (SAMPLE_PT, round(SAMPLE_PT * 1.3)),
        r'\begin{minipage}{%dpt}' % SAMPLE_WIDTH_PT,
        r'\setlength\abovedisplayskip{6pt}\setlength\belowdisplayskip{2pt}\setlength\abovedisplayshortskip{6pt}',
        r'\noindent ' + SAMPLE_TEXT,
    ]
    for i, eq in enumerate(SAMPLE_MATH):
        lines.append(r'\[ %s \]' % eq)
        if i == 0:
            lines.append(r'\vspace{-2pt}')
    lines += [r'\end{minipage}', r'\end{mfpage}']
    for s in info['sets']:
        if not s['shown']:
            continue
        cols = len(s['shown'])
        top = ' & '.join(r'\G{%d}' % x['gid'] for x in s['shown'])
        bot = ' & '.join(r'\G{%d}' % x['alt_gid'] for x in s['shown'])
        lines.append(r'\begin{mfpage}\strip\setlength\tabcolsep{3.5pt}\renewcommand\arraystretch{1.15}'
                     r'\begin{tabular}{@{}*{%d}{c}@{}}\color[HTML]{8C8C8C}%s\\ %s\end{tabular}\end{mfpage}'
                     % (cols, top.replace(' & ', r' & \color[HTML]{8C8C8C}'), bot))
    lines.append(r'\end{document}')
    return '\n'.join(lines) + '\n'


USE_SYSTEMD = shutil.which('systemd-run') is not None and os.environ.get('XDG_RUNTIME_DIR')


def run_capped(cmd, cwd, log, unit, mem='2000M'):
    env = {'TEXMFVAR': str(TEXMFVAR)}
    shell = f'{shlex.join(cmd)} > {shlex.quote(str(log))} 2>&1'
    if USE_SYSTEMD:
        full = ['systemd-run', '--user', f'--unit={unit}-{os.getpid()}', '--collect', '--wait', '-q',
                '-p', f'MemoryMax={mem}', '-p', 'MemorySwapMax=0', f'--working-directory={cwd}',
                '-E', f'PATH={os.environ["PATH"]}'] + [x for k, v in env.items() for x in ('-E', f'{k}={v}')] + ['sh', '-c', shell]
        return subprocess.run(full).returncode
    return subprocess.run(['sh', '-c', shell], cwd=cwd, env={**os.environ, **env}).returncode


GLYPH_LUA = r'''-- glyph by glyph index, whatever its slot in the loaded font
mfslots = {}
function mfglyph(gid)
  local fid = font.current()
  local map = mfslots[fid]
  if not map then
    map = {}
    for slot, c in pairs(fonts.hashes.identifiers[fid].characters) do
      if c.index and (not map[c.index] or slot < map[c.index]) then map[c.index] = slot end
    end
    mfslots[fid] = map
  end
  local s = map[gid]
  if s then tex.sprint("\\char" .. s .. " ") else texio.write_nl("mathfonts: no slot for glyph " .. gid) end
end
'''


def warm(path):
    """Let luaotfload cache one font file in a run of its own: a first load costs far
    more memory than later ones, and several at once would not fit in the cap."""
    otl = TEXMFVAR / 'luatex-cache' / 'generic' / 'fonts' / 'otl'
    if (otl / (re.sub(r'[^a-z0-9]+', '-', path.stem.lower()) + '.luc')).exists():
        return
    d = WORK / '_warm'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'warm.tex').write_text('\\documentclass{article}\\begin{document}\\font\\x={[%s]:mode=base} \\x x\\end{document}\n' % path)
    run_capped(['lualatex', '-interaction=nonstopmode', 'warm.tex'], d, d / 'warm.log', 'mathfonts-warm')


def lualatex(font, info, fallback):
    d = WORK / font['id']
    d.mkdir(parents=True, exist_ok=True)
    for p in font_files(font) + (CACHE / 'fonts' / 'latinmodern' / 'latinmodern-math.otf',):
        warm(p)
    (d / 'mathfonts.lua').write_text(GLYPH_LUA)
    (d / 'sample.tex').write_text(tex_source(font, info, fallback))
    for f in d.glob('sample.pdf'):
        f.unlink()
    rc = run_capped(['lualatex', '-interaction=nonstopmode', '-halt-on-error', 'sample.tex'], d, d / 'run.log', f'mathfonts-tex-{font["id"]}')
    log = (d / 'sample.log').read_text(errors='replace') if (d / 'sample.log').exists() else ''
    if rc != 0 or not (d / 'sample.pdf').exists():
        raise RuntimeError(f'LuaLaTeX failed for {font["id"]}, see {d}/run.log')
    return d / 'sample.pdf', log


def missing_chars(log):
    return sorted({int(h, 16) for h in re.findall(r'Missing character: There is no .*?\(U\+([0-9A-F]+)\)', log)})


def bboxes(pdf):
    out = subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-sDEVICE=bbox', str(pdf)],
                         capture_output=True, text=True).stderr
    return [tuple(map(float, b)) for b in re.findall(r'%%HiResBoundingBox: ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)', out)]


def page_size(pdf):
    out = subprocess.run(['pdfinfo', '-f', '1', '-l', '9999', str(pdf)], capture_output=True, text=True).stdout
    return [tuple(map(float, s)) for s in re.findall(r'Page\s+\d+ size:\s+([\d.]+) x ([\d.]+)', out)]


# --- SVG: pdftocairo output, rewritten small ----------------------------------

NUM = r'-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?'


PREC = 0   # path data in whole tenths of a point (UNIT): 0.05 pt at most off, under a tenth of a pixel
UNIT = 10  # drawing units per point; the SVG scales them back with one transform


def fmt(x, prec=None):
    p = PREC if prec is None else prec
    s = f'{x:.{p}f}'.rstrip('0').rstrip('.') if p else f'{x:.0f}'
    if s in ('-0', ''):
        s = '0'
    if s.startswith('0.'):
        s = s[1:]
    elif s.startswith('-0.'):
        s = '-' + s[2:]
    return s


def path_rel(d):
    """Absolute M/L/C/Q/Z path (pdftocairo) to rounded relative commands, as short as
    SVG allows: no separator before a minus sign or before a second decimal point."""
    toks = re.findall(r'[MLCQZmlcqz]|' + NUM, d)
    arity = {'M': 2, 'L': 2, 'C': 6, 'Q': 4}
    out, prev, last = [], '', None
    cx = cy = sx = sy = 0.0
    i, cmd = 0, None

    def emit(num):
        nonlocal prev
        if prev and not num.startswith('-') and not (num.startswith('.') and '.' in prev):
            out.append(' ')
        out.append(num)
        prev = num

    while i < len(toks):
        t = toks[i]
        if t in 'MLCQZmlcqz':
            cmd = t.upper()
            i += 1
            if cmd == 'Z':
                out.append('z')
                prev, last = '', 'z'
                cx, cy = sx, sy
                continue
        n = arity[cmd]
        vals = [round(float(v) * UNIT, PREC) for v in toks[i:i + n]]
        i += n
        letter = cmd.lower()
        if letter != last or letter == 'm':
            out.append(letter)
            prev = ''
        for k in range(0, n, 2):
            emit(fmt(vals[k] - cx))
            emit(fmt(vals[k + 1] - cy))
        cx, cy = vals[-2], vals[-1]
        if cmd == 'M':
            sx, sy = cx, cy
            last = 'l'  # pairs after a moveto are linetos
        else:
            last = letter
    return ''.join(out)


def colour(c):
    m = re.match(r'rgb\(([\d.]+)%,\s*([\d.]+)%,\s*([\d.]+)%\)', c.strip())
    if not m:
        return c
    v = [round(float(x) * 2.55) for x in m.groups()]
    h = '#%02x%02x%02x' % tuple(v)
    if h[1] == h[2] and h[3] == h[4] and h[5] == h[6]:
        h = '#' + h[1] + h[3] + h[5]
    return h


def svg_attr(el, key):
    v = el.get(key)
    if v is None:
        m = re.search(r'(?:^|;)\s*' + key + r'\s*:\s*([^;]+)', el.get('style', ''))
        v = m.group(1).strip() if m else None
    return v


def svg_small(svg_text, box, title):
    """pdftocairo's SVG rewritten small: glyph outlines once each, rounded relative
    path data, one group per colour, no page background; cropped to box
    (x0, y0, x1, y1 in SVG units)."""
    import xml.etree.ElementTree as ET
    S, X = '{http://www.w3.org/2000/svg}', '{http://www.w3.org/1999/xlink}'
    root = ET.fromstring(svg_text)
    x0, y0, x1, y1 = box
    glyphs = {}
    for defs in root.iter(S + 'defs'):
        for el in defs.iter():
            if el.get('id') and el.tag in (S + 'g', S + 'symbol'):
                ds = [p.get('d', '') for p in el.iter(S + 'path')]
                if any(d.strip() for d in ds):
                    glyphs[el.get('id')] = ' '.join(ds)
    body = []

    def walk(el, fill):
        tag = el.tag[len(S):] if el.tag.startswith(S) else el.tag
        if tag in ('defs', 'clipPath', 'symbol', 'rect', 'title'):
            return
        f = svg_attr(el, 'fill')
        if tag == 'use':
            ref = (el.get(X + 'href') or el.get('href') or '#')[1:]
            if ref in glyphs:
                body.append(dict(kind='use', ref=ref, x=float(el.get('x', 0)) - x0, y=float(el.get('y', 0)) - y0,
                                 colour=colour(f) if f and f != 'none' else fill))
            return
        if tag == 'path':
            d = el.get('d', '')
            st = svg_attr(el, 'stroke')
            if f == 'none' and st and st != 'none':
                body.append(dict(kind='stroke', d=d, tr=el.get('transform', ''), w=float(svg_attr(el, 'stroke-width') or 1),
                                 colour=colour(st)))
            elif d.strip():
                body.append(dict(kind='fill', d=d, tr=el.get('transform', ''), colour=colour(f) if f and f != 'none' else fill))
            return
        if f and f != 'none':
            fill = colour(f)
        for ch in el:
            walk(ch, fill)

    for ch in root:
        walk(ch, '#000')
    used = []
    for b in body:
        if b['kind'] == 'use' and b['ref'] not in used:
            used.append(b['ref'])
    short = {sid: f'g{i}' for i, sid in enumerate(used)}
    w, h = x1 - x0, y1 - y0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{fmt(w, 1)}pt" height="{fmt(h, 1)}pt" viewBox="0 0 {fmt(w, 1)} {fmt(h, 1)}">',
           f'<title>{html.escape(title)}</title>']
    if used:
        out.append('<defs>' + ''.join(f'<path id="{short[sid]}" d="{path_rel(glyphs[sid])}"/>' for sid in used) + '</defs>')
    out.append(f'<g transform="scale({fmt(1 / UNIT, 3)})">')
    groups = {}
    for b in body:
        groups.setdefault((b['kind'] == 'stroke', b['colour']), []).append(b)
    for (stroked, col), items in groups.items():
        if stroked:
            for b in items:
                d2, scale = apply_matrix(b['d'], parse_matrix(b['tr']), x0, y0)
                out.append(f'<path d="{path_rel(d2)}" fill="none" stroke="{col}" stroke-width="{fmt(b["w"] * scale * UNIT)}"/>')
            continue
        out.append(f'<g fill="{col}">' if col != '#000' else '<g>')
        for b in items:
            if b['kind'] == 'use':
                out.append(f'<use xlink:href="#{short[b["ref"]]}" x="{fmt(b["x"] * UNIT)}" y="{fmt(b["y"] * UNIT)}"/>')
            else:
                d2, _ = apply_matrix(b['d'], parse_matrix(b['tr']), x0, y0)
                out.append(f'<path d="{path_rel(d2)}"/>')
        out.append('</g>')
    out.append('</g></svg>')
    return ''.join(out)


def parse_matrix(tr):
    m = re.search(r'matrix\(([^)]*)\)', tr or '')
    if not m:
        return (1, 0, 0, 1, 0, 0)
    return tuple(float(v) for v in re.split(r'[ ,]+', m.group(1).strip()))


def apply_matrix(d, mat, x0, y0):
    a, b, c, dd, e, f = mat
    toks = re.findall(r'[MLCQZ]|' + NUM, d)
    out, pair = [], []
    for t in toks:
        if t in 'MLCQZ':
            out.append(t)
            continue
        pair.append(float(t))
        if len(pair) == 2:
            x, y = pair
            out += [str(a * x + c * y + e - x0), str(b * x + dd * y + f - y0)]
            pair = []
    return ' '.join(out), (abs(a) + abs(dd)) / 2 or 1


def pdf_page_svg(pdf, page, box_pt, size_pt, pad, title, dest):
    """One PDF page as a small SVG, cropped to box_pt (PDF coordinates) plus pad."""
    tmp = dest.with_suffix('.raw.svg')
    subprocess.run(['pdftocairo', '-svg', '-f', str(page), '-l', str(page), str(pdf), str(tmp)], check=True)
    raw = tmp.read_text()
    tmp.unlink()
    ph = size_pt[1]
    bx0, by0, bx1, by1 = box_pt
    box = (bx0 - pad[0], ph - by1 - pad[1], bx1 + pad[0], ph - by0 + pad[1])
    dest.write_text(svg_small(raw, box, title))
    return box[2] - box[0], box[3] - box[1]


def render(font, info):
    miss = []
    if not font.get('nomath'):
        style = 'upright' if 'math-style=upright' in font.get('unimath', '') else 'TeX'
        miss = sorted(cp for cp in SAMPLE_CODEPOINTS[style] if cp not in info['cmap'])
        if miss:
            print(f'  {font["id"]}: not in the cmap, set in Latin Modern Math: {"".join(map(chr, miss))}', flush=True)
    pdf, log = lualatex(font, info, miss)
    late = [cp for cp in missing_chars(log) if cp not in miss]
    if late and not font.get('nomath'):
        print(f'  {font["id"]}: LuaTeX also missed {"".join(map(chr, late))}', flush=True)
        miss = sorted(miss + late)
        pdf, log = lualatex(font, info, miss)
    info['missing'] = [dict(char=chr(cp), cp=f'U+{cp:04X}') for cp in miss]
    to_svg(font, info, pdf)


def to_svg(font, info, pdf):
    for old in OUT.glob(f'{font["id"]}-*.svg'):
        old.unlink()
    boxes = bboxes(pdf)
    sizes = page_size(pdf)
    border = 8
    # sample: keep the minipage's width (every font at the same scale), crop height to ink
    bx = boxes[0]
    w, h = pdf_page_svg(pdf, 1, (border, bx[1], sizes[0][0] - border, bx[3]), sizes[0], (2, 2.5),
                        f'{font["name"]}: sample', OUT / f'{font["id"]}.svg')
    info['image'] = dict(file=f'images/mathfonts/{font["id"]}.svg', w=round(w * 4 / 3), h=round(h * 4 / 3))
    page = 2
    for s in info['sets']:
        if not s['shown']:
            continue
        name = f'{font["id"]}-{s["tag"]}.svg'
        w, h = pdf_page_svg(pdf, page, boxes[page - 1], sizes[page - 1], (2, 2),
                            f'{font["name"]} {s["tag"]}: default above, alternate below', OUT / name)
        s['image'] = dict(file=f'images/mathfonts/{name}', w=round(w), h=round(h))  # 1 px per pt: 20 px glyphs
        page += 1


# ---------------------------------------------------------------------------
# page

def esc(s):
    return html.escape(s, quote=True)


def num(n):
    return f'{n:,}'.replace(',', ' ')


def features_line(font, info):
    bits = []
    bits.append(f'{num(info["glyphs"])} glyphs')
    m = info['math']
    if m:
        bits.append(f'{num(m["size_variants"])} size variants and {num(m["assemblies"])} assemblies for '
                    f'{num(m["vertical"])} vertical and {num(m["horizontal"])} horizontal stretchy glyphs')
        if m['kerns']:
            bits.append(f'cut-ins for {num(m["kerns"])} glyphs')
    else:
        bits.append('no MATH table')
    bits.append(f'script forms (ssty) for {num(info["ssty"])} glyphs' if info['ssty'] else 'no script forms (ssty)')
    bits.append(f'maths alphabets {num(info["alphabets"])} of {num(info["alphabets_total"])}')
    if font['bold']:
        bits.append('bold maths: ' + ', '.join(font['bold']))
    else:
        bits.append('no bold maths font')
    names = {'dtls': 'dotless i and j under accents (dtls)', 'flac': 'flatter accents over capitals (flac)',
             'rtlm': 'mirrored forms for right-to-left maths (rtlm)'}
    bits += [names[t] for t in info['gsub_features'] if t in names]
    hidden = [s['tag'] for s in info['sets'] if not s['changes'] and s['unencoded']]
    if hidden:
        bits.append(', '.join(hidden) + (' changes' if len(hidden) == 1 else ' change') + ' only glyphs without a character of their own')
    return bits


def panel(font, info):
    sets = [s for s in info['sets'] if s.get('image')]
    first = font['id'] == 'anodyne'
    src = font['math']
    origin = ('this repository' if not re.match('https?://', src) else 'CTAN' if src.startswith(CTAN)
              else 'GitHub' if 'github' in src else 'Arkandis' if 'arkandis' in src else re.sub(r'^https?://([^/]+)/.*$', r'\1', src))
    lic = info['licence'] or 'see the font'
    out = [f'<article class="panel mf-font{" mf-ours" if first else ""}" id="mf-{font["id"]}">',
           f'<div class="mf-head"><h3>{esc(font["name"])}</h3><span class="mf-lic">{esc(lic)}</span></div>',
           f'<img class="mf-sample" src="{info["image"]["file"]}" width="{info["image"]["w"]}" height="{info["image"]["h"]}" loading="lazy" '
           f'alt="{esc(font["name"])}{"" if font["text_name"] == font["name"] else " with " + esc(font["text_name"])}: the sample sentence, a sum over a fraction with a root against an integral of a partial derivative in bars, '
           f'and a product in brackets beside script, fraktur and double-struck letters">']
    notes = []
    if font.get('note'):
        notes.append(esc(font['note']))
    if info.get('missing'):
        chars = ' '.join(x['char'] for x in info['missing'])
        notes.append(f'Not in the font, so set in grey from Latin Modern Math: {esc(chars)}.')
    text = ' '.join([f'Text in {esc(font["text_name"])}.'] + notes)
    out.append(f'<p class="mf-note">{text}</p>')
    out.append('<ul class="mf-facts">' + ''.join(f'<li>{esc(b)}</li>' for b in features_line(font, info)) + '</ul>')
    if sets:
        out.append('<div class="mf-sets">')
        for s in sets:
            label = s['name'] or s['kinds']
            chars = ''.join(x['char'] for x in s['shown'])
            out.append(f'<figure><img src="{s["image"]["file"]}" width="{s["image"]["w"]}" height="{s["image"]["h"]}" loading="lazy" '
                       f'alt="{esc(s["tag"])} changes {s["changes"]} character{"" if s["changes"] == 1 else "s"}; shown: {esc(chars)}, default above, alternate below">'
                       f'<figcaption><code>{s["tag"]}</code> {esc(label)}</figcaption></figure>')
        out.append('</div>')
    elif info['sets']:
        out.append('<p class="mf-note">Its stylistic sets change only glyphs without a character of their own.</p>')
    src_links = f'<a href="{esc(font["home"])}">{esc(font["home"].split("//")[1].rstrip("/"))}</a>'
    which = {A1: 'the main answer', A2: 'the answer on newer fonts'}
    ans = f' · listed in <a href="{SE}{font["answer"]}">{which[font["answer"]]}</a>' if font.get('answer') else ''
    version = re.sub(r'^Version\s*', '', info['version'].split(';')[0]).strip()
    out.append(f'<p class="mf-src">Version {esc(version)} from {esc(origin)} · {src_links}{ans}</p>')
    out.append('</article>')
    return '\n'.join(out)


def section(fonts, infos):
    by = {f['id']: f for f in fonts}
    sans = [f for f in fonts if f['group'] == 'sans' and f['id'] != 'anodyne']
    serif = [f for f in fonts if f['group'] == 'serif']
    n = len(fonts)
    parts = ['<!-- mathfonts:start (written by sources/mathfonts/build.py) -->',
             '<section class="mf" aria-labelledby="mathfonts">',
             '<h2 id="mathfonts">Next to the other OpenType maths fonts</h2>',
             f'<p>The same sentence and formulas in Anodyne and in the {n - 1} other free fonts listed under '
             '<a href="https://tex.stackexchange.com/questions/425098">“Which OpenType math fonts are available?”</a>, '
             f'each with its text companion, set by LuaLaTeX with unicode-math at {SAMPLE_PT} pt and drawn as outlines. '
             'The facts come from the font files: stretchy glyphs from the MATH table, script forms from the ssty feature, '
             'maths alphabets out of the Unicode block. Under each font, every stylistic set and character variant that '
             'changes characters, with the usual glyphs in grey above and the alternates below.</p>',
             '<p class="mf-jump">' + ' '.join(f'<a href="#mf-{f["id"]}">{esc(f["name"])}</a>' for f in fonts) + '</p>']
    parts.append('<h3 class="mf-group">Sans-serif</h3><div class="mf-grid">')
    parts += [panel(f, infos[f['id']]) for f in [by['anodyne']] + sans]
    parts.append('</div><h3 class="mf-group">Serif</h3><div class="mf-grid">')
    parts += [panel(f, infos[f['id']]) for f in serif]
    parts.append('</div>')
    rows = ''.join(f'<li><strong>{esc(x["name"])}</strong>: {esc(x["licence"])}.</li>' for x in NOT_SHOWN)
    parts.append('<div class="panel mf-absent"><span class="label">Not shown</span>'
                 '<p>These fonts from the same answers are not free to obtain and use, so this page leaves them out:</p>'
                 f'<ul>{rows}</ul></div>')
    parts.append('</section>')
    parts.append('<!-- mathfonts:end -->')
    return '\n'.join(parts)


def write_page(fonts, infos):
    s = INDEX.read_text()
    a, b = '<!-- mathfonts:start', '<!-- mathfonts:end -->'
    if a not in s or b not in s:
        raise SystemExit('index.html has no <!-- mathfonts:start --> … <!-- mathfonts:end --> markers')
    i, j = s.index(a), s.index(b) + len(b)
    INDEX.write_text(s[:i] + section(fonts, infos) + s[j:])


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('steps', nargs='*', default=['fetch', 'analyse', 'render', 'page'])
    ap.add_argument('--only', help='comma-separated font ids')
    ap.add_argument('--no-systemd', action='store_true')
    args = ap.parse_args()
    global USE_SYSTEMD
    if args.no_systemd:
        USE_SYSTEMD = False
    only = set(args.only.split(',')) if args.only else None
    fonts = [f for f in FONTS if not only or f['id'] in only]
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    TEXMFVAR.mkdir(parents=True, exist_ok=True)
    # Latin Modern Math fills in characters a font lacks
    lm = next(f for f in FONTS if f['id'] == 'latinmodern')
    state = CACHE / 'state.json'
    infos = json.loads(state.read_text()) if state.exists() else {}
    if 'fetch' in args.steps:
        for f in [lm] + fonts:
            fetch(f)
    if 'analyse' in args.steps:
        for f in fonts:
            print(f'analyse {f["id"]}', flush=True)
            info = analyse(f)
            old = infos.get(f['id'], {})
            for k in ('image', 'missing'):
                if k in old:
                    info[k] = old[k]
            infos[f['id']] = info
            state.write_text(json.dumps(infos, ensure_ascii=False, indent=1))
    failed = []
    if 'render' in args.steps:
        from fontTools.ttLib import TTFont
        for f in fonts:
            print(f'render {f["id"]}', flush=True)
            info = infos[f['id']]
            t = TTFont(local_or_cached(f['math'], f['id']), lazy=True)
            info['cmap'] = set(t.getBestCmap())
            t.close()
            for old in OUT.glob(f'{f["id"]}-*.svg'):
                old.unlink()
            try:
                render(f, info)
            except Exception as e:  # keep going; the page leaves out fonts without an image
                print(f'  FAILED {f["id"]}: {e}', flush=True)
                info.pop('image', None)
                failed.append(f['id'])
            info.pop('cmap', None)
            state.write_text(json.dumps(infos, ensure_ascii=False, indent=1))
    if 'svg' in args.steps:  # convert the PDFs of the last render again
        for f in fonts:
            pdf = WORK / f['id'] / 'sample.pdf'
            if pdf.exists() and infos.get(f['id'], {}).get('image'):
                print(f'svg {f["id"]}', flush=True)
                to_svg(f, infos[f['id']], pdf)
        state.write_text(json.dumps(infos, ensure_ascii=False, indent=1))
    if 'page' in args.steps:
        allf = [f for f in FONTS if f['id'] in infos and infos[f['id']].get('image')]
        data = dict(
            source='https://tex.stackexchange.com/questions/425098',
            generator='sources/mathfonts/build.py',
            sample=dict(text=SAMPLE_TEXT, math=SAMPLE_MATH, size_pt=SAMPLE_PT, width_pt=SAMPLE_WIDTH_PT),
            fonts=[dict(id=f['id'], name=f['name'], group=f['group'], text_font=f['text_name'],
                        math_url=f['math'] if re.match('https?://', f['math']) else f['math'],
                        text_url=f['text'], home=f['home'], answer=(SE + f['answer']) if f.get('answer') else None,
                        bold_maths=f['bold'], note=f.get('note', ''), setup=dict(opts=f.get('opts', ''), unimath=f.get('unimath', '')),
                        **infos[f['id']]) for f in allf],
            not_shown=[dict(x, answer=SE + x['answer']) for x in NOT_SHOWN],
        )
        for f in data['fonts']:
            f['sets'] = [dict({k: v for k, v in x.items() if k != 'shown'},
                              shown=[[y['char'], y['glyph'], y['alt']] for y in x['shown']]) for x in f['sets']]
        # one font per line: small, and still readable in a diff
        head = json.dumps({k: v for k, v in data.items() if k not in ('fonts', 'not_shown')}, ensure_ascii=False)[:-1]
        rows = lambda xs: ',\n'.join('  ' + json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in xs)
        JSON_OUT.write_text(f'{head},\n"fonts": [\n{rows(data["fonts"])}\n],\n"not_shown": [\n{rows(data["not_shown"])}\n]}}\n')
        write_page(allf, infos)
    if failed:
        raise SystemExit('failed: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
