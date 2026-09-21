# -*- coding: utf-8 -*-
"""
6x8 launcher — 2" drain line
============================

Modifies ``6x8_launcher.FCStd``:

  * deletes the DN50 600# **blind** flange ``Flange013`` that currently blanks
    the outboard face of the drain ball valve ``Valve006``;
  * builds the 2" Sch-80 drain run drawn in ``Piping_sketch.png`` in its place.

Route (world axes of the launcher model; the drain branch leaves the header
along -X, the headers themselves run along Y, +Z is up):

    Valve006 face / Gasket010
      -> SO flange 600#  (bolts to the existing gasket + stud set)
      -> 6" pipe, -X
      -> SW 90 ell  ..... turn down
      -> vertical drop to grade
      -> SW 90 ell  ..... turn -X
      -> 6'-0" leg, -X
      -> SW 90 ell  ..... turn +Y
      -> 20'-0" leg, +Y: 6" pipe, a 2" SW union, then the remainder
      -> SW 90 ell  ..... turn up
      -> 6'-0" rise
      -> SW 90 ell  ..... turn +Y
      -> 12" pipe, +Y
      -> SO flange 600#  (open face, no gasket/bolts)

Line spec (``Pipe_specs.md``): 2" NPS = **DN50**, **Sch-80** pipe,
**600#** slip-on RF flanges, **3000lb socket-weld** elbows and union.

RUN IT FROM THE FreeCAD GUI (Macro -> Execute, or paste into the Python
console).  Quetzal's execute() methods write to ``ViewObject``, so the makers
only build geometry when a GUI ViewObject exists.

Nothing is saved (``Pipe_specs.md``: Save = no).  Save-As the document to
``6x8_launcher_drain.FCStd`` yourself if you want to keep the result.
"""

import os
import sys
import math

import FreeCAD
from FreeCAD import Vector

try:
    import FreeCADGui
    _HAS_GUI = True
except Exception:
    _HAS_GUI = False


# ---------------------------------------------------------------------------
# DIMENSIONS — every number taken off Piping_sketch.png lives here.
# ---------------------------------------------------------------------------

IN = 25.4                      # mm per inch
FT = 304.8                     # mm per foot

DN = "DN50"                    # 2" NPS
SCHED = "SCH-80"               # pipe schedule            -> Pipe_SCH-80.csv
FIT_RATING = "3000lb"          # socket-weld fitting class-> Elbow/Union_3000lb_SW.csv
FCLASS = "600lb"               # flange class             -> Flange_ASME-SO-RF-600lb.csv
NORATE = "No rating"           # PRating for a non-WN flange (the guide §4)

# --- cut pipe lengths called out on the sketch ------------------------------
L_STUB_VALVE = 6.0 * IN        # "SO flange, 6" length of 2" pipe, then SW 90 ell"
L_STUB_END = 12.0 * IN         # "SO flange, 12" length of 2" pipe, then SW 90 elbow"

# --- leg dimensions ---------------------------------------------------------
# The two ground legs are dimensioned to the OTHER leg's centreline at one end
# and to a face at the other, NOT elbow work point to elbow work point; the
# build derives the work-point spacing from these and checks it back.
L_LEG_X = 6.0 * FT             # 6'-0": gasket mating face -> centreline of the
#                                +Y (20'-0") run, measured along -X
L_LEG_Y = 20.0 * FT            # 20'-0": centreline of the -X (6'-0") run ->
#                                raised face of the open end flange, along +Y
L_RISE = 6.0 * FT              # 6'-0" rise at the far end, elbow WP -> elbow WP

# --- route directions (world unit vectors) ----------------------------------
DIR_STUB = Vector(-1, 0, 0)    # off the valve, away from the header
DIR_DOWN = Vector(0, 0, -1)    # drop to grade
DIR_LEG_X = Vector(-1, 0, 0)   # 6'-0" ground leg
DIR_LEG_Y = Vector(0, 1, 0)    # 20'-0" ground leg
DIR_UP = Vector(0, 0, 1)       # rise
DIR_END = Vector(0, 1, 0)      # final short leg into the open SO flange

# --- elevation --------------------------------------------------------------
# "Bottom of pipe run on ground (0' elevation relative to pipe support bottom)":
# the ground run's pipe OUTSIDE bottom sits at the bottom of the support posts.
SUPPORT_BOTTOM_Z = -826.7      # verified below against the support post Tube019
SUPPORT_POST = "Tube019"

# Where the union sits in the 20'-0" ground leg: a 6" pipe segment runs +Y off
# the X-Y plane elbow, then the union, then the remainder of the leg.
L_UNION_LEAD = 6.0 * IN

# --- the part we replace ----------------------------------------------------
BLIND_TO_DELETE = "Flange013"  # DN50 600# BL blanking the drain valve
MATE_GASKET = "Gasket010"      # its gasket; the new SO flange bolts to this
DOC_NAME = "6x8_launcher"
NEW_PART_LABEL = "DrainLine"

MIN_PIPE_ABS = 50.0            # the guide §9.2.2 short-pipe rule


# ---------------------------------------------------------------------------
# Quetzal / table plumbing
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

import quetzal_env as qenv  # noqa: E402

pCmd = qenv.import_pcmd()

# `fieldnames` handles the header-less tables (Union_3000lb_SW.csv); extra
# kwargs are additional exact-match column filters (e.g. BendAngle).
_read_row = qenv.read_row
_f = qenv.f                 # float from a CSV row, by column name


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def rot_two(a0, a1, b0, b1):
    """Rotation R with R*a0 == b0 and R*a1 == b1 (the guide §9.3)."""
    def frame(u, v):
        x = Vector(u)
        x.normalize()
        z = x.cross(Vector(v))
        z.normalize()
        return FreeCAD.Rotation(x, z.cross(x), z)
    return frame(b0, b1).multiply(frame(a0, a1).inverted())


def world_port(obj, i):
    return obj.Placement.multVec(obj.Ports[i])


def world_dir(obj, i):
    return obj.Placement.Rotation.multVec(obj.PortDirections[i])


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    report = []
    checks = []
    adjust = []

    def say(line=""):
        report.append(line)

    # -- the document -------------------------------------------------------
    doc = None
    for d in FreeCAD.listDocuments().values():
        if d.Name == DOC_NAME or d.Label == DOC_NAME:
            doc = d
            break
    if doc is None:
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                DOC_NAME + ".FCStd")
        except NameError:
            path = None
        if path and os.path.isfile(path):
            doc = FreeCAD.openDocument(path)
        else:
            raise RuntimeError(
                "Open %s.FCStd before running this macro." % DOC_NAME)
    FreeCAD.setActiveDocument(doc.Name)
    FreeCAD.ActiveDocument = doc

    gasket = doc.getObject(MATE_GASKET)
    if gasket is None:
        raise RuntimeError("%s not found in %s" % (MATE_GASKET, doc.Name))

    # -- delete the blind flange -------------------------------------------
    blind = doc.getObject(BLIND_TO_DELETE)
    if blind is None:
        say("NOTE: %s not present (already deleted?) - continuing."
            % BLIND_TO_DELETE)
    else:
        say("Deleted %s  (%s %s %s blind flange)"
            % (blind.Name, blind.Label, blind.PSize, blind.FClass))
        doc.removeObject(blind.Name)
    doc.recompute()

    # -- table rows ---------------------------------------------------------
    pipe_row = _read_row("Pipe_%s.csv" % SCHED, DN)
    OD = _f(pipe_row, "OD")
    THK = _f(pipe_row, "thk")

    ell_row = _read_row("Elbow_%s_SW.csv" % FIT_RATING, DN, BendAngle="90")
    ELL = [DN, _f(ell_row, "OD"), _f(ell_row, "BendAngle"), _f(ell_row, "A"),
           _f(ell_row, "C"), _f(ell_row, "D"), _f(ell_row, "E"),
           _f(ell_row, "G"), ell_row.get("Conn", "SW").strip()]
    E_ELL = ELL[6]                      # elbow work point -> socket base (take-out)

    uni_row = _read_row(
        "Union_%s_SW.csv" % FIT_RATING, DN,
        fieldnames=["PSize", "OD", "A", "C", "D", "E", "Conn"])  # no header row
    UNI = [DN, _f(uni_row, "OD"), _f(uni_row, "A"), _f(uni_row, "C"),
           _f(uni_row, "D"), _f(uni_row, "E"), uni_row.get("Conn", "SW").strip()]
    E_UNI = UNI[2] - UNI[5]             # union centre -> port  (= A - E)

    flg_row = _read_row("Flange_ASME-SO-RF-%s.csv" % FCLASS, DN)
    #                DN  type  D   d   df  f   t   n   trf drf twn dwn ODp R  T1 B2 Y
    FLG = [DN, "SO", _f(flg_row, "D"), _f(flg_row, "d"), _f(flg_row, "df"),
           _f(flg_row, "f"), _f(flg_row, "t"), int(_f(flg_row, "n")),
           _f(flg_row, "trf"), _f(flg_row, "drf"), _f(flg_row, "twn", 0.0),
           _f(flg_row, "dwn", 0.0), _f(flg_row, "ODp", 0.0),
           _f(flg_row, "R", 0.0), _f(flg_row, "T1", 0.0),
           _f(flg_row, "B2", 0.0), _f(flg_row, "Y", 0.0)]

    # -- grade / centreline elevation --------------------------------------
    post = doc.getObject(SUPPORT_POST)
    ground_z = SUPPORT_BOTTOM_Z
    if post is not None and hasattr(post, "Height"):
        derived = post.Placement.multVec(Vector(0, 0, float(post.Height))).z
        checks.append(("support-post bottom (%s)" % SUPPORT_POST,
                       derived, SUPPORT_BOTTOM_Z))
        ground_z = derived
    cl_z = ground_z + OD / 2.0          # bottom of pipe on grade -> centreline

    # -- object factory helpers --------------------------------------------
    made = []

    def keep(obj, label):
        obj.Label = label
        made.append(obj)
        return obj

    pipes = []

    def mk_pipe(length, label):
        lim = min(MIN_PIPE_ABS, OD / 2.0)
        if length < lim:
            adjust.append((label, length, lim))
        p = pCmd.makePipe(SCHED, [DN, OD, THK, length])
        p.PRating = SCHED
        doc.recompute()
        pipes.append((label, length))
        return keep(p, label)

    def mk_ell(label):
        e = pCmd.makeSocketElbow(ELL, rating=FIT_RATING)
        e.PRating = FIT_RATING
        doc.recompute()
        return keep(e, label)

    def place_ell(ell, wp, inlet_dir, outlet_dir):
        """Anchor a SW 90 ell: work point at `wp`, port0 outward along
        `inlet_dir` (back up the run), port1 outward along `outlet_dir`."""
        bend = math.radians(180.0 - ELL[2])
        got = inlet_dir.getAngle(outlet_dir)
        assert abs(got - bend) < 1e-6, (
            "%s: legs %.1f deg apart, a %.0f deg ell needs %.1f"
            % (ell.Label, math.degrees(got), ELL[2], math.degrees(bend)))
        d0, d1 = ell.PortDirections[0], ell.PortDirections[1]
        R = rot_two(d0, d1, inlet_dir, outlet_dir)
        # SocketEll's work point is its local origin (both port centrelines
        # pass through it), so the base goes straight onto the work point.
        ell.Placement = FreeCAD.Placement(wp, R)
        doc.recompute()

    def gap(objA, portA, objB, portB):
        return (world_port(objA, portA) - world_port(objB, portB)).Length

    # -- 1. SO flange onto the existing gasket / stud set -------------------
    fA = pCmd.makeFlange(FLG, doOffset=True, rating=NORATE, fclass=FCLASS)
    doc.recompute()
    pCmd.alignTwoPorts(fA, 0, gasket, 1)
    doc.recompute()
    keep(fA, 'Flange DN50 600# SO RF - drain, at Valve006 (replaces %s)'
         % BLIND_TO_DELETE)
    gasket_face = world_port(fA, 0)     # datum for the 6'-0" dimension
    TRF = FLG[8]

    # -- 2. 6" stub -> ell 1 (turn down) ------------------------------------
    p1 = mk_pipe(L_STUB_VALVE, 'Pipe DN50 SCH-80 - 6" stub off valve flange')
    pCmd.alignTwoPorts(p1, 0, fA, 1)
    doc.recompute()

    wp1 = world_port(p1, 1) + DIR_STUB * E_ELL
    e1 = mk_ell("SocketEll DN50 3000lb 90 SW - [1] turn down")
    place_ell(e1, wp1, -DIR_STUB, DIR_DOWN)
    checks.append(("ell 1 socket vs stub end", gap(e1, 0, p1, 1), 0.0))

    # -- 3. drop to grade -> ell 2 (turn -X) --------------------------------
    wp2 = Vector(wp1.x, wp1.y, cl_z)
    drop = (wp1 - wp2).Length
    p2 = mk_pipe(drop - 2 * E_ELL, "Pipe DN50 SCH-80 - drop to grade")
    pCmd.alignTwoPorts(p2, 0, e1, 1)
    doc.recompute()

    e2 = mk_ell("SocketEll DN50 3000lb 90 SW - [2] grade, turn -X")
    place_ell(e2, wp2, -DIR_DOWN, DIR_LEG_X)
    checks.append(("ell 2 socket vs drop end", gap(e2, 0, p2, 1), 0.0))

    # -- 4. 6'-0" ground leg -> ell 3 (turn +Y) -----------------------------
    # 6'-0" runs from the gasket face, not from ell 2, so back the already-used
    # part of it out of the work-point spacing.
    run_x = L_LEG_X - (wp2 - gasket_face).dot(DIR_LEG_X)
    wp3 = wp2 + DIR_LEG_X * run_x
    p3 = mk_pipe(run_x - 2 * E_ELL, "Pipe DN50 SCH-80 - 6'-0\" ground leg")
    pCmd.alignTwoPorts(p3, 0, e2, 1)
    doc.recompute()

    e3 = mk_ell("SocketEll DN50 3000lb 90 SW - [3] grade, turn +Y")
    place_ell(e3, wp3, -DIR_LEG_X, DIR_LEG_Y)
    checks.append(("ell 3 socket vs 6'-0\" leg end", gap(e3, 0, p3, 1), 0.0))

    # -- 5. 20'-0" ground leg: 6" pipe, union, remainder -> ell 4 (turn up) -
    # 20'-0" runs on past ell 4 to the open flange FACE: rise take-out, 12"
    # stub and the flange's own 2*trf all come out of the work-point spacing.
    tail_y = E_ELL + L_STUB_END + 2 * TRF
    run_y = L_LEG_Y - tail_y
    wp4 = wp3 + DIR_LEG_Y * run_y
    leg_y_pipe = run_y - 2 * E_ELL - 2 * E_UNI        # union eats 2*(A-E)
    la = L_UNION_LEAD
    lb = leg_y_pipe - la

    p4a = mk_pipe(la, "Pipe DN50 SCH-80 - 20'-0\" leg, 6\" ell 3 -> union")
    pCmd.alignTwoPorts(p4a, 0, e3, 1)
    doc.recompute()

    uni = pCmd.makeSocketUnion(UNI)
    uni.PRating = FIT_RATING
    doc.recompute()
    pCmd.alignTwoPorts(uni, 0, p4a, 1)
    doc.recompute()
    keep(uni, 'SocketUnion DN50 3000lb SW - 2" union')

    p4b = mk_pipe(lb, "Pipe DN50 SCH-80 - 20'-0\" leg, union -> ell 4")
    pCmd.alignTwoPorts(p4b, 0, uni, 1)
    doc.recompute()

    e4 = mk_ell("SocketEll DN50 3000lb 90 SW - [4] turn up")
    place_ell(e4, wp4, -DIR_LEG_Y, DIR_UP)
    checks.append(("ell 4 socket vs 20'-0\" leg end", gap(e4, 0, p4b, 1), 0.0))

    # -- 6. 6'-0" rise -> ell 5 (turn +Y) -----------------------------------
    wp5 = wp4 + DIR_UP * L_RISE
    p5 = mk_pipe(L_RISE - 2 * E_ELL, "Pipe DN50 SCH-80 - 6'-0\" rise")
    pCmd.alignTwoPorts(p5, 0, e4, 1)
    doc.recompute()

    e5 = mk_ell("SocketEll DN50 3000lb 90 SW - [5] top of rise, turn +Y")
    place_ell(e5, wp5, -DIR_UP, DIR_END)
    checks.append(("ell 5 socket vs rise end", gap(e5, 0, p5, 1), 0.0))

    # -- 7. 12" stub -> open SO flange --------------------------------------
    p6 = mk_pipe(L_STUB_END, 'Pipe DN50 SCH-80 - 12" stub to end flange')
    pCmd.alignTwoPorts(p6, 0, e5, 1)
    doc.recompute()

    fB = pCmd.makeFlange(FLG, doOffset=True, rating=NORATE, fclass=FCLASS)
    doc.recompute()
    pCmd.alignTwoPorts(fB, 1, p6, 1)
    doc.recompute()
    keep(fB, "Flange DN50 600# SO RF - drain, open end (bare face)")

    # closure of the two dimensions as the sketch datums them
    checks.append(("6'-0\" gasket face -> +Y run centreline",
                   (wp3 - gasket_face).dot(DIR_LEG_X), L_LEG_X))
    checks.append(("20'-0\" -X run centreline -> open flange face",
                   (world_port(fB, 0) - wp3).dot(DIR_LEG_Y), L_LEG_Y))

    # -- group it -----------------------------------------------------------
    grp = doc.addObject("App::Part", "DrainLine")
    grp.Label = NEW_PART_LABEL
    for o in made:
        grp.addObject(o)
    doc.recompute()

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    say()
    say("=" * 74)
    say('6x8 launcher - 2" Sch-80 drain line   (document: %s)' % doc.Name)
    say("=" * 74)
    say("Line spec : %s, %s pipe, %s SW fittings, %s SO RF flanges"
        % (DN, SCHED, FIT_RATING, FCLASS))
    say("Tables    : Pipe_%s.csv / Elbow_%s_SW.csv / Union_%s_SW.csv / "
        "Flange_ASME-SO-RF-%s.csv" % (SCHED, FIT_RATING, FIT_RATING, FCLASS))
    say("Pipe      : OD %.2f  thk %.2f  ID %.2f" % (OD, THK, OD - 2 * THK))
    say("Take-outs read from tablez/:")
    say("   SW 90 ell  A=%.2f  E(work point->socket base)=%.2f" % (ELL[3], E_ELL))
    say("   SW union   A=%.2f  E=%.2f  ->  centre->port %.2f"
        % (UNI[2], UNI[5], E_UNI))
    say("   SO flange  t=%.2f  trf=%.2f  bore d=%.2f  %d x %.2f bolts on %.2f BC"
        % (FLG[6], FLG[8], FLG[3], FLG[7], FLG[5], FLG[4]))
    say()
    say("Grade     : support-post bottom z = %.2f  (0'-0\" datum)" % ground_z)
    say("            ground-run centreline z = %.2f  (= datum + OD/2)" % cl_z)
    say()
    say("Work points (mm, launcher model coordinates)")
    for name, wp in (("ell 1  turn down", wp1), ("ell 2  grade, turn -X", wp2),
                     ("ell 3  grade, turn +Y", wp3), ("ell 4  turn up", wp4),
                     ("ell 5  top of rise", wp5)):
        say("   %-22s  X %10.2f   Y %10.2f   Z %10.2f"
            % (name, wp.x, wp.y, wp.z))
    say()
    say("Pipe cut lengths")
    total = 0.0
    for label, L in pipes:
        total += L
        say("   %8.2f mm  (%7.3f in)   %s" % (L, L / IN, label))
    say("   %8.2f mm  (%7.2f m)   TOTAL DN50 pipe" % (total, total / 1000.0))
    say()
    say("Component count: 2 x SO flange, 5 x SW 90 ell, 1 x SW union, "
        "%d x pipe" % len(pipes))
    say()
    say("Checks (derived vs expected)")
    for name, got, want in checks:
        say("   %-34s got %12.4f   expect %12.4f   d %8.4f"
            % (name, got, want, got - want))
    say("   %-34s got %12.4f   expect %12.4f"
        % ("WN/SO bore d vs CSV", FLG[3], _f(flg_row, "d")))
    ext_lo = Vector(min(wp1.x, wp5.x), min(wp1.y, wp5.y), cl_z)
    ext_hi = Vector(max(wp1.x, wp5.x), max(wp1.y, wp5.y), wp5.z)
    say("   overall extents  X %.1f..%.1f   Y %.1f..%.1f   Z %.1f..%.1f"
        % (ext_lo.x, ext_hi.x, ext_lo.y, ext_hi.y, ext_lo.z, ext_hi.z))
    if adjust:
        say()
        say("Short-pipe adjustments (the guide §9.2.2)")
        for label, L, lim in adjust:
            say("   %s: %.2f mm < %.2f mm limit" % (label, L, lim))
    else:
        say("   no stub trips the short-pipe rule (limit %.2f mm)"
            % min(MIN_PIPE_ABS, OD / 2.0))
    say()
    say("Assumptions / defaults applied")
    say("   * 6'-0\" is measured from the gasket mating face to the centreline")
    say("     of the 20'-0\" (+Y) run;  20'-0\" is measured from the centreline")
    say("     of the 6'-0\" (-X) run to the raised face of the open end flange.")
    say("     Both are closed back in the checks above.")
    say("   * The 6'-0\" rise is elbow work point to elbow work point, and the")
    say("     6\" and 12\" stubs are CUT pipe lengths, as the sketch words them.")
    say("   * The union sits in the 20'-0\" +Y leg, %.1f mm (%.0f\") of pipe"
        % (L_UNION_LEAD, L_UNION_LEAD / IN))
    say("     downstream of the X-Y plane elbow [3]; the balance of the leg")
    say("     follows it.")
    say("   * Grade is the bottom of the pipe OD, per the sketch note.")
    say("   * The new SO flange re-uses the existing %s and Bolts_Nuts010."
        % MATE_GASKET)
    say("   * Nothing was saved. Save-As '%s_drain.FCStd' to keep it."
        % DOC_NAME)
    say("=" * 74)

    FreeCAD.Console.PrintMessage("\n".join(report) + "\n")

    try:
        if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
            FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass

    return doc


if __name__ == "__main__":
    build()
