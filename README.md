# Anodyne

<picture><source media="(prefers-color-scheme: dark)" srcset="images/specimen-dark.png"><img alt="Anodyne at weights 100 to 900, widths 87.5 to 62.5, grades −100, 0 and 150, with small capitals, old-style figures, italics and maths alphabets" src="images/specimen.png"></picture>

**[Try it in your browser](https://japhba.github.io/anodyne/)**: weight, width, grade and features on your own text (`index.html`).

**Anodyne** is the sans-serif of [OverLyX](https://overlyx.app), a collaborative LaTeX editor: its
interface font, an editor and slide font, and a font documents can be typeset in, formulas
included. It is a fork of [Lisnoti](https://github.com/Lisnoti/Lisnoti) by Tim Gordon, which is
[Noto Sans](https://fonts.google.com/noto) with the characters that get confused in maths, science
and code redrawn (I l 1, O 0, operators on one maths axis, brackets, α), an OpenType `MATH` table
from Khaled Hosny's redesign of Noto Sans Math, and many more symbols. All of that is Lisnoti's
work; Anodyne adds:

- **Weight, 100 to 900** (`wght`). Lisnoti comes in Regular and Bold. Anodyne is a variable font:
  glyphs Lisnoti kept from Noto Sans use Noto Sans's own masters (Thin, Bold, Black, and Noto's
  weight mapping), so every weight between is Noto's design; glyphs Lisnoti redrew or added use
  Lisnoti Bold, made point-compatible with the Regular, with Thin and Black extrapolated at Noto's
  stem ratios. About 5 % of glyphs (rare symbols whose Bold has other contours) are emboldened
  point by point instead.
- **Width, 62.5 to 100** (`wdth`). Glyphs Lisnoti kept from Noto Sans use Noto Sans's own condensed
  designs at every weight; Lisnoti's redrawn and added glyphs (l, 0, brackets, operators, maths
  alphabets) have no condensed drawing anywhere, so they are squeezed to Noto's width at each weight
  and their stems brought back to Noto's condensed stems.
- **Grade, −100 to 150** (`GRAD`). Grade gives the stems of a lighter or heavier weight at the widths
  of the current one, so text darkens or lightens without reflowing: for light text on dark
  backgrounds (OverLyX takes 25 off in its dark theme), for screens and projectors that wash text
  out, for emphasis that must not move a line. Grade 100 is roughly the stem of weight 500 at the
  widths of 400.
- **The features Lisnoti dropped** while keeping their glyphs: small capitals (`smcp`, `c2sc`), so
  `\textsc` and small-caps headings have real ones; old-style, proportional, tabular and lining
  figures (`onum`, `pnum`, `tnum`, `lnum`; the zero stays slashed); case forms (`case`, not for figures
  and the maths-axis brackets); the Greek alternates (`ss06`, `ss07`); and Noto Sans Math's dotless
  i and j for accents (`dtls`).
- **Formulas set as Computer Modern sets them** (0.3). Noto Sans Math's `MATH` table, which Lisnoti
  uses, sets formulas tighter than beamer's default does with Computer Modern's symbols: subscripts on
  brackets and operators hardly drop, limits sit at half TeX's gap, a root's index is jammed against
  the sign, brackets keep the same thin margin at every size, and its tall braces are the brace
  stretched upright, hooks and beak drawn out until they look like brackets. Anodyne takes TeX's
  constants (Latin Modern Math's, the vertical ones scaled to Anodyne's x-height), and draws every size
  of `( ) [ ] { } ⌈ ⌉ ⌊ ⌋ ⟨ ⟩` again from its own text-size glyph the way Computer Modern's sizes grow:
  parentheses and angle brackets bow out almost in proportion to their height, a brace's hooks and
  beak grow with the square root of its height while only its arms lengthen, brackets' arms lengthen
  a little, and every stroke keeps its weight. Their margins grow on the outside only, as Computer
  Modern's do, and the extensible pieces are cut from the largest size (the closing brace gets its own
  extender). Only TeX's numbers are used: Computer Modern's outlines are under other licences.

It keeps Lisnoti's `ss01` (chancery script capitals for `\mathcal`), fractions, super- and
subscripts, and Unicode's maths alphanumerics.

<img alt="Formulas set by LuaLaTeX in Anodyne's MATH table" src="images/math.png">

## Files

| Folder | What |
|:--|:--|
| `fonts/variable/` | `Anodyne[GRAD,wdth,wght].ttf` and `Anodyne-Italic[GRAD,wdth,wght].ttf`: every weight, width and grade |
| `fonts/static/` | Regular, Bold, Italic and Bold Italic at normal width and grade 0, each with the `MATH` table: for desktop apps and LuaLaTeX |
| `fonts/webfonts/` | the variable fonts as woff2 by Unicode range (Latin, Latin extended, Greek, Cyrillic, symbols, maths, maths alphabets) and `anodyne.css` |
| `sources/` | the build: `build.py` (with `delimgen.py`, the delimiters, and `mathtune.py`, the maths spacing) and `fetch-sources.sh` |

## Use it

**On the web**, copy `fonts/webfonts/` to your site and link its stylesheet. A page fetches only the
ranges its text uses (about 195 kB for Latin, every weight, width and grade).

```html
<link rel="stylesheet" href="/webfonts/anodyne.css">
```
```css
body { font-family: Anodyne, sans-serif; }
@media (prefers-color-scheme: dark) { body { font-variation-settings: "GRAD" -25; } }
```

Any weight from 100 to 900 works with `font-weight`, any width from 62.5 % to 100 % with `font-stretch`;
grade with `font-variation-settings: "GRAD" <n>`.

**On a computer**, install the four files in `fonts/static/` (or the two variable ones, if your
apps handle variable fonts).

**In LaTeX** (LuaLaTeX or XeLaTeX), with the static files installed or next to the document:

```latex
\usepackage{unicode-math}
\setmainfont{Anodyne}
\setsansfont{Anodyne}
\setmathfont{Anodyne}
\setmathfont{Anodyne Bold}[version=bold]
\setmathfont{Anodyne}[range=\mathcal, StylisticSet=1]
```

As with Lisnoti: load `amsmath` before these lines, and keep the `\mathcal` line after the bold one.
LuaLaTeX also sets the variable font by axis, for any weight, width and grade, e.g.
`\fontspec{Anodyne}[RawFeature={axis={wght=550,wdth=75,GRAD=50}}]` with the variable file installed
under its own name. Anodyne is a large font for LuaTeX: caching each face the first time takes about
0.8 GB, so a first run that loads all of them at once needs a few GB.

## How it is built

`sources/build.py` (Python with fontTools and brotli; about 15 minutes and 3 GB per style) reads Lisnoti 2.006 and
Google's variable Noto Sans and writes the variable fonts, the statics and the license. Regular and
Bold of Lisnoti's own glyphs come from separately converted TrueType files, so their points rarely
correspond; the build matches each glyph's contours, aligns their on-curve points along each
contour, inserts the points one master has and the other lacks at the same arc-length fraction,
refits each run as a cubic and converts both with cu2qu's multi-master conversion, as fontmake does,
then checks that the half-way outline lies between the masters. Grade masters are the weight
masters with the advance growth spread back across each glyph by its points' positions, so stems
change and widths do not.

```sh
sh sources/fetch-sources.sh            # Lisnoti and Noto Sans into ./src
python3 sources/build.py --lisnoti src/lisnoti/font-Lisnoti/Lisnoti-ttf --noto src/noto --out build --only roman
python3 sources/build.py --lisnoti src/lisnoti/font-Lisnoti/Lisnoti-ttf --noto src/noto --out build --only italic
```

The build is maintained in the OverLyX repository (`scripts/anodyne/build.py`); its `--repo` option
writes the web and TeX files OverLyX serves.

## Licence

SIL Open Font License 1.1 ([OFL.txt](OFL.txt)), with the copyright notices of Noto Sans, Noto Sans
Symbols, Noto Sans Math, Lisnoti and Anodyne. "Lisnoti" is a Reserved Font Name of Lisnoti, which is
why this changed version has a name of its own. Anodyne reserves no name.

Version 0.300, built from Lisnoti 2.006 (commit `6642e5b`, 3 Nov 2026), Noto Sans 2.015 and Noto Sans Math 3.000.
