# make_launcher_drawings.py
#
# Three TechDraw construction drawings (ANSI B 11x17 landscape, title block,
# BOM, balloons, notes) of the pig launcher built by make_pig_launcher.py:
#
#   PL-001  major barrel spool   [F4] .. [F5], with [T3], [F10], drain, vent
#   PL-002  4" kicker line       [F8] .. [F9], with flange-roll details
#   PL-003  1" equalization line from the first nipple off each sockolet
#
# Run make_pig_launcher.py FIRST: it rebuilds Header_with_pig_launcher.FCStd
# from the header copy and so deletes these drawings.  This macro works on
# that document (opening it if needed), tears down any previous drawings,
# rebuilds all three pages, verifies them numerically and saves.
#
# What it demonstrates beyond examples/TechDraw_example (whose helpers it
# imports as `tdx`) -- see skills/techdraw-drawing/:
#   * several pages in one document, one App::Part container per spool,
#     membership chosen by model mark ([F4], [P8], ...), BOM keyed by mark;
#   * views aligned to skewed legs (elevation normal to a leg's vertical
#     plane) and an iso turned 45 deg off a planar line;
#   * work points for tees, socket fittings, unions and SW valves; dimension
#     lanes so parallel dims never share a line;
#   * dimension text in ft-in to the nearest 1/16 in (FormatSpec + Arbitrary);
#   * flange bolt-hole roll measured from the solids, and an Angle3Pt
#     dimension of elbow roll vs plant Y on from-above flange details.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute).  Units are mm internally.

import importlib.util
import math
import os
import re
import sys
import textwrap
import time
from math import gcd

import FreeCAD
import Part
from FreeCAD import Vector

try:
    import FreeCADGui
    _HAS_GUI = True
except Exception:
    _HAS_GUI = False


# ---------------------------------------------------------------------------
# Bootstrap: repo root, quetzal_env, and the TechDraw example's helpers
# ---------------------------------------------------------------------------

def _repo_root():
    """Walk up from this file to the directory that holds quetzal_env.py."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()  # __file__ undefined when exec()'d from the console
    while True:
        if os.path.isfile(os.path.join(here, "quetzal_env.py")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise RuntimeError(
                "Cannot find quetzal_env.py at or above %s -- run this macro "
                "from its place in the AI_Piping_Design repo." % here)
        here = parent


_ROOT = _repo_root()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import quetzal_env as qenv  # noqa: E402,F401  (also resolves Quetzal for tdx)

_spec = importlib.util.spec_from_file_location(
    "tdx", os.path.join(_ROOT, "examples", "TechDraw_example", "make_techdraw_page.py"))
tdx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tdx)

val = tdx._val
gp = tdx._gports
Zh = Vector(0, 0, 1)

HERE = os.path.join(_ROOT, "examples", "pig_trap_design")
MODEL = os.path.join(HERE, "Header_with_pig_launcher.FCStd")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAG = "LaunchDwg"                 # prefix on every drawing object made here
DIM_GAP, DIM_STEP = 12.0, 9.0     # page mm: outline -> first dim, lane pitch
Y_LANE_STEP = 3.4 * DIM_STEP      # vertical dims print horizontal ft-in text
BOM_ROW_PX, BOM_TEXT, PX_MM = 15, 9.0, 0.2646    # spreadsheet px -> page mm
NOTE_TEXT, NOTE_LINE_MM, NOTE_WRAP = 2.5, 5.2, 66
RIGHT_COL = (340.0, 256.0)        # BOM centre-x, top-y (page mm, ANSI B)
BORDER = (22.0, 409.0, 22.0, 257.0)   # inner drawing border xmin, xmax, ymin, ymax
SMALL_BORE = ("DN15", "DN20", "DN25", "DN32", "DN40", "DN50")
STD_NIPPLES_IN = (3, 4, 6, 12)    # pre-cut nipple lengths stocked for NPS <= 2
FRAC_DEN = 16                     # display lengths to the nearest 1/16 in
MARK_RE = re.compile(r"^\[([A-Z]+\d+)\]")
ISO = ((0.57735, 0.57735, 0.57735), (-0.70711, 0.70711, 0.0))


def ftin(mm, den=FRAC_DEN):
    """Feet-inch-fraction text, rounded to the nearest 1/den in:
    4036.65 mm -> 13'-2 15/16", 326.8 mm -> 1'-0 7/8", 300.45 mm -> 11 13/16".

    FreeCAD's own 'Building US' schema (with the FracInch preference) TRUNCATES
    to the fraction -- 158.923 in prints 2 7/8 over the feet, not 2 15/16 --
    joins the fraction with a '+', and drops a zero inch.  So the text is
    formatted here and written into the dimension (skill section 11.3)."""
    n = int(round(mm / 25.4 * den))
    ft, rem = divmod(n, 12 * den)
    whole, frac = divmod(rem, den)
    fs = ""
    if frac:
        g = gcd(frac, den)
        fs = "%d/%d" % (frac // g, den // g)
    if fs:
        ins = "%d %s" % (whole, fs) if (whole or ft) else fs
    else:
        ins = str(whole)
    return ("%d'-%s\"" % (ft, ins)) if ft else ("%s\"" % ins)


def mark_of(o):
    m = MARK_RE.match(o.Label)
    return m.group(1) if m else None


def objs_by_mark(doc):
    return {mark_of(o): o for o in doc.Objects if mark_of(o)}


def mark_sort_key(m):
    order = "FPORTEVNGB"
    return (order.index(m[0]) if m[0] in order else 99, int(m[1:]))


def ell_wp(o):
    (p0, d0), (p1, d1) = gp(o)[:2]
    return tdx._line_intersection(p0, d0, p1, d1)


def hdir(v):
    v = Vector(v.x, v.y, 0)
    v.normalize()
    return v


# ---------------------------------------------------------------------------
# Flange bolt-hole roll, measured from the solids
# ---------------------------------------------------------------------------

def hole_angles(obj, axis_pt, axis, ref, rad, tol=0.6):
    """Clock angles (deg) of bolt-hole / stud cylinders of radius `rad` about
    `axis`, measured from `ref`, right-handed about `axis`.  Works on flanges,
    valve end flanges and Bolts_Nuts alike, so mating parts can be compared."""
    axis = Vector(axis); axis.normalize()
    ref = Vector(ref); ref = ref - axis * ref.dot(axis); ref.normalize()
    side = axis.cross(ref)
    angs = set()
    for f in obj.Shape.Faces:
        srf = f.Surface
        if srf.__class__.__name__ != "Cylinder" or abs(srf.Radius - rad) > tol:
            continue
        if abs(abs(Vector(srf.Axis).dot(axis)) - 1) > 1e-4:
            continue
        c = Vector(srf.Center) - axis_pt
        r = c - axis * c.dot(axis)
        if r.Length > 1:
            angs.add(round(math.degrees(math.atan2(r.dot(side), r.dot(ref))) % 360, 3))
    return sorted(angs)


def flange_roll(flange, mate, spool_dir):
    """Roll of a vertical flange's bolt pattern relative to the spool CL,
    viewed from above (+Z toward the viewer, CCW positive).  Raises unless the
    mating part's holes coincide -- alignTwoPorts leaves roll free, so this is
    a real check, not a formality."""
    face = gp(flange)[0][0]
    rad = val(flange.f) / 2.0
    n = int(flange.n)
    pitch = 360.0 / n
    own = hole_angles(flange, face, Zh, spool_dir, rad)
    other = hole_angles(mate, face, Zh, spool_dir, rad)
    if len(own) != n or own != other:
        raise RuntimeError("%s holes %s do not match mate %s holes %s"
                           % (flange.Label, own, mate.Label, other))
    nearest = min(own, key=lambda a: min(a, 360.0 - a))    # closest to the CL
    return dict(n=n, pitch=pitch, holes=own,
                nearest=nearest if nearest <= 180 else nearest - 360,
                from_2hole=(own[0] % pitch) - pitch / 2.0)


# ---------------------------------------------------------------------------
# Spool definitions -- the only place that knows this particular model
# ---------------------------------------------------------------------------

def spool_defs(M):
    d_h = hdir(ell_wp(M["E4"]) - ell_wp(M["E3"]))           # kicker skew leg
    d1 = hdir(ell_wp(M["E6"]) - M["T5"].Placement.Base)     # eq top leg
    dB = hdir(M["T4"].Placement.Base - ell_wp(M["E5"]))     # eq bottom leg

    def elev(x):
        """Elevation normal to the vertical plane containing x: the leg reads
        true length along page-right, +Z is page-up."""
        return (tuple(x.cross(Zh)), tuple(x))

    def iso_off(plane_dir):
        """Iso-style viewpoint 45 deg off a vertical plane containing
        plane_dir, so a planar line reads broadside instead of edge-on."""
        h = plane_dir.cross(Zh) + plane_dir
        h.normalize()
        d = Vector(h.x * 0.81650, h.y * 0.81650, 0.57735)
        x = Zh.cross(d)
        x.normalize()
        return (tuple(d), tuple(x))

    # views: (key, caption, Direction, XDirection, page pos, fit box)
    return [
        dict(key="barrel", no="PL-001", sheet="1 OF 3",
             title2="MAJOR BARREL SPOOL",
             welded=["F4", "P7", "O5", "R1", "P8", "O3", "F11", "O4", "P11",
                     "T3", "F5", "F10"],
             assembly=["V4", "G4", "B4", "G5", "B5", "F6", "G8", "B8", "G9", "B9",
                       "V6", "G10", "B10", "F12", "V7"],
             views=[("iso", "ISOMETRIC", ISO[0], ISO[1], (140, 200), (250, 100)),
                    ("elev", "ELEVATION", (1, 0, 0), (0, 1, 0),
                     (145, 100), (255, 70))],
             extra=[("F4 face to F5 face", "elev", ("face", "F4"), ("face", "F5"),
                     "DistanceX")],
             notes=["TRAP VALVE [V4] BOLTS TO [F4]; CLOSURE [F6] BOLTS TO [F5].",
                    "KICKER LINE (PL-002) BOLTS TO [F10].",
                    "ECC. REDUCER [R1] INSTALLED FLAT ON BOTTOM.",
                    "PIG SPACE: 8'-0\", [R1] LARGE-END WELD TO [T3] BRANCH BORE.",
                    "EQ. LINE (PL-003) SOCKET-WELDS INTO SOCKOLET [O5]."]),
        dict(key="kicker", no="PL-002", sheet="2 OF 3",
             title2="KICKER LINE 4 IN",
             welded=["F8", "E3", "P9", "O6", "E4", "P10", "F9"],
             assembly=["V5", "G6", "B6", "G7", "B7"],
             views=[("iso", "ISOMETRIC", ISO[0], ISO[1], (140, 146), (230, 58)),
                    ("elev", "ELEVATION IN PLANE OF KICKER (TRUE LENGTH)",
                     *elev(d_h), (122, 86), (200, 50))],
             extra=[("F8 face to F9 face", "elev", ("face", "F8"), ("face", "F9"),
                     "DistanceY")],
             # (key, caption, source marks, Direction, XDirection, page pos)
             details=[("detF8", "DETAIL [F8]",
                       ["F8", "E3"], (0, 0, 1), tuple(d_h), (75, 229)),
                      ("detF9", "DETAIL [F9]",
                       ["F9", "P10", "E4"], (0, 0, 1), tuple(d_h), (195, 229))],
             # (detail, flange, elbow, elbow's horizontal direction off the flange)
             roll_dims=[("detF8", "F8", "E3", d_h), ("detF9", "F9", "E4", -d_h)],
             roll=[("F8", flange_roll(M["F8"], M["V5"], d_h)),
                   ("F9", flange_roll(M["F9"], M["F10"], d_h))],
             notes=["[F8] BOLTS TO KICKER VALVE [V5]; [F9] BOLTS TO [F10] (PL-001).",
                    "KICKER RUN [P9] IS SKEWED %.1f DEG IN PLAN FROM THE BARREL "
                    "AXIS; LAY OUT IN ITS OWN PLANE."
                    % math.degrees(d_h.getAngle(Vector(0, 1, 0))),
                    "EQ. LINE (PL-003) SOCKET-WELDS INTO SOCKOLET [O6].",
                    "DETAILS [F8]/[F9] ARE VIEWED FROM ABOVE WITH THE SPOOL CL "
                    "RUNNING TO THE RIGHT; HIDDEN LINES SHOWN."]),
        dict(key="eq", no="PL-003", sheet="3 OF 3",
             title2="EQUALIZATION LINE 1 IN",
             welded=["P12", "T4", "P13", "P14", "N1", "P15", "E5", "P16", "V9",
                     "P17", "E6", "P18", "T5", "P19", "P20"],
             assembly=["V8", "V10"],
             views=[("iso", "ISOMETRIC", *iso_off(d1), (215, 150), (100, 190)),
                    ("elev", "ELEVATION IN PLANE OF EQ. LINE",
                     *elev(d1), (100, 145), (85, 170))],
             extra=[("T4 CL to T5 CL", "elev", ("wp", "T4"), ("wp", "T5"),
                     "DistanceY")],
             notes=["NIPPLES [P12] AND [P19] SOCKET-WELD INTO SOCKOLETS [O5] "
                    "(PL-001) AND [O6] (PL-002).",
                    "[P13]/[P20] ARE THREAD-ONE-END; VENT VALVES [V8]/[V10] "
                    "THREAD ON; OUTLETS PLUGGED.",
                    "[V9] SOCKET-WELD BALL VALVE (MODELLED ON THREADED BODY DIMS).",
                    "UNION [N1] SPLITS THE LINE FOR REMOVAL.",
                    "STD PRE-CUT NIPPLES: [P18] 6 IN, [P17] 12 IN, [P12]/[P13]/[P19]/"
                    "[P20] 3 IN. [P14], [P15], [P16] ARE CUT TO LENGTH (FIXED BY "
                    "THE SOCKOLET LOCATIONS).",
                    ("EQ. LINE IS PLANAR: ONE VERTICAL PLANE, SQUARE (%.1f DEG) TO "
                     "KICKER RUN [P9]." % math.degrees(d1.getAngle(d_h)))
                    if d1.getAngle(dB) < math.radians(0.05) else
                    ("[P14]/[P15] RUN %.1f DEG IN PLAN FROM [P18]."
                     % math.degrees(d1.getAngle(dB)))]),
    ]


# ---------------------------------------------------------------------------
# Work points
# ---------------------------------------------------------------------------

def wp_of(obj, port_pos, members):
    """Work point a pipe end runs to -> (point, kind, anchor component).

    Extends tdx._resolve_work_point to the fittings this model uses: a Quetzal
    Tee / SocketTee / SocketEll has its work point at its local origin, a
    flange resolves to its raised face, an outlet to the run centreline.  A
    union or socket-weld valve is a 'weld' point at its port.  An end with
    nothing welded to it in THIS spool is 'end' (it runs to another sheet)."""
    nb = tdx._attached(obj, port_pos, members)
    if nb is None:
        return port_pos, "end", obj
    t = nb.PType
    if t == "Flange":
        faces = [p for p, _ in gp(nb) if p.distanceToPoint(port_pos) > 0.5]
        return (faces[0] if faces else port_pos), "face", nb
    if t in ("Elbow", "SocketEll"):
        wp = ell_wp(nb)
        if wp is not None:
            return wp, "CL", nb
    if t in ("Tee", "SocketTee"):
        return nb.Placement.Base, "CL", nb
    if t == "Outlet":
        run, a, axis = tdx._carrier_pipe(nb, members)
        if run is not None:
            return tdx._project_onto_axis(port_pos, a, axis), "run CL", run
    return port_pos, "weld", nb


def named_point(spec, M):
    kind, mark = spec
    o = M[mark]
    if kind == "face":
        return gp(o)[0][0], o                     # WN/blind: port 0 = raised face
    if kind == "wp":
        return (o.Placement.Base if o.PType in ("Tee", "SocketTee") else ell_wp(o)), o
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# Dimension planning, with lane packing so parallel dims never share a line
# ---------------------------------------------------------------------------

class Lanes(object):
    """First-fit interval packing: a dimension goes in the first lane where
    its span (plus `pad`) does not overlap one already there."""

    def __init__(self):
        self.lanes = []

    def put(self, lo, hi, pad):
        for i, occ in enumerate(self.lanes):
            if all(hi + pad < a or lo - pad > b for a, b in occ):
                occ.append((lo, hi))
                return i
        self.lanes.append([(lo, hi)])
        return len(self.lanes) - 1


def plan_view_dims(view, vkey, members, M, extra, done):
    """Dimensions this view can show TRUE: spans in its plane and parallel
    (to 0.999) to page-right or page-up.  At the 0.9 the TechDraw example uses,
    a DistanceX on a leg 25 deg off the axis would print the projection."""
    _, xa, ya = tdx.view_frame(view)
    d_axis = Vector(view.Direction); d_axis.normalize()
    centre = tdx.view_centre(view)
    hw, hh = tdx.view_extent(view)
    s = view.Scale
    below0 = -(hh * s + DIM_GAP + 12.0)           # room for the caption
    left0 = -(hw * s + DIM_GAP)
    right0 = hw * s + DIM_GAP
    xl, yl_l, yl_r = Lanes(), Lanes(), Lanes()
    wanted = []

    def add(label, p_a, c_a, p_b, c_b, force=None):
        span = p_b - p_a
        if span.Length < 5.0:
            return
        unit = Vector(span); unit.normalize()
        if force:
            kind = force
        elif abs(unit.dot(d_axis)) > 1e-3:
            return                                  # not in the view plane
        elif abs(unit.dot(xa)) > 0.999:
            kind = "DistanceX"
        elif abs(unit.dot(ya)) > 0.999:
            kind = "DistanceY"
        else:
            return
        axis = xa if kind == "DistanceX" else ya
        expected = abs(span.dot(axis))
        ua, va = tdx.view_uv(view, p_a, centre)
        ub, vb = tdx.view_uv(view, p_b, centre)
        key = ((kind, round(min(ua, ub)), round(max(ua, ub))) if kind == "DistanceX"
               else (kind, round(min(va, vb)), round(max(va, vb))))
        if key in done:                             # same span, another view
            return
        done.add(key)
        if kind == "DistanceX":
            lane = xl.put(min(ua, ub) * s, max(ua, ub) * s, 14.0)
            off = (0.5 * (ua + ub) * s, below0 - lane * DIM_STEP)
            side_axis, side = ya, -1
        else:
            right = (ua + ub) > 0                   # the side the feature is on
            lanes = yl_r if right else yl_l
            lane = lanes.put(min(va, vb) * s, max(va, vb) * s, 2.0)
            off = ((right0 + lane * Y_LANE_STEP) if right
                   else (left0 - lane * Y_LANE_STEP), 0.5 * (va + vb) * s)
            side_axis, side = xa, (1 if right else -1)
        a = tdx._anchor_to(p_a, c_a, side_axis, side)
        b = tdx._anchor_to(p_b, c_b, side_axis, side)
        wanted.append((kind, a, b, off, label, expected))

    for pipe in sorted([o for o in members if o.PType == "Pipe"],
                       key=lambda o: mark_sort_key(mark_of(o))):
        ports = gp(pipe)
        pa, ka, ca = wp_of(pipe, ports[0][0], members)
        pb, kb, cb = wp_of(pipe, ports[1][0], members)
        if "end" in (ka, kb):
            continue          # nipple to an off-spool part: a cut length (BOM)
        add("%s %s-%s" % (mark_of(pipe), ka, kb), pa, ca, pb, cb)
    for out in [o for o in members if o.PType == "Outlet"]:
        run, a, axis = tdx._carrier_pipe(out, members)
        if run is None:
            continue
        cross = tdx._project_onto_axis(gp(out)[0][0], a, axis)
        datum, _, dcomp = wp_of(run, gp(run)[0][0], members)
        add("%s CL" % mark_of(out), datum, dcomp, cross, run)
    for label, key, s1, s2, kind in extra:
        if key == vkey:
            p1, c1 = named_point(s1, M)
            p2, c2 = named_point(s2, M)
            add(label, p1, c1, p2, c2, force=kind)
    return wanted


# ---------------------------------------------------------------------------
# Flange-roll angle dimension (kicker details)
# ---------------------------------------------------------------------------

def add_roll_angle(doc, page, view, elbow, edir, L=190.0):
    """Angle dimension, on a from-above flange detail, between plant Y and
    the elbow's direction off the flange: the elbow roll a fitter sets.

    Three measured TechDraw 1.1 behaviours drive this (skill section 11.8):
      * projected edges (getVisibleEdges) come back Y-DOWN and SCALED, while
        makeCosmeticLine / makeCosmeticVertex points are drawn Y-UP and
        unscaled -- so the flange centre is the projected disc circle's
        centre, divided by the scale, with Y negated;
      * a small detail's origin is NOT TechDraw.findCentroid of its sources,
        so anchor on the projected geometry, not view_uv();
      * a two-edge 'Angle' dimension on cosmetic lines reads 0 or NaN; an
        'Angle3Pt' on three cosmetic vertices reads correctly -- and only
        while page.KeepUpdated is True.
    """
    sc = view.Scale
    circles = [e.Curve for e in view.getVisibleEdges() + view.getHiddenEdges()
               if e.Curve.__class__.__name__ == "Circle"]
    disc = max(circles, key=lambda c: c.Radius)
    cx, cy = disc.Center.x / sc, -disc.Center.y / sc
    _, xa, ya = tdx.view_frame(view)
    e2 = (edir.dot(xa), edir.dot(ya))
    yax = Vector(0, 1, 0) if Vector(0, 1, 0).dot(edir) >= 0 else Vector(0, -1, 0)
    y2 = (yax.dot(xa), yax.dot(ya))
    # reference lines: plant Y through the centre, elbow CL out along the elbow
    view.makeCosmeticLine(Vector(cx - L * y2[0], cy - L * y2[1], 0),
                          Vector(cx + L * y2[0], cy + L * y2[1], 0))
    view.makeCosmeticLine(Vector(cx, cy, 0), Vector(cx + L * e2[0], cy + L * e2[1], 0))
    r = 0.75 * L
    for pt in ((cx + r * e2[0], cy + r * e2[1]), (cx, cy),
               (cx + r * y2[0], cy + r * y2[1])):
        view.makeCosmeticVertex(Vector(pt[0], pt[1], 0))
    view.touch()
    doc.recompute()
    if _HAS_GUI:
        FreeCADGui.updateGui()
    nv = len(view.getVisibleVertexes()) + len(view.getHiddenVertexes())
    idx = [nv - 3, nv - 2, nv - 1]                  # end, apex, end
    prm = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
    was = prm.GetBool("AutoCorrectRefs")
    prm.SetBool("AutoCorrectRefs", False)
    try:
        d = doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        d.Type = "Angle3Pt"
        d.MeasureType = "Projected"
        d.References2D = [(view, tuple("Vertex%d" % i for i in idx))]
        page.addView(d)
        d.FormatSpec = "%.1f"                       # TechDraw appends the degree sign
        bis = (e2[0] + y2[0], e2[1] + y2[1])
        n = math.hypot(*bis)
        d.X, d.Y = (cx + 0.95 * L * bis[0] / n) * sc, (cy + 0.95 * L * bis[1] / n) * sc
        tag = elbow.Label.split("]")[0] + "]"
        d.Label = "Roll %s to plant %sY" % (tag, "+" if yax.y > 0 else "-")
        doc.recompute()
    finally:
        prm.SetBool("AutoCorrectRefs", was)
    for text, v2 in (("PLANT %sY" % ("+" if yax.y > 0 else "-"), y2),
                     ("ELBOW %s" % tag, e2)):
        a = doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        a.Label = "%s roll label" % TAG
        a.Text = [text]
        a.TextSize = 2.2
        page.addView(a)
        a.X = val(view.X) + (cx + 1.3 * L * v2[0]) * sc
        a.Y = val(view.Y) + (cy + 1.3 * L * v2[1]) * sc
    return d, math.degrees(edir.getAngle(yax))


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

def size_of(o):
    a = tdx._nps(o.PSize)
    b = getattr(o, "PSizeBranch", None) or getattr(o, "PSize2", None)
    return "%s x %s" % (a, tdx._nps(b)) if b and b != o.PSize else a


def describe(o):
    """Draft description from geometry; <...> is for the user to fill in."""
    t = o.PType
    if t == "Pipe":
        sched = "/".join(tdx._schedules_matching(o.PSize, val(o.OD), val(o.thk)))
        L = val(o.Height)
        if o.PSize in SMALL_BORE:
            std = [n for n in STD_NIPPLES_IN if abs(L - n * 25.4) < 0.01]
            if std:
                return "NIPPLE %g IN, %s, %s, <A106 GR B SMLS>" % (
                    std[0], "TOE" if "TOE" in o.Label else "PBE", sched)
            return "PIPE, PE, CUT TO LENGTH, %s, <A106 GR B SMLS>" % sched
        return "PIPE, BE, %s, <A106 GR B SMLS>" % sched
    if t == "Elbow":
        return "ELBOW 90 LR, BW, %s, <A234 WPB>" % "/".join(
            tdx._schedules_matching(o.PSize, val(o.OD), val(o.thk)))
    if t == "SocketEll":
        return "ELBOW 90, 3000# SW, <A105>"
    if t == "Tee":
        return "TEE, %sBW, SCH-STD, <A234 WPB>" % (
            "RED " if o.PSizeBranch != o.PSize else "")
    if t == "SocketTee":
        return "TEE, 3000# SW, <A105>"
    if t == "SocketUnion":
        return "UNION, 3000# SW, <A105>"
    if t == "Reduct":
        return "REDUCER, %s, BW, SCH-STD, <A234 WPB>" % ("CONC" if o.conc else "ECC")
    if t == "Flange":
        if o.FlangeType == "BL":
            return "BLIND FLANGE, %s RF, <A105>" % o.FClass.replace("lb", "#")
        return "FLANGE, WN %s RF, BORE %s, <A105>" % (
            o.FClass.replace("lb", "#"), o.PRating)
    if t == "Outlet":
        kind = ("SOCKOLET, 3000# SW" if o.EndType == "SW"
                else "WELDOLET, %s" % o.PRating.upper())
        return "%s, ON %s RUN, <A105>" % (kind, tdx._nps(tdx._carrier_dn(o)))
    if t == "Valve":
        if o.Conn in ("SW", "TH"):
            return "VALVE, BALL, %s, <800# / 3000#>" % (
                "SOCKET WELD" if o.Conn == "SW" else "THREADED")
        body = {"Ball_TrunnionRF": "BALL, TRUNNION, FULL PORT",
                "Ball_LongPatternRF": "BALL, LONG PATTERN"}.get(o.PRating, o.PRating)
        return "VALVE, %s, %s RF, %s" % (body, o.Conn.replace("lb", "#"),
                                          getattr(o, "Actuator", "").upper())
    if t == "Gasket":
        return "GASKET, %s RF, <SPIRAL WOUND>" % o.FClass.replace("lb", "#")
    if t == "Bolts_Nuts":
        return "STUD BOLTS W/ 2 NUTS, %d REQ'D, <A193 B7 / A194 2H>" % int(o.n)
    return "%s, <describe>" % t.upper()


def write_bom(doc, page, sp, M, top):
    """One row per model mark: welded first, then assembly material.

    DrawViewSpreadsheet: X/Y is the CENTRE of the table; row height and
    column width come from the sheet in px (0.2646 mm each), and the default
    30 px row is ~8 mm tall -- set it, or a 30-row BOM runs off the sheet."""
    sheet = doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
    sheet.Label = "%s BOM %s" % (TAG, sp["no"])
    for col, head in zip("ABCD", ("MARK", "QTY", "SIZE", "DESCRIPTION")):
        tdx._text(sheet, "%s1" % col, head)
    r, rows = 2, []
    for group, title in ((sp["welded"], None), (sp["assembly"], "ASSEMBLY MATERIALS")):
        if title:
            r += 1
            tdx._text(sheet, "D%d" % r, title)
            r += 1
        for m in sorted(group, key=mark_sort_key):
            o = M[m]
            qty = ftin(val(o.Height)) if o.PType == "Pipe" else "1"
            row = (m, qty, size_of(o), describe(o))
            for col, v in zip("ABCD", row):
                tdx._text(sheet, "%s%d" % (col, r), v)
            rows.append(row + (title is None,))
            r += 1
    for col, w in zip("ABCD", (40, 66, 60, 322)):
        sheet.setColumnWidth(col, w)
    for i in range(1, r):
        sheet.setRowHeight(str(i), BOM_ROW_PX)
    doc.recompute()
    view = doc.addObject("TechDraw::DrawViewSpreadsheet", "Sheet")
    view.Label = "%s BOM view %s" % (TAG, sp["no"])
    view.Source = sheet
    view.CellStart, view.CellEnd = "A1", "D%d" % (r - 1)
    view.TextSize = BOM_TEXT
    page.addView(view)
    height = (r - 1) * BOM_ROW_PX * PX_MM
    view.X, view.Y = top[0], top[1] - height / 2.0
    return sheet, view, rows, top[1] - height


def write_notes(doc, page, sp, bottom_of_bom):
    lines = (["NOTES:",
              "1. DIMENSIONS IN FT-IN, ROUNDED TO THE NEAREST 1/16 IN, TO WORK",
              "   POINTS: FLANGE FACES AND FITTING CENTERLINES. PIPE CUT LENGTHS",
              "   PER BOM. ANGLES IN DECIMAL DEGREES.",
              "2. <MATERIAL GRADES> ARE PLACEHOLDERS - CONFIRM BEFORE ISSUE.",
              "3. FLANGES ASME B16.5 600# RF; SMALL BORE 3000# SW."] +
             ["%d. %s" % (i + 4, n) for i, n in enumerate(sp["notes"])])
    for j, (mk, r) in enumerate(sp.get("roll", [])):
        lines += [
            "%d. FLANGE ROLL [%s]: %d HOLES 2-HOLED TO PLANT AXES, MATCHING ITS MATE."
            % (4 + len(sp["notes"]) + j, mk, r["n"]),
            "   VIEWED FROM ABOVE, PATTERN IS %.1f DEG %s OF 2-HOLE ON THE SPOOL CL;"
            % (abs(r["from_2hole"]), "CCW" if r["from_2hole"] > 0 else "CW"),
            "   NEAREST HOLE %.1f DEG %s OF THE SPOOL CL."
            % (abs(r["nearest"]), "CCW" if r["nearest"] > 0 else "CW")]
    # DrawViewAnnotation does not wrap, and its X/Y is the CENTRE of the block.
    wrapped = []
    for line in lines:
        wrapped += textwrap.wrap(line.strip(), NOTE_WRAP,
                                 initial_indent="   " if line.startswith(" ") else "",
                                 subsequent_indent="   ") or [""]
    notes = doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
    notes.Label = "%s notes %s" % (TAG, sp["no"])
    notes.Text = wrapped
    notes.TextSize = NOTE_TEXT
    page.addView(notes)
    notes.X = RIGHT_COL[0]
    notes.Y = bottom_of_bom - 5.0 - len(wrapped) * NOTE_LINE_MM / 2.0
    return notes


# ---------------------------------------------------------------------------
# Balloon placement fixes on top of tdx.add_balloons
# ---------------------------------------------------------------------------

def respace_if_crowded(view, balloons, min_mm=12.0):
    """tdx.add_balloons spaces bubbles by angle, but its push-apart can wrap
    past +/-pi and land a bubble on another.  If any two are closer than
    min_mm, re-space all of them evenly round a wider ring, keeping their
    order and leaving the caption sector clear.  Leaders stay on the parts."""
    s = view.Scale
    pts = [(val(b.X) * s, val(b.Y) * s) for b in balloons]
    if not any(math.hypot(a[0] - c[0], a[1] - c[1]) < min_mm
               for i, a in enumerate(pts) for c in pts[i + 1:]):
        return False
    hw, hh = tdx.view_extent(view)
    gap = (tdx.BALLOON_GAP + 8.0) / s
    ru, rv = hw + gap, hh + gap
    order = sorted(balloons, key=lambda b: (math.atan2(val(b.Y) / rv, val(b.X) / ru)
                                            + math.pi / 2) % (2 * math.pi))
    skip, n = 0.45, len(order)                      # rad either side of straight down
    span = 2 * math.pi - 2 * skip
    for i, b in enumerate(order):
        a = -math.pi / 2 + skip + span * (i + 0.5) / n
        b.X, b.Y = math.cos(a) * ru, math.sin(a) * rv
    return True


def clear_caption(view, balloons, char_mm=2.9, bubble_mm=7.0):
    """Push a bubble that lands on the view's caption out sideways.  The
    caption prints centred just below the projected outline (skill section 8)."""
    s = view.Scale
    _, hh = tdx.view_extent(view)
    half_w = len(view.Caption) * char_mm / 2.0
    cy = -(hh * s + 7.0)
    for b in balloons:
        bx, by = val(b.X) * s, val(b.Y) * s
        if abs(by - cy) < 4.0 + bubble_mm and abs(bx) < half_w + bubble_mm:
            b.X = (1 if bx >= 0 else -1) * (half_w + bubble_mm + 2.0) / s


# ---------------------------------------------------------------------------
# Teardown, projection, pages
# ---------------------------------------------------------------------------

_WINDOWS = []      # page windows THIS macro opened (never close by title)


def teardown(doc):
    """Remove every page, BOM, annotation and container -- never geometry.
    Containers are emptied first, or they take their children with them."""
    for sub in _WINDOWS:
        try:
            sub.close()
        except RuntimeError:
            pass
    del _WINDOWS[:]
    for p in [o for o in doc.Objects if o.TypeId == "TechDraw::DrawPage"]:
        p.KeepUpdated = False
    for tid in tdx._DRAWING_TYPES:
        for o in [o for o in doc.Objects if o.TypeId == tid]:
            doc.removeObject(o.Name)
    for part in [o for o in doc.Objects if o.TypeId == "App::Part"]:
        part.Group = []
        doc.removeObject(part.Name)
    for tid in ("App::Origin", "App::Line", "App::Plane", "App::Point"):
        for o in [o for o in doc.Objects if o.TypeId == tid]:
            doc.removeObject(o.Name)
    doc.recompute()


def project_wait(doc, page, views, timeout=90.0):
    """tdx.project_views with a time budget.  Its ten quick passes were not
    enough here: two views with 4-8 in flanges took several seconds, and the
    macro then refused views that were in fact about to project."""
    page.KeepUpdated = True
    for v in views:
        v.touch()
    doc.recompute()
    t0 = time.time()
    while time.time() - t0 < timeout:
        if all(len(v.getVisibleEdges()) for v in views):
            break
        if _HAS_GUI:
            FreeCADGui.updateGui()
        time.sleep(0.2)
        doc.recompute()
    empty = [v.Name for v in views if not len(v.getVisibleEdges())]
    if empty:
        raise RuntimeError("views %s never projected" % empty)
    return {v.Name: len(v.getVisibleEdges()) for v in views}


def fit_scale(shape, views):
    """Largest nice scale at which every listed view fits its own box."""
    for s in tdx.NICE_SCALES:
        if all(2 * hw * s <= box[0] and 2 * hh * s <= box[1]
               for hw, hh, box in
               [tdx._extent(shape, Vector(*d), Vector(*x)) + (box,)
                for _, _, d, x, _, box in views]):
            return s
    return tdx.NICE_SCALES[-1]


def add_detail(doc, page, sp, key, cap, marks, d, x, pos, M, box=(62, 50)):
    srcs = [M[m] for m in marks]
    hw, hh = tdx._extent(Part.makeCompound([o.Shape for o in srcs]),
                         Vector(*d), Vector(*x))
    sc = next((s for s in tdx.NICE_SCALES
               if 2 * hw * s <= box[0] and 2 * hh * s <= box[1]), tdx.NICE_SCALES[-1])
    v = doc.addObject("TechDraw::DrawProjGroupItem", "View")
    v.Source = srcs                         # objects inside a container are fine
    v.Type = "Front"
    v.Direction, v.XDirection = Vector(*d), Vector(*x)
    v.ScaleType = "Custom"
    v.Scale = sc
    v.HardHidden = True                     # the elbow sits over the bolt holes
    v.Caption = "%s 1:%g" % (cap, round(1.0 / sc, 3))
    page.addView(v)
    v.X, v.Y = pos
    v.Label = "%s %s %s" % (TAG, sp["no"], key)
    return v


def build_one(doc, sp, M):
    members = [M[m] for m in sp["welded"]]
    part = doc.addObject("App::Part", "Part")
    part.Label = "%s %s %s" % (TAG, sp["no"], sp["title2"])
    part.Group = members                    # an object can be in ONE container
    doc.recompute()

    page = doc.addObject("TechDraw::DrawPage", "Page")
    page.Label = "%s %s" % (sp["no"], sp["title2"])
    tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    tmpl.Template = os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                                 "Templates", "ASME", "ANSIB_Landscape.svg")
    page.Template = tmpl

    # One scale for the dimensioned views (the title block states it).  The
    # isometric carries no dimensions, so it gets its own, in its caption.
    shape = Part.makeCompound([o.Shape for o in members])
    scale = fit_scale(shape, [v for v in sp["views"] if v[0] != "iso"])
    iso_scale = fit_scale(shape, [v for v in sp["views"] if v[0] == "iso"])
    views = {}
    for key, cap, d, x, pos, _ in sp["views"]:
        sc = iso_scale if key == "iso" else scale
        if key == "iso":
            cap = "%s 1:%g" % (cap, round(1.0 / sc, 3))
        v = tdx.add_view(doc, page, part, cap, d, x, sc, pos)
        v.Label = "%s %s %s" % (TAG, sp["no"], key)
        views[key] = v
    details = {key: add_detail(doc, page, sp, key, cap, marks, d, x, pos, M)
               for key, cap, marks, d, x, pos in sp.get("details", [])}
    edges = project_wait(doc, page, list(views.values()) + list(details.values()))

    # Everything that reads projected geometry, while KeepUpdated is True.
    dims, done = [], set()
    for key, v in views.items():
        if key != "iso":
            dims += tdx.attach_dimensions(
                doc, page, v, plan_view_dims(v, key, members, M, sp["extra"], done))
    for d, _ in dims:
        d.Arbitrary = True                  # print FormatSpec verbatim
        d.FormatSpec = ftin(d.getRawValue())
    roll_dims = [add_roll_angle(doc, page, details[dk], M[em], edir)
                 for dk, _, em, edir in sp.get("roll_dims", [])]

    sheet, sview, rows, bom_bottom = write_bom(doc, page, sp, M, RIGHT_COL)
    balloons = tdx.add_balloons(doc, page, views["iso"], members,
                                {o.Name: mark_of(o) for o in members})
    respace_if_crowded(views["iso"], balloons)
    clear_caption(views["iso"], balloons)
    notes = write_notes(doc, page, sp, bom_bottom)

    # ASME ANSIB_Landscape.svg in FreeCAD 1.1: the scale field is 'scale'
    # (lower case); there is no 'Scale' key.  Assign a NEW dict.
    t = dict(tmpl.EditableTexts)
    t.update({"DrawingTitle1": 'PIG LAUNCHER 6" x 8" 600#',
              "DrawingTitle2": sp["title2"],
              "DrawingTitle3": os.path.basename(MODEL),
              "drawing_number": sp["no"], "revision_index": "A",
              "scale": "1:%g" % round(1.0 / scale, 4), "Sheet": sp["sheet"],
              "CompanyName": "<COMPANY>", "CompanyAddress": "",
              "DrawnBy": "CLAUDE (AI)", "CheckedBy": "", "Approved1": "",
              "Approved2": "", "Code": "", "Weight": ""})
    tmpl.EditableTexts = t
    doc.recompute()
    return dict(page=page, tmpl=tmpl, part=part, views=views, details=details,
                dims=dims, roll_dims=roll_dims, balloons=balloons, rows=rows,
                sheet=sheet, sview=sview, notes=notes, scale=scale, edges=edges)


def show(page):
    """Open one window on the page and paint it, before KeepUpdated=False."""
    if not _HAS_GUI:
        return None
    from PySide import QtGui
    mdi = FreeCADGui.getMainWindow().findChild(QtGui.QMdiArea)
    before = set(mdi.subWindowList())
    page.ViewObject.doubleClicked()
    FreeCADGui.updateGui()
    new = [s for s in mdi.subWindowList() if s not in before]
    if new:
        _WINDOWS.append(new[-1])
    page.requestPaint()
    FreeCADGui.updateGui()
    return new[-1] if new else None


def find_model():
    """The launcher model: already open (by file), else opened from disk.
    It is this repo's generated file, never a user's own model."""
    for d in FreeCAD.listDocuments().values():
        if os.path.normcase(os.path.abspath(d.FileName or "")) == os.path.normcase(MODEL):
            return d
    if not os.path.isfile(MODEL):
        raise RuntimeError("%s not found -- run make_pig_launcher.py first" % MODEL)
    return FreeCAD.openDocument(MODEL)


def build_all(doc=None):
    doc = doc or find_model()
    FreeCAD.setActiveDocument(doc.Name)
    if _HAS_GUI:
        FreeCADGui.setActiveDocument(doc.Name)
    teardown(doc)
    M = objs_by_mark(doc)
    out = {}
    for sp in spool_defs(M):
        out[sp["key"]] = r = build_one(doc, sp, M)
        r["win"] = show(r["page"])
        r["page"].KeepUpdated = False       # leave it off: the user re-enables
    return doc, M, out


# ---------------------------------------------------------------------------
# Verification (skill section 14)
# ---------------------------------------------------------------------------

def report(doc, out):
    lines = ["", "=== Pig launcher drawings on %s ===" % doc.Label]
    bad = 0
    for key, r in out.items():
        tmpl = r["tmpl"]
        lines.append("  %s  %s  sheet %s  scale %s  (template %s, %.1f x %.1f mm)"
                     % (tmpl.EditableTexts["drawing_number"], r["page"].Label,
                        tmpl.EditableTexts["Sheet"], tmpl.EditableTexts["scale"],
                        os.path.basename(tmpl.Template), val(tmpl.Width), val(tmpl.Height)))
        wrong = [o.Label for o in r["part"].Group
                 if o.PType in ("Gasket", "Bolts_Nuts")
                 or (o.PType == "Valve" and getattr(o, "Conn", "") != "SW")]
        bad += bool(wrong)
        lines.append("    container %d parts; bolted material inside: %s"
                     % (len(r["part"].Group), wrong or "none"))
        allv = list(r["views"].values()) + list(r["details"].values())
        empty = [v.Caption for v in allv if not len(v.getVisibleEdges())]
        bad += len(empty)
        lines.append("    views: %s%s" % (", ".join("%s (%d edges)" % (v.Caption, len(v.getVisibleEdges()))
                                                  for v in allv),
                                       ("  EMPTY: %s" % empty) if empty else ""))
        for d, e in r["dims"]:
            ok = abs(d.getRawValue() - e) < 0.05 and d.FormatSpec == ftin(e)
            bad += not ok
            lines.append("    %s %-20s %-9s %9.2f mm (model %9.2f)  prints %s"
                         % ("OK " if ok else "BAD", d.Label, d.Type, d.getRawValue(), e,
                            d.FormatSpec))
        for d, e in r["roll_dims"]:
            ok = abs(d.getRawValue() - e) < 0.05
            bad += not ok
            lines.append("    %s %-28s %7.3f deg (model %.3f)"
                         % ("OK " if ok else "BAD", d.Label, d.getRawValue(), e))
        iso = r["views"]["iso"]
        s = iso.Scale
        off = [b.Text for b in r["balloons"]
               if not (BORDER[0] <= val(iso.X) + val(b.X) * s <= BORDER[1]
                       and BORDER[2] <= val(iso.Y) + val(b.Y) * s <= BORDER[3])]
        pts = [(val(b.X) * s, val(b.Y) * s) for b in r["balloons"]]
        mind = min(math.hypot(a[0] - c[0], a[1] - c[1])
                   for i, a in enumerate(pts) for c in pts[i + 1:])
        welded = set(mark_of(o) for o in r["part"].Group)
        missing = sorted(welded - set(b.Text for b in r["balloons"]))
        bad += len(off) + len(missing)
        lines.append("    balloons %d, min spacing %.1f mm, outside border: %s, "
                     "welded marks with no balloon: %s"
                     % (len(r["balloons"]), mind, off or "none", missing or "none"))
        asm = [row[0] for row in r["rows"] if not row[4]]
        lines.append("    BOM %d welded + %d assembly (no balloon: not drawn) %s"
                     % (len(r["rows"]) - len(asm), len(asm), asm))
    lines.append("  Dimension text is ft-in to 1/%d in (fixed text; re-run to update)."
                 % FRAC_DEN)
    lines.append("  %s" % ("ALL CHECKS PASSED" if not bad else "%d CHECK(S) FAILED" % bad))
    FreeCAD.Console.PrintMessage("\n".join(lines) + "\n")
    if bad:
        raise RuntimeError("%d drawing check(s) failed -- see the report" % bad)


def main():
    doc, M, out = build_all()
    report(doc, out)
    doc.save()
    FreeCAD.Console.PrintMessage("  Saved: %s\n" % doc.FileName)
    return doc


if __name__ == "__main__":
    main()
