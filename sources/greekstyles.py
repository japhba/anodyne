"""Anodyne interpretations of Greek mathematical alphabets.

Unicode has no Greek script, fraktur or monospace alphabet blocks. These named
OpenType alternatives preserve the original Greek characters. Shared Latin and
Greek forms adapt Anodyne's mathematical alphabet drawings: capitals retain
their geometry, while lowercase homographs are sized to the Greek x-height.
Greek-specific
forms have explicit centre-line drawings below: broad-pen roundhand/chancery,
angular broken strokes for fraktur, and parallel stems for double-struck.
They are new interpretations, not historical facsimiles or affine copies of the
text Greek. The authored paths and compiled UFO masters are editable sources.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
import unicodedata

from fontTools.pens.basePen import BasePen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib.builder import buildLookup, buildSingleSubstSubtable


UPPER = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'
LOWER = 'αβγδεζηθικλμνξοπρστυφχψω'
VARIANTS = 'ςϵϑϰϕϱϖϴ∂∇ϜϝϐϒϹϲ϶ϳ'
MODERN_ACCENTS = 'ΆΈΉΊΌΎΏΪΫάέήίόύώϊϋΐΰ'
BASE_CHARACTERS = UPPER + LOWER + VARIANTS
ACCENTED_CHARACTERS = ''.join(
    chr(cp) for cp in (*range(0x370, 0x400), *range(0x1F00, 0x2000))
    if len(parts := unicodedata.normalize('NFD', chr(cp))) > 1
    and parts[0] in UPPER + LOWER
    and all(unicodedata.category(mark).startswith('M') for mark in parts[1:]))
CHARACTERS = BASE_CHARACTERS + ACCENTED_CHARACTERS
CODEPOINTS = tuple(map(ord, CHARACTERS))
MONO_CELL = 680
STYLE_SLANT = {'script': .15, 'bold-script': .15, 'chancery': .07,
               'fraktur': 0, 'bold-fraktur': 0, 'double-struck': 0, 'monospace': 0}
FEATURES = {
    'ss08': {'style': 'script', 'name': 'Greek roundhand script', 'family': 'Anodyne Greek Script'},
    'ss09': {'style': 'bold-script', 'name': 'Greek bold script', 'family': 'Anodyne Greek Bold Script'},
    'ss10': {'style': 'fraktur', 'name': 'Greek fraktur', 'family': 'Anodyne Greek Fraktur'},
    'ss11': {'style': 'bold-fraktur', 'name': 'Greek bold fraktur', 'family': 'Anodyne Greek Bold Fraktur'},
    'ss12': {'style': 'double-struck', 'name': 'Greek double-struck', 'family': 'Anodyne Greek Double Struck'},
    'ss13': {'style': 'monospace', 'name': 'Greek monospace', 'family': 'Anodyne Greek Monospace'},
    'ss14': {'style': 'chancery', 'name': 'Greek chancery script', 'family': 'Anodyne Greek Chancery'},
}

# Genuine shared forms. Greek-specific letters below are drawn individually.
SHARED = dict(zip('ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ', 'ABEZHIKMNOPTYX'))
SHARED.update(dict(zip('γο νρυϜϹϲϳ'.replace(' ', ''), 'yovpuFCcj')))

# Centre-line coordinates, in design units; capitals 700, lowercase 510.
# Each explicit stroke describes a recognisable Greek form independently of the
# pen treatment. Curves are retained as authored data rather than recovered from
# a finished TrueType outline on each build.
PATHS = {
 'Γ': 'M140 0 L140 680 Q350 730 590 680',
 'Δ': 'M70 0 L330 700 L610 0 Z',
 'Θ': 'M350 710 C80 710 80 -10 350 -10 C620 -10 620 710 350 710 Z M150 350 L550 350',
 'Λ': 'M70 0 L330 700 L610 0',
 'Ξ': 'M90 690 Q330 720 580 690 M140 350 Q340 370 540 350 M90 0 Q340 -20 580 0',
 'Π': 'M130 0 L130 690 L560 690 L560 0',
 'Σ': 'M590 690 L110 690 L390 365 L100 0 L590 0',
 'Φ': 'M350 710 L350 -10 M350 610 C10 610 10 90 350 90 C690 90 690 610 350 610 Z',
 'Ψ': 'M350 710 L350 -10 M80 660 L100 440 C110 170 590 170 600 440 L620 660',
 'Ω': 'M70 0 L245 0 L220 110 C-40 260 70 710 350 710 C630 710 740 260 480 110 L455 0 L630 0',
 'α': 'M430 450 C330 590 95 480 95 245 C95 -20 340 -80 435 175 L490 490 M430 450 L420 100 Q430 -30 550 30',
 'β': 'M125 -190 L125 520 C140 790 480 790 470 580 C465 480 330 405 125 405 M150 405 C540 450 580 0 270 0 Q180 0 125 70',
 'δ': 'M420 470 C100 650 -30 40 280 0 C550 -30 600 400 420 470 C270 570 125 635 240 745 Q330 805 440 720',
 'ε': 'M490 440 C290 625 40 470 155 305 Q220 245 400 260 M155 305 C-10 100 290 -115 500 70',
 'ζ': 'M100 510 Q300 560 510 510 C390 340 80 260 125 90 C165 -60 435 40 400 -130 Q355 -250 230 -160',
 'η': 'M100 500 L100 0 M100 320 C210 610 500 580 500 300 L500 -190',
 'θ': 'M340 720 C95 720 80 -10 300 -10 C555 -10 570 720 340 720 Z M125 350 L510 350',
 'ι': 'M230 510 L185 130 Q165 -45 320 20',
 'κ': 'M110 510 L110 0 M530 510 C410 345 275 235 110 205 M260 260 Q345 200 385 90 Q445 -30 555 30',
 'λ': 'M90 745 C240 820 270 550 325 420 L520 0 M325 420 L80 0',
 'μ': 'M120 500 L120 -190 M120 140 C120 -80 400 -30 465 240 L500 510 M465 240 L465 85 Q485 -25 560 15',
 'ξ': 'M500 700 C320 790 65 650 145 500 Q195 400 460 430 M145 500 C-10 340 130 195 430 230 M150 220 C10 70 170 -20 345 0 Q490 -25 425 -145 Q370 -240 245 -180',
 'π': 'M60 500 Q300 550 590 500 M175 510 L150 70 Q145 -20 85 5 M465 510 L465 75 Q470 -30 565 20',
 'σ': 'M530 500 L295 500 C35 510 40 -10 300 -10 C555 -10 585 380 410 460 M295 500 L600 500',
 'τ': 'M60 500 Q310 540 575 500 M335 515 L300 105 Q300 -35 445 15',
 'φ': 'M330 720 L310 -190 M330 500 C-10 530 -25 -15 315 -15 C650 -15 650 530 330 500 Z',
 'χ': 'M80 540 C220 490 370 75 510 -190 M60 -155 C220 10 370 375 540 530',
 'ψ': 'M330 720 L330 -190 M70 500 L95 210 C125 -60 550 -60 565 230 L580 500',
 'ω': 'M120 500 C-60 270 40 -40 205 0 Q345 15 330 255 M330 255 C315 -80 650 -50 590 280 Q585 420 495 500',
 'ς': 'M485 455 C250 635 -10 380 160 170 Q225 100 370 70 C555 15 420 -215 270 -160',
 'ϵ': 'M500 450 C185 670 -40 -80 490 40 M75 260 L450 260',
 'ϑ': 'M205 515 C100 770 520 800 510 470 C500 155 400 -50 230 5 C80 55 90 350 250 350 L590 350',
 'ϰ': 'M130 500 C35 265 80 -40 205 25 Q255 80 260 250 M550 510 C385 290 310 235 130 205 M260 250 Q380 -55 570 35',
 'ϕ': 'M330 500 C100 500 100 40 330 40 C560 40 560 500 330 500 Z M240 700 Q400 760 360 520 L300 -190',
 'ϱ': 'M115 -160 C-35 -210 -15 -70 100 30 L145 360 C160 590 575 595 540 265 C520 -15 205 -75 130 155',
 'ϖ': 'M60 500 Q315 540 600 500 M130 500 C-40 150 90 -40 235 0 Q345 40 330 290 M330 290 C300 -30 610 -70 575 240 Q575 400 520 500',
 'ϴ': 'M350 710 C80 710 80 -10 350 -10 C620 -10 620 710 350 710 Z M70 350 L630 350',
 '∂': 'M155 655 C360 850 650 630 540 300 C450 -30 95 -110 95 175 C95 420 400 490 545 310',
 '∇': 'M70 700 L610 700 L330 0 Z',
 'ϝ': 'M150 -150 L150 500 L490 500 M150 260 L430 260',
 'ϐ': 'M145 -160 L145 500 C150 795 500 795 480 585 C470 410 150 480 145 235 C145 -90 560 -65 540 220 C520 430 330 410 145 350',
 'ϒ': 'M80 650 C110 790 270 720 350 440 C430 720 590 790 620 650 M350 440 L350 0',
 '϶': 'M80 450 C395 670 620 -80 90 40 M120 260 L505 260',
}

# The Greek-specific blackletter paths have deliberately broken strokes,
# chamfered bowls and split joins. They are not merely the script paths skewed
# or emboldened. Latin-homograph forms use the established fraktur originals.
FRAKTUR = {
 'Γ': 'M130 0 L150 680 L310 730 L585 675 L545 575 M105 75 L225 95',
 'Δ': 'M95 30 L315 690 L360 720 L605 25 L95 30 M160 55 L530 55',
 'Θ': 'M330 710 L160 620 L100 185 L245 0 L425 0 L575 170 L570 545 L440 700 Z M120 350 L550 350',
 'Λ': 'M90 20 L305 685 L355 720 L605 20 M80 20 L190 65 M500 60 L625 15',
 'Ξ': 'M95 680 L295 725 L590 680 M155 350 L345 385 L530 350 M95 30 L300 0 L595 40',
 'Π': 'M125 0 L155 675 L320 720 L555 680 L555 0 M105 35 L215 75 M490 70 L610 20',
 'Σ': 'M590 665 L310 715 L110 660 L370 365 L105 35 L320 -5 L600 40',
 'Φ': 'M350 720 L350 -20 M350 600 L160 550 L70 400 L95 235 L255 110 L445 110 L615 245 L630 405 L535 555 Z',
 'Ψ': 'M350 720 L350 -20 M80 655 L110 310 L265 200 L435 200 L585 310 L620 655',
 'Ω': 'M65 20 L245 20 L245 110 L100 250 L100 540 L245 700 L440 700 L590 540 L590 250 L455 110 L455 20 L635 20',
 'α': 'M430 470 L290 530 L145 460 L85 145 L210 0 L365 45 L470 510 M430 470 L430 55 L540 20',
 'β': 'M120 -180 L155 640 L280 740 L425 700 L490 555 L375 420 L145 400 M145 400 L360 405 L515 285 L490 95 L355 0 L195 40 L135 120',
 'δ': 'M430 475 L250 510 L115 380 L90 125 L230 0 L410 35 L520 200 L500 410 L260 620 L240 735 L345 790 L460 715',
 'ε': 'M490 455 L335 530 L160 470 L95 320 L210 250 L430 270 M210 250 L90 140 L200 15 L370 -5 L505 80',
 'ζ': 'M95 500 L300 545 L510 500 L290 300 L125 145 L170 25 L380 -10 L440 -90 L365 -210 L250 -165',
 'η': 'M110 500 L110 0 M110 335 L260 530 L400 510 L500 385 L500 -190',
 'θ': 'M320 725 L180 610 L105 180 L230 0 L380 15 L510 190 L535 560 L430 710 Z M120 350 L515 350',
 'ι': 'M230 515 L190 90 L255 10 L330 45',
 'κ': 'M110 515 L110 0 M535 500 L390 385 L275 250 L110 210 M275 250 L390 65 L540 15',
 'λ': 'M90 730 L200 780 L265 630 L330 405 L520 10 M330 405 L95 15',
 'μ': 'M115 510 L115 -190 M115 155 L215 0 L355 25 L485 270 L500 510 M485 270 L485 75 L560 10',
 'ξ': 'M495 700 L330 755 L170 690 L105 560 L195 435 L455 435 M195 435 L90 340 L165 210 L420 220 M165 210 L90 110 L190 5 L370 0 L445 -85 L355 -210 L245 -175',
 'π': 'M65 500 L280 540 L595 500 M165 510 L150 55 L85 5 M465 510 L465 60 L565 15',
 'σ': 'M535 495 L285 510 L125 395 L85 170 L215 0 L390 25 L525 180 L510 360 L410 460 M285 510 L605 510',
 'τ': 'M65 505 L305 540 L580 505 M330 520 L300 110 L370 0 L455 35',
 'φ': 'M330 730 L310 -195 M330 510 L145 455 L65 250 L150 60 L305 -10 L485 40 L595 230 L550 420 Z',
 'χ': 'M80 520 L205 445 L365 90 L505 -180 M65 -155 L230 70 L385 375 L540 520',
 'ψ': 'M330 730 L330 -190 M75 500 L95 200 L230 0 L430 0 L560 210 L580 500',
 'ω': 'M125 505 L55 340 L65 100 L200 0 L330 110 L330 300 M330 300 L335 110 L455 0 L585 95 L605 315 L500 505',
 'ς': 'M490 460 L335 535 L165 440 L85 280 L180 135 L375 65 L450 -45 L355 -200 L265 -160',
 'ϵ': 'M500 450 L345 520 L170 445 L90 265 L140 95 L315 -10 L495 40 M95 265 L450 265',
 'ϑ': 'M210 515 L160 665 L275 755 L435 700 L515 530 L475 195 L345 0 L205 30 L115 175 L150 340 L590 340',
 'ϰ': 'M130 510 L80 260 L125 35 L205 20 L260 250 M550 510 L380 330 L130 205 M260 250 L400 35 L570 35',
 'ϕ': 'M330 500 L175 435 L120 235 L190 65 L335 40 L490 110 L540 300 L465 460 Z M240 710 L380 750 L365 520 L300 -190',
 'ϱ': 'M115 -160 L25 -210 L-5 -95 L110 45 L145 350 L265 525 L435 500 L550 335 L500 140 L355 0 L185 65',
 'ϖ': 'M65 505 L295 540 L605 505 M135 505 L65 285 L105 65 L235 0 L330 110 L330 290 M330 290 L350 70 L475 0 L585 100 L580 330 L520 505',
 'ϴ': 'M330 710 L160 620 L100 185 L245 0 L425 0 L575 170 L570 545 L440 700 Z M70 350 L630 350',
 '∂': 'M155 665 L310 750 L470 655 L555 485 L525 245 L385 30 L220 -10 L95 135 L140 335 L335 440 L545 310',
 '∇': 'M80 690 L610 690 L335 10 Z',
 'ϝ': 'M150 -155 L150 500 L320 535 L495 500 M150 260 L430 260',
 'ϐ': 'M145 -160 L155 640 L280 750 L430 700 L490 550 L380 410 L145 235 L185 50 L330 0 L495 85 L540 245 L415 390 L145 350',
 'ϒ': 'M80 650 L135 745 L265 640 L350 440 L440 640 L560 745 L620 650 M350 440 L350 0',
 '϶': 'M80 450 L235 520 L410 445 L490 265 L440 95 L265 -10 L85 40 M135 265 L485 265',
}


class SkeletonPen(BasePen):
    def __init__(self):
        super().__init__(None)
        self.paths, self.current = [], []

    def _moveTo(self, point):
        self.current = [point]

    def _lineTo(self, point):
        self.current.append(point)

    def _qCurveToOne(self, control, end):
        start = self.current[-1]
        for i in range(1, 13):
            t, m = i/12, 1-i/12
            self.current.append((m*m*start[0]+2*m*t*control[0]+t*t*end[0],
                                 m*m*start[1]+2*m*t*control[1]+t*t*end[1]))

    def _curveToOne(self, c1, c2, end):
        start = self.current[-1]
        for i in range(1, 17):
            t, m = i/16, 1-i/16
            self.current.append((m**3*start[0]+3*m*m*t*c1[0]+3*m*t*t*c2[0]+t**3*end[0],
                                 m**3*start[1]+3*m*m*t*c1[1]+3*m*t*t*c2[1]+t**3*end[1]))

    def _closePath(self):
        if self.current[-1] == self.current[0]:
            self.current.pop()
        self.paths.append((self.current, True))
        self.current = []

    def _endPath(self):
        self.paths.append((self.current, False))
        self.current = []


def area(points):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points, points[1:]+points[:1]))/2


def oriented(points, clockwise=True):
    if (area(points) < 0) != clockwise:
        points = list(reversed(points))
    return [(x,y,True) for x,y in points]


def unit(vector):
    length = math.hypot(*vector)
    return (vector[0]/length,vector[1]/length) if length else (0,1)


def stroke_path(points, closed, major, minor, angle, square=False):
    """Stroke with an elliptical broad nib, preserving source point counts."""
    left, right = [], []
    for i,p in enumerate(points):
        before = points[(i-1)%len(points)] if closed or i else points[0]
        after = points[(i+1)%len(points)] if closed or i+1<len(points) else points[-1]
        tx,ty = unit((after[0]-before[0],after[1]-before[1]))
        nx,ny = -ty,tx
        ax,ay = math.cos(angle),math.sin(angle)
        radius = math.hypot(major*(nx*ax+ny*ay),minor*(-nx*ay+ny*ax))/2
        left.append((p[0]+nx*radius,p[1]+ny*radius))
        right.append((p[0]-nx*radius,p[1]-ny*radius))
    if closed:
        outside,inside = sorted((left,right), key=lambda c:abs(area(c)),reverse=True)
        return [oriented(outside),oriented(inside,False)]
    if square:
        return [oriented(left+list(reversed(right)))]
    # Rounded terminals are authored geometry rather than a renderer effect.
    cap_end,cap_start = [],[]
    for at,other,target in ((points[-1],points[-2],cap_end),(points[0],points[1],cap_start)):
        tx,ty = unit((at[0]-other[0],at[1]-other[1]))
        base = math.atan2(ty,tx)+math.pi/2
        for k in range(1,8):
            a = base-math.pi*k/8
            target.append((at[0]+math.cos(a)*minor/2,at[1]+math.sin(a)*minor/2))
    return [oriented(left+cap_end+list(reversed(right))+cap_start)]


def flatten(outline, glyphs):
    contours = [list(c) for c in outline.contours]
    for name,x,y,transform in outline.components:
        matrix = transform or ((1,0),(0,1))
        for contour in flatten(glyphs[name],glyphs):
            contours.append([(matrix[0][0]*px+matrix[1][0]*py+x,
                              matrix[0][1]*px+matrix[1][1]*py+y,on) for px,py,on in contour])
    return contours


def upper_body_center(outline, glyphs):
    """Anchor an accent to the upper body, excluding descenders and swashes."""
    points = [p for contour in flatten(outline, glyphs) for p in contour]
    top = max(p[1] for p in points)
    bottom = max(0, min(p[1] for p in points))
    upper = [p[0] for p in points if p[1] >= top-(top-bottom)*.25]
    return (min(upper)+max(upper))/2


def remap_attachment(value, old, new, old_glyphs, new_glyphs):
    previous = [p[0] for c in flatten(old, old_glyphs) for p in c]
    current = [p[0] for c in flatten(new, new_glyphs) for p in c]
    x0,x1=min(previous),max(previous);y0,y1=min(current),max(current)
    return y0+(value-x0)*(y1-y0)/(x1-x0) if x1!=x0 else value


def latin_codepoint(letter,style):
    prefix = {'script':'SCRIPT','bold-script':'BOLD SCRIPT','fraktur':'FRAKTUR',
              'bold-fraktur':'BOLD FRAKTUR','double-struck':'DOUBLE-STRUCK','monospace':'MONOSPACE',
              'chancery':'SCRIPT'}[style]
    case = 'CAPITAL' if letter.isupper() else 'SMALL'
    name = f'MATHEMATICAL {prefix} {case} {letter.upper()}'
    try:
        return ord(unicodedata.lookup(name))
    except KeyError:
        holes = {'script':{'B':0x212C,'E':0x2130,'F':0x2131,'H':0x210B,'I':0x2110,'L':0x2112,'M':0x2133,'R':0x211B,'e':0x212F,'g':0x210A,'o':0x2134},
                 'fraktur':{'C':0x212D,'H':0x210C,'I':0x2111,'R':0x211C,'Z':0x2128},
                 'double-struck':{'C':0x2102,'H':0x210D,'N':0x2115,'P':0x2119,'Q':0x211A,'R':0x211D,'Z':0x2124}}
        return holes.get('script' if style=='chancery' else style,{}).get(letter)


def single_mapping(font,tag):
    table=font['GSUB'].table
    result={}
    for feature in table.FeatureList.FeatureRecord:
        if feature.FeatureTag==tag:
            for index in feature.Feature.LookupListIndex:
                lookup=table.LookupList.Lookup[index]
                for sub in lookup.SubTable:
                    sub=getattr(sub,'ExtSubTable',sub)
                    result.update(getattr(sub,'mapping',{}))
    return result


def optical_alternates(font):
    """Both ssty optical sizes can precede a user-selected math alphabet."""
    table = font['GSUB'].table
    result = {}
    for feature in table.FeatureList.FeatureRecord:
        if feature.FeatureTag != 'ssty':
            continue
        for index in feature.Feature.LookupListIndex:
            for sub in table.LookupList.Lookup[index].SubTable:
                sub = getattr(sub, 'ExtSubTable', sub)
                for source, target in getattr(sub, 'mapping', {}).items():
                    result.setdefault(source, []).append(target)
                for source, targets in getattr(sub, 'alternates', {}).items():
                    result.setdefault(source, []).extend(targets)
    return result


def accent_groups(marks, cmap):
    """Keep the font's designed breathing/tone and diaeresis/tone pairs."""
    combined = {
        ('\u0308', '\u0301'): 0x0344,
        ('\u0308', '\u0300'): 0x1FED,
        ('\u0308', '\u0342'): 0x1FC1,
        ('\u0313', '\u0300'): 0x1FCD,
        ('\u0313', '\u0301'): 0x1FCE,
        ('\u0313', '\u0342'): 0x1FCF,
        ('\u0314', '\u0300'): 0x1FDD,
        ('\u0314', '\u0301'): 0x1FDE,
        ('\u0314', '\u0342'): 0x1FDF,
    }
    above = [mark for mark in marks if unicodedata.combining(mark) != 240]
    below = [mark for mark in marks if unicodedata.combining(mark) == 240]
    pair = combined.get(tuple(above))
    if pair in cmap:
        above = [chr(pair)]
    return above, below


def register(font,tag,mapping):
    table=font['GSUB'].table
    if any(r.FeatureTag==tag for r in table.FeatureList.FeatureRecord):
        raise ValueError(f'{tag} already exists')
    table.LookupList.Lookup.append(buildLookup([buildSingleSubstSubtable(mapping)]))
    table.LookupList.LookupCount=len(table.LookupList.Lookup)
    record=ot.FeatureRecord();record.FeatureTag=tag;record.Feature=ot.Feature()
    params=ot.FeatureParamsStylisticSet();params.Version=0
    params.UINameID=font['name'].addName(FEATURES[tag]['name'],platforms=((3,1,0x409),))
    record.Feature.FeatureParams=params
    record.Feature.LookupListIndex=[len(table.LookupList.Lookup)-1];record.Feature.LookupCount=1
    old=table.FeatureList.FeatureRecord;old.append(record);index=len(old)-1
    langs=[lang for sr in table.ScriptList.ScriptRecord for lang in
           [sr.Script.DefaultLangSys]+[x.LangSys for x in sr.Script.LangSysRecord] if lang is not None]
    for lang in langs:lang.FeatureIndex.append(index);lang.FeatureCount=len(lang.FeatureIndex)
    permutation=sorted(range(len(old)),key=lambda i:old[i].FeatureTag)
    remap={before:after for after,before in enumerate(permutation)}
    table.FeatureList.FeatureRecord=[old[i] for i in permutation];table.FeatureList.FeatureCount=len(old)
    for lang in langs:
        lang.FeatureIndex=sorted(remap[i] for i in lang.FeatureIndex)
        if lang.ReqFeatureIndex!=0xFFFF:lang.ReqFeatureIndex=remap[lang.ReqFeatureIndex]


def authored(character,style,weight,Outline):
    blackletter='fraktur' in style
    bold=style.startswith('bold-')
    paths=(FRAKTUR if blackletter else PATHS).get(character)
    if paths is None:
        raise ValueError(f'No authored Greek {style} drawing for {character}')
    pen=SkeletonPen();parse_path(paths,pen)
    nib={100:30,400:105,700:150,900:180}[weight]
    if blackletter:nib*=1.15
    if bold:nib*=1.38
    thin={100:8,400:13,700:20,900:25}[weight]*(1.18 if bold else 1)
    shear=STYLE_SLANT[style]
    if style=='chancery':nib*=.76
    if style=='monospace':nib={100:26,400:70,700:110,900:140}[weight];thin=nib
    if style=='double-struck':nib=thin={100:14,400:50,700:74,900:92}[weight]
    angle=math.radians(35 if blackletter else 20 if style=='chancery' else 30)
    contours=[]
    for points,closed in pen.paths:
        transformed=[(x+shear*y,y) for x,y in points]
        contours.extend(stroke_path(transformed,closed,nib,thin,angle,square=style=='monospace'))
        if style=='monospace' and not closed and sum(math.dist(a,b) for a,b in zip(transformed,transformed[1:]))>400:
            # Real slab terminals complement the existing Latin mono family;
            # fixed-width Greek is not just a proportional font with new widths.
            for endpoint,neighbour in ((transformed[0],transformed[1]),(transformed[-1],transformed[-2])):
                tx,ty=unit((neighbour[0]-endpoint[0],neighbour[1]-endpoint[1]));x,y=endpoint
                half=max(65,nib*.9);depth=max(14,nib*.26)
                if abs(tx)<.3:
                    contours.append(oriented([(x-half,y-depth),(x-half,y+depth),(x+half,y+depth),(x+half,y-depth)]))
                elif abs(ty)<.3:
                    contours.append(oriented([(x-depth,y-half*.65),(x-depth,y+half*.65),(x+depth,y+half*.65),(x+depth,y-half*.65)]))
        if blackletter and not closed:
            for x,y in (transformed[0],transformed[-1]):
                r=nib*.62
                contours.append(oriented([(x-r,y),(x,y+r*.75),(x+r,y),(x,y-r*.75)]))
        if style=='double-struck':
            # Blackboard construction: a second stroke beside the predominantly
            # vertical pieces, with horizontal bars remaining single.
            separation=nib*.65+15
            if character=='Ξ':
                contours.extend(stroke_path([(x,y+separation) for x,y in transformed],closed,nib*.25,thin*.25,0))
            run=[]
            for a,b in zip(transformed,transformed[1:]):
                if abs(b[1]-a[1])>abs(b[0]-a[0])*.65:
                    if not run:run=[a]
                    run.append(b)
                elif run:
                    contours.extend(stroke_path([(x+separation,y) for x,y in run],False,nib*.25,thin*.25,0));run=[]
            if run:contours.extend(stroke_path([(x+separation,y) for x,y in run],False,nib*.25,thin*.25,0))
    if style in ('script','bold-script','chancery'):
        # Distinct entry strokes and terminals complement the broad-nib bowls.
        # Fraktur and blackboard alphabets do not receive these flourishes.
        start=pen.paths[0][0][0]
        x,y=start
        if y<80:
            extra=SkeletonPen()
            curl=f'M{x-115} {y-15} C{x-180} {y-80} {x-210} {y+55} {x-135} {y+35} Q{x-50} {y-20} {x} {y}' if style!='chancery' else f'M{x-80} {y-15} Q{x-25} {y+35} {x} {y}'
            parse_path(curl,extra)
            for points,closed in extra.paths:
                contours.extend(stroke_path([(px+shear*py,py) for px,py in points],closed,nib*.72,thin,angle))
    xmin=min(p[0] for c in contours for p in c);xmax=max(p[0] for c in contours for p in c)
    shift=35-xmin
    contours=[[(x+shift,y,on) for x,y,on in c] for c in contours]
    advance=max(260 if character in LOWER+VARIANTS else 640,xmax+shift+35)
    if style=='monospace':
        scale=min(1,520/(xmax-xmin));centre=(xmin+xmax)/2+shift
        contours=[[(MONO_CELL/2+(x-centre)*scale,y,on) for x,y,on in c] for c in contours];advance=MONO_CELL
    return Outline(contours,adv=advance)


def math_info(font,targets,glyphs,attachments):
    info=font['MATH'].table.MathGlyphInfo
    order=font.getReverseGlyphMap()
    for attr,cov_attr,values_attr,count_attr in (
        ('MathItalicsCorrectionInfo','Coverage','ItalicsCorrection','ItalicsCorrectionCount'),
        ('MathTopAccentAttachment','TopAccentCoverage','TopAccentAttachment','TopAccentAttachmentCount')):
        table=getattr(info,attr)
        if table is None:continue
        records=dict(zip(getattr(table,cov_attr).glyphs,getattr(table,values_attr)))
        for name,outline in targets.items():
            record=ot.MathValueRecord();record.DeviceTable=None
            xs=[p[0] for c in flatten(outline,glyphs) for p in c]
            record.Value=round(max(0,max(xs)-outline.adv+18) if attr=='MathItalicsCorrectionInfo' else attachments[name])
            records[name]=record
        names=sorted(records,key=order.__getitem__)
        getattr(table,cov_attr).glyphs=names;setattr(table,values_attr,[records[n] for n in names]);setattr(table,count_attr,len(names))


@dataclass
class GreekStylesModel:
    names: tuple[str,...]
    mappings: dict

    def condensed(self,name,weight):
        return None


def apply_to_normal_anchors(normal,R,B=None,noto=None,notoC=None):
    """Append compatible Greek drawings to four normal-width weight anchors."""
    from build import Outline,write
    cmap=R.getBestCmap();chancery=single_mapping(R,'ss01')
    accent_info=R['MATH'].table.MathGlyphInfo.MathTopAccentAttachment
    source_accents=dict(zip(accent_info.TopAccentCoverage.glyphs,
                           (record.Value for record in accent_info.TopAccentAttachment)))
    original_order=list(R.getGlyphOrder())
    available=[c for c in BASE_CHARACTERS if ord(c) in cmap]
    missing=set(UPPER+LOWER+'ςϵϑϰϕϱϖϴ∂∇')-set(available)
    if missing:raise ValueError('Missing base mathematical Greek: '+''.join(sorted(missing)))
    targets={};mappings={};names=[];attachments={}
    for tag,spec in FEATURES.items():
        style=spec['style'];mapping={}
        for character in available:
            name=f'uni{ord(character):04X}.anodyne.grk.{style}'
            donor=None
            if character in SHARED:
                codepoint=latin_codepoint(SHARED[character],style)
                donor=cmap.get(codepoint) if codepoint else None
                if donor and style=='chancery':donor=chancery.get(donor,donor)
            for weight,glyphs in normal.items():
                if donor:
                    original=glyphs[donor]
                    outline=Outline(flatten(original,glyphs),adv=original.adv)
                    attachment=source_accents.get(donor)
                    if character.islower():
                        # Source script y/v/u have an x-height near 310, versus
                        # the Greek-specific 510. Keep their authentic contour
                        # style but give the Greek alphabet one coherent size.
                        # One Regular-derived factor applies to every weight;
                        # descenders scale around the baseline with the body.
                        regular=flatten(normal[400][donor],normal[400])
                        height=max(p[1] for c in regular for p in c)
                        scale=510/height
                        outline.contours=[[(x*scale,y*scale,on) for x,y,on in c] for c in outline.contours]
                        outline.adv*=scale
                        if attachment is not None:attachment*=scale
                    if style=='monospace':
                        points=[p for c in outline.contours for p in c]
                        x0,x1=min(p[0] for p in points),max(p[0] for p in points)
                        fit=min(1,520/(x1-x0))
                        if fit<1:
                            middle=(x0+x1)/2
                            outline.contours=[[(middle+(x-middle)*fit,y,on) for x,y,on in c] for c in outline.contours]
                            if attachment is not None:attachment=middle+(attachment-middle)*fit
                        delta=(MONO_CELL-outline.adv)/2
                        outline.contours=[[(x+delta,y,on) for x,y,on in c] for c in outline.contours];outline.adv=MONO_CELL
                        if attachment is not None:attachment+=delta
                else:
                    outline=authored(character,style,weight,Outline)
                    attachment=None
                glyphs[name]=outline
                if weight==400:
                    attachments[name]=attachment if attachment is not None else upper_body_center(outline,glyphs)
            write(R,name,normal[400][name])
            targets[name]=normal[400][name]
            mapping[cmap[ord(character)]]=name
            names.append(name)
        # Greek accents retain their ordinary Unicode and combine the
        # styled letter with the font's existing, weight-compatible accent.
        # No unstyled precomposed Greek is used as a fallback.
        for character in ACCENTED_CHARACTERS:
            if ord(character) not in cmap:
                continue
            decomposition=unicodedata.normalize('NFD',character)
            base,*marks=decomposition
            base_name=f'uni{ord(base):04X}.anodyne.grk.{style}'
            above,below=accent_groups(marks,cmap)
            name=f'uni{ord(character):04X}.anodyne.grk.{style}'
            for weight,glyphs in normal.items():
                body=glyphs[base_name]
                body_points=[p for c in flatten(body,glyphs) for p in c]
                left=min(p[0] for p in body_points);top=max(p[1] for p in body_points)
                bottom=min(p[1] for p in body_points)
                attachment=remap_attachment(attachments[base_name],normal[400][base_name],body,
                                            normal[400],glyphs)
                components=[(base_name,0,0,None)]
                for mark in above+below:
                    mark_name=cmap.get(ord(mark))
                    if mark_name is None:raise ValueError(f'Missing Greek accent U+{ord(mark):04X}')
                    points=[p for c in flatten(glyphs[mark_name],glyphs) for p in c]
                    x0,x1=min(p[0] for p in points),max(p[0] for p in points)
                    y0,y1=min(p[1] for p in points),max(p[1] for p in points)
                    left_accent=base in UPPER and any(m in marks for m in '\u0300\u0301\u0313\u0314') and mark in above
                    dx=left-16-x1 if left_accent else attachment-(x0+x1)/2
                    dy=top-70-y0 if left_accent else top+22-y0
                    if left_accent and style=='monospace':
                        dx=body.adv*.25-(x0+x1)/2
                        dy=top+22-y0
                    if mark in below:
                        dx=body.adv/2-(x0+x1)/2
                        dy=min(-45,bottom-22)-y1
                    components.append((mark_name,dx,dy,None))
                    if mark in above and not left_accent:top=dy+y1
                glyphs[name]=Outline(components=components,adv=body.adv)
            write(R,name,normal[400][name]);targets[name]=normal[400][name]
            attachments[name]=attachments[base_name]
            mapping[cmap[ord(character)]]=name;names.append(name)
        # Mathematical Greek from Unicode and TeX's existing math alphabet
        # assignments must receive the selected family too. Direct <font>
        # decomposition keeps epsilon/theta/etc. symbol variants distinct.
        for cp,source_name in cmap.items():
            decomposition=unicodedata.decomposition(chr(cp)).split()
            if len(decomposition)==2 and decomposition[0]=='<font>':
                base=int(decomposition[1],16)
                if base in cmap and cmap[base] in mapping:
                    mapping[source_name]=mapping[cmap[base]]
        optical=optical_alternates(R)
        for source_name,target_name in list(mapping.items()):
            for alternate in optical.get(source_name,[]):
                mapping[alternate]=target_name
        mappings[tag]=mapping
        register(R,tag,mapping)
    R.setGlyphOrder(original_order+names)
    R['glyf'].glyphOrder=R.getGlyphOrder()
    math_info(R,targets,normal[400],attachments)
    if 'GDEF' in R and getattr(R['GDEF'].table,'GlyphClassDef',None):
        R['GDEF'].table.GlyphClassDef.classDefs.update({n:1 for n in names})
    return GreekStylesModel(tuple(names),mappings)
