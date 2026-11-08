# Building and editing Anodyne

The canonical build lives in this repository. OverLyX should consume a built
release, rather than maintain another copy of the generator.

```sh
make build                       # staged files in build/dist/, no publication
make check FONTS=build/dist/fonts # regression checks and OpenType Sanitizer
make release                     # copy the staged distribution into fonts/
make sources                     # build/dist/Anodyne-sources.zip
```

Python 3.12 with `venv`, a C/C++ toolchain for optional QA dependencies, and
`ots-sanitize` are needed. On Ubuntu the packages are `python3.12-venv`,
`build-essential` and `opentype-sanitizer`. The normal build dependencies are
pinned in `requirements.lock`; `make setup` installs them in `build/venv`.
The optional `make qa` target installs the separately pinned FontBakery tools.
Its selected universal checks run against static and variable installation
cohorts separately, with raw reports and exact inherited exceptions retained.
The reports and summary go under `build/fontbakery/`; `qa-policy.json` documents
the selected release checks. Run `python sources/qa.py --full` for every universal
outline/interpolation diagnostic. Exact exceptions retain their original FAIL
messages and evidence in the report; unknown failures remain blocking.
See [QA-NOTES.md](QA-NOTES.md) for the interpretation of inherited warnings and
mathematical font design choices.

`source-lock.json` pins every upstream font and license to an immutable commit
and SHA-256. `fetch-sources.sh` works from any directory and refuses to use an
altered cached input. `SOURCE_DATE_EPOCH`, defaulting to the value in that lock,
fixes font and source archive timestamps. Font builds run with
`PYTHONHASHSEED=0`; the distribution includes `build-info.json` with source,
dependency and output checksums.

## Editable source preparation

The first `make build` runs `make prepare`: it imports the pinned upstream
drawings, adds the Anodyne features and constructs point-compatible masters.
The generated designspaces and standard UFOZ master sources live in
`build/masters/Roman/` and `build/masters/Italic/`. Subsequent builds compile
those sources; they do not repeat contour matching. The first compile needs
about 8 GB of available memory and compiles one style at a time. Complete styles
are cached by source, override, compiler and dependency hashes for later builds.

Each style also has a verified final-TTF cache in `build/compiled/`. Its key
covers the actual designspace/master contents, style overrides, compiler
modules, dependency versions and build options. Cache hits verify the output
checksum too. Editing any input or corrupting an output invalidates that style;
the named static faces and web subsets are regenerated from the verified TTFs.
For direct Python use, `pipeline.compile_style(masters_root, flat_output,
italic=False)` compiles one style without requiring the other style to exist.
Start Python with `PYTHONHASHSEED=0`, as the Make targets do, for reusable
deterministic cache keys across processes.

```sh
make edit     # unpack UFOZ masters to directory UFOs and update the designspaces
make build    # consumes the edited directory UFOs
```

Each source has quadratic contours, components, Unicode assignments, widths and
glyph order in ordinary UFO data. `ufo2ft`, the compiler used by fontmake,
compiles those outlines without contour optimization or implied-point removal.
Keep master contours and component structures compatible when editing. Layout
and math tables remain editable XML in each UFO's
`data/com.overlyx.anodyne/tables.ttx`; rebuilding preserves these tables and
constructs their variation data. This avoids losing mathematical layout or
complex shaping in a lossy TTF-to-feature-file conversion.

`make sources` packages the prepared master sources, designspaces, generators,
overrides and licenses. Generated full masters are build/release artifacts;
intentional drawing changes belong in tracked partial UFOs under
`sources/overrides/{Roman,Italic}/{master-name}.ufo`. A partial UFO replaces only
the glyphs it contains during compilation. Record the reason, location and
review status in `sources/overrides/manifest.json`.

`master-plan.json` documents the source contract and its limits. Generated
Thin/Black/condensed drawings for Lisnoti additions are compatible starting
points. Exporting them as UFO does not make them independently drawn or
optically reviewed. Noto's native editable source revision is also recorded in
the source lock for drawing work. `make prepare` reuses current preparation;
explicit refresh with `pipeline.py prepare --force` refuses to overwrite
unpacked edits.

`mathletters.py` handles mathematical letterlikes whose imported weight anchors
have identical ink, including the historical symbols outside U+1D400–1D7FF.
It preserves Regular and existing varying optical drawings. Compatible local
stroke changes are calibrated against varying script, fraktur and double-struck
peers, with clearance limits for counters and joins. Responsive ordinary-letter
width references also prevent static upstream letterlike glyphs from bypassing
condensation. Greek bodies and their accented composites are regenerated from
the repaired integer donors. These derived masters remain editable starting
points; the migration ledger records their actual source and validation hashes.

Compatible source migrations retain their original `preparation.json` inputs.
The `source_migrations` ledger records the previous and current source hashes,
generator hashes, validation results and copied evidence. A migration is
accepted only after the preserved originals and the complete candidate
designspaces have been checked. It is not recorded as a fresh upstream import.
The image generators retain separate proof provenance: `images/math-source.json`,
`images/greek-math-styles.json` and the specimen JSON sidecars identify the actual
font hashes used for rendering. `make specimen FONTS=build/dist/fonts` reproduces
the text, mathematical and Greek specimens with the documented rendering tools.

## Text, math and arbitrary instances

The staged distribution contains the complete variable TTFs, four named static
math faces, the text-only Unicode-range WOFF2 subsets, and full variable
`mathwebfonts/` WOFF2s retaining MATH and variation stores for MathML. The full
math webfonts intentionally cost more bandwidth than the text subsets.
Small adapter fonts in the same directory expose upright integrals, chancery
capitals and the seven named Greek alphabet features to native MathML. The Greek
adapters keep Greek Unicode characters and mathematical accent data; Latin and
other symbols fall back to the full `Anodyne Math` family. For example,
`\mathcal{\alpha\Gamma}`, `\mathfrak{\alpha\Gamma}`,
`\mathbb{\alpha\Gamma}` and `\mathtt{\alpha\Gamma}` select the corresponding
Greek drawings in the demo's converter. `\boldsymbol{\mathcal{...}}` and
`\mathbffrak{...}` select bold script and bold fraktur. With the chancery switch
enabled, regular Greek script uses its chancery alternate. These alphabets are
OpenType alternatives, since Unicode has no script or fraktur Greek blocks.
The browser normalizes canonically equivalent Greek accents and uses
`mathvariant="normal"` with the selected adapter family to retain that notation.
Combining marks without a precomposed form remain in the same Greek adapter
font. Native Greek mark classes are calibrated to each mathematical drawing's
bounds; missing source classes use case-matched alpha anchors and the explicit
symbol donors documented in `greek_positioning.py`. Existing native anchors
are retained, and new anchors vary with the actual source masters. Above marks
on mathematical and styled Greek align horizontally to each master's authored
MATH top-accent attachment, including narrow iota and shared Latin/Greek forms.

```sh
make instance AXES='--weight 550 --width 75 --grade 50'
make instance AXES='--weight 700 --width 62.5 --grade -25 --italic'
```

Instances are genuine static TTFs with unique coordinate-based family and
PostScript names. The fontTools instancer folds variable positioning and MATH
values, then `refresh_math_metrics` updates geometry-dependent construction
measurements. Use these files for TeX engines that cannot consume variable
MATH data directly. The input can be a variable TTF or WOFF2 via `--source`.

Final metadata separates raster clipping from text line height. The Windows
clipping rectangle covers the mathematical outlines; hhea and OS/2 typographic
line metrics retain the text line height, with `USE_TYPO_METRICS` enabled as the
[OpenType specification recommends](https://learn.microsoft.com/en-us/typography/opentype/spec/os2#os2-table-and-opentype-font-variations).
Text-only subsets recompute their own variation envelopes. Legacy applications
that use Windows clipping bounds for line spacing can still show loose lines
with a complete math font; explicit document/CSS line spacing or text subsets
are appropriate there. This is not a reason to clip large delimiters.

For a custom environment, set `PYTHON=path/to/venv/bin/python` in Make commands,
`MASTERS=path/to/masters` for another source directory, or pass `--masters` and
`--dist` directly to `sources/pipeline.py`.
