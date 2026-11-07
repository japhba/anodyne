# Release QA interpretation

`check.py` checks every shipped binary, actual grade advances and representative
outlines, mathematical constructions and variable MATH values, and sanitizes
each file. `qa.py` runs the selected FontBakery release checks on static and
variable installation sets separately. Raw diagnostics remain available in the
JSON/log files, including the two narrowly scoped inherited exceptions in
`qa-policy.json`. These exceptions do not establish complete Unicode coverage.

The following FontBakery warnings need interpretation for this font; they are
retained as warnings and are not erased or converted into blanket passes:

- **`math_signs_width`** assumes mathematical signs share a common advance.
  Anodyne inherits proportionally drawn relation, membership, geometric and
  other symbols from Lisnoti/Noto Math. Their ink is aligned to the mathematical
  axis, but a proportional sign or a wide geometric symbol need not have the
  same advance as `+`. Mathematical layout supplies additional spacing by atom
  class. This is separate from grade's strict fixed-advance requirement.
- **`opentype/STAT/ital_axis`** asks Roman entries to link to an italic value.
  The complete variable faces have that link. A named static face has a
  single-location STAT table; the four static styles retain ordinary family,
  subfamily, `fsSelection` and `macStyle` links. The check's missing-STAT-link
  warning for a Roman static is visible without implying a missing static style.
- **`stylisticset_description`** identifies inherited `ss01`, `ss06` and `ss07`
  features without desktop UI labels. Their existing mappings are retained.
  The six new feature choices have explicit labels. Browser controls and the
  README describe both old and new features.
- **GDEF classification warnings** identify inherited combining characters or
  unencoded shaping glyphs that deserve further text-shaping review. They are
  not a claim of complete mark positioning in every supported Unicode block.
  Representative text-mark shaping and mathematical accent attachment are
  checked separately; a regression in those functional checks remains blocking.
- **`opentype/points_out_of_bounds`** can report fractional coordinates in a
  scaled composite such as `periodcentered`, compared with integer glyph bounds.
  Preserve the compatible composite construction; this warning does not justify
  inserting incompatible points into one master. Final Windows clipping metrics
  use a safe variation envelope, and formula/outline proofs inspect rendering.

The selected release profile intentionally does not run every expensive
whole-font contour/interpolation heuristic. `qa.py --full` does so and keeps its
raw report. The selected checks, source compatibility gate, runtime checks and
visual proofs do not replace independent optical review of every glyph.
