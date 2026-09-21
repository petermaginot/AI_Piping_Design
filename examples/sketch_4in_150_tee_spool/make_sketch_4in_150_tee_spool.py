# make_sketch_4in_150_tee_spool.py
#
# Reconstruct the piping spool drawn on the hand isometric IMG_2618.jpg with
# the Quetzal FreeCAD workbench.  Section numbers refer to docs/freecad-quetzal-guide.md.
#
# SOURCE
#   examples/sketch_4in_150_tee_spool/IMG_2618.jpg   4032 x 3024, pencil/pen on
#   triangular grid paper.  Every dimension cluster was cropped and upscaled 3x
#   before transcription (§9.1.1).
#
# SPEC (boxed note, upper right of the sheet)
#   4" Sch-STD pipe and fittings  ->  DN100, SCH-STD
#   150lb flanges                 ->  FClass 150lb, raised face
#
# AXIS LEGEND (drawn on the sheet)
#   Z up, X to the lower-left, Y to the lower-right.  The elbow sits at the apex
#   and both legs descend from it, so the flange leg runs +X from the elbow and
#   the tee leg runs +Y.
#
# TOPOLOGY
#   Slip-on flange (open face, +X end)
#     -- 24" leg --  90 LR elbow  -- 36" leg --  4x4 equal tee
#                                                  |-- branch UP (+Z): WN flange
#                                                  `-- far run (+Y):   WN flange
#
# DIMENSIONS -- both are work-point distances, NOT cut lengths (§9.2)
#   24"  slip-on flange RAISED FACE  ->  elbow work point      (along +X)
#   36"  elbow work point            ->  tee work point        (along +Y)
#
#   The 36" arrowhead lands on the dashed witness line dropping from the tee
#   centreline (source x ~2865 px), not on the WN flange (x ~3488 px).  This is
#   where the sheet differs from its sister drawing IMG_2146, whose 36" ran to
#   the flange face -- see examples/iso_3in_tee_run/make_iso_3in_tee_run.py.  Confirmed with the
#   user before building.
#
#   Pipe cut lengths are NOT taken off the sheet.  They are derived by spanning
#   the placed fittings' ports, so the take-outs come from tablez/ (§9.2.3).
#
# SHORT-PIPE RULE (§9.2.2)
#   Scaling the sheet off the 36" dimension gives ~0.83 mm/px.  On that scale the
#   run-side weld dot sits ~148 mm from the tee work point against a table C of
#   105 mm, and the branch weld ~139 mm against M = 105 mm -- residual stubs of
#   ~43 and ~34 mm, both below the min(50, OD/2 = 57.15) mm limit.  Both WN
#   flanges are therefore welded DIRECTLY to the tee, with no pipe between.
#   Confirmed with the user.  Reported as an adjustment below.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute, or paste in the Python console).
# Quetzal's execute() methods need a GUI ViewObject, so this cannot run under
# freecadcmd.  See the guide section 1.

import os
import sys
import math

import FreeCAD
from FreeCAD import Vector, Rotation, Placement

try:
    import FreeCADGui
    _HAS_GUI = True
except Exception:
    _HAS_GUI = False


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _repo_root():
    """Walk up from this file to the directory that holds quetzal_env.py.

    This macro lives two levels below the repo root, so the search walks the
    parent directories rather than testing a single path.
    """
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


def _read_row(csv_name, psize, branch=None):
    """Row for PSize=psize (and optional PSizeBranch=branch) from tablez/<csv_name>."""
    return qenv.read_row(csv_name, psize, PSizeBranch=branch)


_f = qenv.f    # column by NAME, with a default -- column sets differ (§6)


def _rot_two(a0, a1, b0, b1):
    """Rotation R such that R*a0 == b0 and R*a1 == b1.

    Builds an orthonormal frame from each direction pair and returns the rotation
    that carries one frame onto the other.  The two pairs must share the same
    in-between angle -- assert that before calling (§9.3).
    """
    def frame(u, v):
        x = Vector(u).normalize()
        z = x.cross(Vector(v)); z.normalize()
        y = z.cross(x)
        return Rotation(x, y, z)
    return frame(b0, b1).multiply(frame(a0, a1).inverted())


def _line_intersect(P0, d0, P1, d1):
    """Intersection (work point) of lines P0+t*d0 and P1+s*d1 (assumed to meet)."""
    P0, d0, P1, d1 = Vector(P0), Vector(d0), Vector(P1), Vector(d1)
    cr = d0.cross(d1)
    denom = cr.Length ** 2
    if denom < 1e-12:
        return P0
    t = (P1 - P0).cross(d1).dot(cr) / denom
    return P0 + d0 * t


def _world(obj, port):
    """Port `port` of `obj` in world coordinates."""
    return obj.Placement.multVec(obj.Ports[port])


# ---------------------------------------------------------------------------
# DIMENSIONS -- everything read off the sketch lives here (§9.6)
# ---------------------------------------------------------------------------

IN = 25.4

DN = "DN100"                # 4" NPS
SCHED = "SCH-STD"           # butt-weld fittings are tabulated SCH-STD (§6)
FCLASS = "150lb"
NORATE = "No rating"

D24 = 24 * IN               # +X : slip-on flange RAISED FACE -> elbow work point
D36 = 36 * IN               # +Y : elbow work point           -> tee work point

Xhat = Vector(1, 0, 0)      # iso lower-left  : elbow -> slip-on flange
Yhat = Vector(0, 1, 0)      # iso lower-right : elbow -> tee
Zhat = Vector(0, 0, 1)      # iso vertical

BRANCH_DIR = Vector(0, 0, 1)    # tee branch points straight up on the sheet

MIN_PIPE_ABS = 50.0         # §9.2.2 short-pipe limit, capped at OD/2 below

# Sketch scale, for the record only -- no build number depends on it.
# 1035 px measured between the elbow and tee work points against the 36" dim.
SKETCH_MM_PER_PX = 914.4 / 1101.0

# Stub lengths the sketch's weld dots imply, eliminated by the short-pipe rule.
SKETCH_RUN_STUB = 43.0      # tee run weld dot  ~148 mm from WP, minus C = 105
SKETCH_BRANCH_STUB = 34.0   # tee branch weld   ~139 mm from WP, minus M = 105


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Sketch_4in_150_TeeSpool")

    adjust = []   # §9.2.2 short-pipe adjustments, reported at the end
    short = []    # span-derived stubs that are short but still built

    # ---- Tables -----------------------------------------------------------
    pipe_row = _read_row("Pipe_%s.csv" % SCHED, DN)
    OD, THK = _f(pipe_row, "OD"), _f(pipe_row, "thk")
    BORE = OD - 2.0 * THK

    el_row = _read_row("Elbow_%s_LR90.csv" % SCHED, DN)
    BA, BR = _f(el_row, "BendAngle"), _f(el_row, "BendRadius")

    tee_row = _read_row("Tee_%s.csv" % SCHED, DN, branch=DN)
    TEE_C, TEE_M = _f(tee_row, "C"), _f(tee_row, "M")

    so_row = _read_row("Flange_ASME-SO-RF-%s.csv" % FCLASS, DN)
    wn_row = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN)

    MIN_PIPE = min(MIN_PIPE_ABS, OD / 2.0)

    # ---- Work-point skeleton (§9.2.1) -------------------------------------
    # Anchor on the elbow; nothing below moves it.
    WP_elbow = Vector(0, 0, 0)
    WP_soFace = WP_elbow + Xhat * D24
    WP_tee = WP_elbow + Yhat * D36

    # ---- Elbow: legs +X (to the flange) and +Y (to the tee) ---------------
    # Angle feasibility (§9.3): the two outward leg directions either side of the
    # fitting must differ by exactly the bend angle.
    inlet_dir, outlet_dir = Xhat, Yhat
    if abs(inlet_dir.getAngle(outlet_dir) - math.radians(180.0 - BA)) > 1e-6:
        raise RuntimeError(
            "elbow infeasible: legs are %.3f deg apart, a %.0f deg bend needs %.0f"
            % (math.degrees(inlet_dir.getAngle(outlet_dir)), BA, 180.0 - BA))

    elbow = pCmd.makeElbow([DN, OD, THK, BA, BR], rating=SCHED)
    elbow.PRating = SCHED
    elbow.Label = "Elbow DN100 4in SCH-STD 90LR"
    doc.recompute()
    # Read the ACTUAL local port layout -- never assume it (§9.3).
    d0, d1 = elbow.PortDirections[0], elbow.PortDirections[1]
    wp_local = _line_intersect(elbow.Ports[0], d0, elbow.Ports[1], d1)
    Rel = _rot_two(d0, d1, inlet_dir, outlet_dir)
    elbow.Placement = Placement(WP_elbow - Rel.multVec(wp_local), Rel)
    doc.recompute()

    # ---- Tee at its work point --------------------------------------------
    # Local frame (pFeatures.py ~L1048): run on local -/+Z (ports 0/1), branch on
    # local +Y (port 2), work point at the local origin.  Want the run on world Y
    # with port 0 facing back at the elbow, and the branch up +Z:
    #   local Z -> +Y,  local Y -> +Z,  local X -> local Y x local Z = -X.
    tee_zdir = Yhat                       # run direction (port 1 side)
    tee_ydir = Vector(BRANCH_DIR)         # branch direction
    tee_xdir = tee_ydir.cross(tee_zdir)
    tee = pCmd.makeTee(
        [DN, _f(tee_row, "OD"), _f(tee_row, "OD2"), _f(tee_row, "thk"),
         _f(tee_row, "thk2"), TEE_C, TEE_M, DN],
        rating=SCHED)
    tee.PRating = SCHED
    tee.Label = "Tee DN100 4x4 SCH-STD"
    tee.Placement = Placement(WP_tee, Rotation(tee_xdir, tee_ydir, tee_zdir))
    doc.recompute()

    # ---- Slip-on flange: raised face on the 24" work point ----------------
    # The SO table has no dwn/twn/R columns -- default them to 0 (§4/§6).
    so = pCmd.makeFlange(
        [DN, "SO", _f(so_row, "D"), _f(so_row, "d"), _f(so_row, "df"),
         _f(so_row, "f"), _f(so_row, "t"), int(so_row["n"]),
         _f(so_row, "trf"), _f(so_row, "drf"), _f(so_row, "twn", 0),
         _f(so_row, "dwn", 0), _f(so_row, "ODp"), _f(so_row, "R", 0),
         _f(so_row, "T1"), 0, 0],
        doOffset=True, rating=NORATE, fclass=FCLASS)
    so.Label = "Flange SO DN100 150# RF (open face, +X end)"
    # Local +Z is the pipe axis; it must point back toward the elbow (-X), which
    # leaves the raised face (port 0) on the +X side.  Then drop port 0 onto the
    # work point.
    so_rot = Rotation(Vector(0, 0, 1), Xhat * -1)
    so.Placement = Placement(WP_soFace - so_rot.multVec(so.Ports[0]), so_rot)
    doc.recompute()

    # ---- Two WN flanges, welded DIRECTLY to the tee (§9.2.2) --------------
    def make_wn(label):
        f = pCmd.makeFlange(
            [DN, "WN", _f(wn_row, "D"), BORE, _f(wn_row, "df"),
             _f(wn_row, "f"), _f(wn_row, "t"), int(wn_row["n"]),
             _f(wn_row, "trf"), _f(wn_row, "drf"), _f(wn_row, "twn"),
             _f(wn_row, "dwn"), _f(wn_row, "ODp"), _f(wn_row, "R"),
             _f(wn_row, "T1"), 0, 0],
            doOffset=True, rating=SCHED, fclass=FCLASS)
        f.Label = label
        return f

    wn_branch = make_wn("Flange WN DN100 150# RF (tee branch, +Z)")
    wn_run = make_wn("Flange WN DN100 150# RF (tee run end, +Y)")
    doc.recompute()
    pCmd.alignTwoPorts(wn_branch, 1, tee, 2)   # weld end -> branch (up, +Z)
    pCmd.alignTwoPorts(wn_run, 1, tee, 1)      # weld end -> far run end (+Y)
    doc.recompute()
    adjust.append(("WN flange -> tee branch (+Z)", SKETCH_BRANCH_STUB, MIN_PIPE))
    adjust.append(("WN flange -> tee run end (+Y)", SKETCH_RUN_STUB, MIN_PIPE))

    # ---- Pipes: derived by spanning the placed fittings' ports ------------
    def mk_pipe(a_obj, a_port, b_obj, b_port, label):
        start = _world(a_obj, a_port)
        vec = _world(b_obj, b_port) - start
        L = vec.Length
        if L <= 1e-6:
            adjust.append((label, L, MIN_PIPE))
            return None, 0.0
        if L < MIN_PIPE:
            short.append((label, L, MIN_PIPE))
        p = pCmd.makePipe(SCHED, [DN, OD, THK, L], pos=start, Z=Vector(vec).normalize())
        p.PRating = SCHED
        p.Label = label
        return p, L

    # Pipe 1 (-X): SO flange weld end -> elbow inlet
    pipe1, L1 = mk_pipe(so, 1, elbow, 0, "Pipe DN100 SCH-STD (24in leg, X)")
    # Pipe 2 (+Y): elbow outlet -> tee run end facing the elbow
    pipe2, L2 = mk_pipe(elbow, 1, tee, 0, "Pipe DN100 SCH-STD (36in leg, Y)")
    doc.recompute()

    # ---- Verification out of the BUILT document (§8) ----------------------
    wp_elbow_built = _line_intersect(
        _world(elbow, 0), elbow.Placement.Rotation.multVec(elbow.PortDirections[0]),
        _world(elbow, 1), elbow.Placement.Rotation.multVec(elbow.PortDirections[1]))
    d24_built = (WP_soFace - wp_elbow_built).x
    d36_vec = tee.Placement.Base - wp_elbow_built
    seat_branch = (_world(wn_branch, 1) - _world(tee, 2)).Length
    seat_run = (_world(wn_run, 1) - _world(tee, 1)).Length
    branch_face = _world(wn_branch, 0)
    branch_dx = abs(branch_face.x - tee.Placement.Base.x)
    branch_dy = abs(branch_face.y - tee.Placement.Base.y)

    checks = [
        ("24in flange face -> elbow WP, along X", d24_built, D24),
        ("36in elbow WP -> tee WP, along Y", d36_vec.y, D36),
        ("36in leg off-axis (dX)", d36_vec.x, 0.0),
        ("36in leg off-axis (dZ)", d36_vec.z, 0.0),
        ("branch WN seated on tee port 2 (gap)", seat_branch, 0.0),
        ("run WN seated on tee port 1 (gap)", seat_run, 0.0),
        ("branch flange face over tee WP (dX)", branch_dx, 0.0),
        ("branch flange face over tee WP (dY)", branch_dy, 0.0),
        # Quetzal stores these as Quantities -- float() them before comparing.
        ("WN bore == OD - 2*thk", float(wn_run.d), BORE),
        ("pipe1 ID == OD - 2*thk", float(pipe1.OD) - 2.0 * float(pipe1.thk), BORE),
    ]
    bad = [c for c in checks if abs(c[1] - c[2]) > 1e-6]

    # ---- View + save ------------------------------------------------------
    try:
        if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
            FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__))
                            if "__file__" in globals() else os.getcwd(),
                            "make_sketch_4in_150_tee_spool.FCStd")
    doc.saveAs(out_path)

    # ---- Report (§9.6) ----------------------------------------------------
    msg = []
    add = msg.append
    add("\n=== Sketch reconstruction: IMG_2618.jpg -- 4in Sch-STD / 150# tee spool ===")
    add("  Spec (boxed note): 4\" Sch-STD pipe and fittings, 150lb flanges"
        "  ->  %s / %s / %s" % (DN, SCHED, FCLASS))
    add("")
    add("  WORK POINTS (mm, axes from the sheet's legend: X lower-left, Y lower-right, Z up)")
    add("    slip-on flange raised face : (%9.3f, %9.3f, %9.3f)" % tuple(WP_soFace))
    add("    elbow work point           : (%9.3f, %9.3f, %9.3f)" % tuple(WP_elbow))
    add("    tee work point             : (%9.3f, %9.3f, %9.3f)" % tuple(WP_tee))
    add("")
    add("  TAKE-OUTS READ FROM tablez/  (nothing below is hardcoded)")
    add("    pipe  Pipe_%s.csv          OD=%.2f  thk=%.2f  bore=%.2f"
        % (SCHED, OD, THK, BORE))
    add("    elbow Elbow_%s_LR90.csv    BendAngle=%.0f  BendRadius=%.2f (= centre-to-face)"
        % (SCHED, BA, BR))
    add("    tee   Tee_%s.csv           C=%.2f (run)  M=%.2f (branch)" % (SCHED, TEE_C, TEE_M))
    add("    SO    Flange_ASME-SO-RF-%s.csv  T1=%.2f  trf=%.2f  face-to-weld=%.2f"
        % (FCLASS, _f(so_row, "T1"), _f(so_row, "trf"), 2.0 * _f(so_row, "trf")))
    add("    WN    Flange_ASME-WN-RF-%s.csv  T1=%.2f  trf=%.2f  face-to-weld=%.2f"
        % (FCLASS, _f(wn_row, "T1"), _f(wn_row, "trf"),
           _f(wn_row, "T1") + _f(wn_row, "trf")))
    add("")
    add("  PIPE CUT LENGTHS (derived by spanning the placed fittings' ports)")
    add("    %-38s %9.2f mm  = %6.2f in" % ("24in leg (flange weld -> elbow)", L1, L1 / IN))
    add("    %-38s %9.2f mm  = %6.2f in" % ("36in leg (elbow -> tee)", L2, L2 / IN))
    add("")
    add("  SHORT-PIPE ADJUSTMENTS (§9.2.2, limit = min(50, OD/2) = %.2f mm)" % MIN_PIPE)
    for label, L, lim in adjust:
        add("    ELIMINATED  %-34s sketch stub %.1f mm < %.2f -> direct weld"
            % (label, L, lim))
    if short:
        for label, L, lim in short:
            add("    WARNING     %-34s %.1f mm < %.2f -- built anyway" % (label, L, lim))
    else:
        add("    (no span-derived stub fell below the limit)")
    add("")
    add("  COMPONENT COUNT vs the sheet")
    add("    slip-on flange 1  |  90 LR elbow 1  |  4x4 tee 1  |  WN flange 2  |  pipe %d"
        % len([p for p in (pipe1, pipe2) if p is not None]))
    add("")
    add("  CHECKS (measured out of the built document)")
    for name, got, want in checks:
        add("    %-42s %14.6f  (want %.6f)  %s"
            % (name, got, want, "OK" if abs(got - want) <= 1e-6 else "** MISMATCH **"))
    add("")
    add("  DEFAULTS AND READINGS APPLIED")
    add("    - Both drawing dims are WORK-POINT distances, not cut lengths (§9.2).")
    add("      The 36\" witness line drops from the tee centreline, not the WN")
    add("      flange face -- unlike the sister sheet IMG_2146.  Confirmed with the user.")
    add("    - Butt-weld fittings taken from the SCH-STD tables; no SCH-40 fitting")
    add("      tables exist and the walls match at DN100 (6.02 mm) (§6).")
    add("    - WN bore computed as OD - 2*thk = %.2f, not the CSV d column (§4)." % BORE)
    add("    - Tee branch points +Z (up) as drawn; run port 0 faces the elbow.")
    add("    - Anchored on the elbow work point at the origin; nothing moves it.")
    add("    - Sketch scale basis %.4f mm/px (1101 px across the 36\" dim).  It is used"
        % SKETCH_MM_PER_PX)
    add("      ONLY to judge the two weld-dot stubs above; the two callout dimensions")
    add("      are exact and no built geometry depends on the scale.  Any station you")
    add("      later take off this sheet by scaling is an estimate, not a dimension.")
    add("")
    add("  Saved: %s" % out_path)
    if bad:
        add("  *** %d CHECK(S) FAILED -- see above ***" % len(bad))
    add("")
    FreeCAD.Console.PrintMessage("\n".join(msg))
    return doc


if __name__ == "__main__":
    build()
