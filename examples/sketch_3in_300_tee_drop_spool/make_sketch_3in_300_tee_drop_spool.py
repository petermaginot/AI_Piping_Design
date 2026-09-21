# make_sketch_3in_300_tee_drop_spool.py
#
# Reconstruct the piping spool drawn on the hand isometric IMG_2619.jpg with the
# Quetzal FreeCAD workbench.  Section numbers below refer to docs/freecad-quetzal-guide.md.
#
# SOURCE
#   examples/sketch_3in_300_tee_drop_spool/IMG_2619.jpg   3492 x 2297, pen on
#   triangular grid paper.  Every dimension cluster was cropped and upscaled
#   ~5-9x before transcription (§9.1.1).
#
# SPEC (boxed note, upper right of the sheet)
#   All pipe   3" Sch-STD            ->  DN80, SCH-STD (butt-weld fittings, §6)
#   All flanges 3" Sch-STD bore WN   ->  weld-neck, raised face, bore = OD-2*thk
#   300#                             ->  FClass 300lb
#
# AXIS LEGEND (Quetzal iso standard -- the sheet has no explicit legend but the
# geometry matches it: Z up, Y up-right +30, X down-right -30)
#   Top run  : along Y  (WN flange A at -Y, WN flange B at +Y, tee in between)
#   Drop     : along -Z (tee branch straight down to the elbow)
#   Bottom run: along X (elbow -> WN flange C), 1" thredolet on the pipe bottom
#
# TOPOLOGY
#   WN flange A --1'-9"-- [ TEE ] --3'-6"-- WN flange B      (run along Y)
#                           |
#                          32"   (branch straight down, -Z)
#                           |
#                       90 LR elbow
#                           |
#                    24" -- (o) 1" thredolet, bottom of pipe (-Z) -- 24"
#                           |
#                       WN flange C
#
# DIMENSIONS (confirmed with the user, §9.2 / §11.2)
#   1'-9" = 21"  : WN flange A RAISED FACE  -> tee work point       (along -Y)
#   3'-6" = 42"  : tee work point           -> WN flange B RAISED FACE (along +Y)
#   32"          : tee work point           -> elbow work point     (along -Z)
#   24" + 24"    : elbow work point -> thredolet CL -> WN flange C RAISED FACE (+X)
#
#   Terminal flange dimensions run to the raised FACE; the 32" fitting-to-fitting
#   dimension runs work point to work point.  Pipe cut lengths are NOT taken off
#   the sheet -- they are derived by spanning the placed fittings' ports, so the
#   take-outs come from tablez/ (§9.2).
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


def _read_row(csv_name, psize, branch=None, ang=None):
    """Row for PSize=psize (+ optional PSizeBranch / Ang) from tablez/<csv_name>."""
    return qenv.read_row(csv_name, psize, PSizeBranch=branch, Ang=ang)


_f = qenv.f    # column by NAME, with a default -- column sets differ (§6)


def _rot_two(a0, a1, b0, b1):
    """Rotation R such that R*a0 == b0 and R*a1 == b1 (§9.3).

    The two direction pairs must share the same in-between angle -- assert that
    before calling.
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


def _phi_for_dir(pipe, desired):
    """Circumferential clock (deg) so an outlet on `pipe` points at `desired`.

    outletPlacementOnPipe measures phi from the pipe's local +X (CCW about the
    pipe axis); the outward radial in world is cos(phi)*ex + sin(phi)*ey with
    ex/ey the pipe's local X/Y in world.  Reading the pipe's actual rotation
    avoids hand-guessing the clock angle (§3.1).
    """
    Rp = pipe.Placement.Rotation
    ex = Rp.multVec(Vector(1, 0, 0))
    ey = Rp.multVec(Vector(0, 1, 0))
    return math.degrees(math.atan2(Vector(desired).dot(ey), Vector(desired).dot(ex)))


# ---------------------------------------------------------------------------
# DIMENSIONS -- everything read off the sketch lives here (§9.6)
# ---------------------------------------------------------------------------

IN = 25.4

DN = "DN80"                 # 3" NPS
DN_BR = "DN25"              # 1" NPS thredolet branch
SCHED = "SCH-STD"           # butt-weld fittings are tabulated SCH-STD (§6)
FCLASS = "300lb"
NORATE = "No rating"
OUTLET_RATING = "3000lb"    # 1" thredolet -> Outlet_3000lb.csv (SW), per the user

D_FLG_A = 21 * IN           # 1'-9" : WN flange A raised face -> tee work point   (-Y)
D_FLG_B = 42 * IN           # 3'-6" : tee work point -> WN flange B raised face   (+Y)
D_DROP = 32 * IN            # 32"   : tee work point -> elbow work point          (-Z)
D_BOT = (24 + 24) * IN      # 24"+24" : elbow work point -> WN flange C raised face (+X)
THREDOLET_STATION = 24 * IN  # elbow work point -> thredolet centerline           (+X)

Xhat = Vector(1, 0, 0)     # iso down-right : elbow -> WN flange C (bottom run)
Yhat = Vector(0, 1, 0)     # iso up-right   : top run  (flange A -> tee -> flange B)
Zhat = Vector(0, 0, 1)     # iso vertical

BRANCH_DIR = Vector(0, 0, -1)      # tee branch points straight down on the sheet
THREDOLET_DIR = Vector(0, 0, -1)   # "1\" thredolet bottom of pipe"

MIN_PIPE_ABS = 50.0        # §9.2.2 short-pipe limit, capped at OD/2 below

# Sketch scale, for the record only -- no build number depends on it.
# ~1590 px measured between the tee and elbow work points against the 32" dim.
SKETCH_MM_PER_PX = 812.8 / 1590.0


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Sketch_3in_300_TeeDropSpool")

    adjust = []   # §9.2.2 short-pipe adjustments (welded direct), reported below
    short = []    # span-derived stubs that are short but still built

    # ---- Tables ---------------------------------------------------------------
    pipe_row = _read_row("Pipe_%s.csv" % SCHED, DN)
    OD, THK = _f(pipe_row, "OD"), _f(pipe_row, "thk")
    BORE = OD - 2.0 * THK

    el_row = _read_row("Elbow_%s_LR90.csv" % SCHED, DN)
    BA, BR = _f(el_row, "BendAngle"), _f(el_row, "BendRadius")

    tee_row = _read_row("Tee_%s.csv" % SCHED, DN, branch=DN)
    TEE_C, TEE_M = _f(tee_row, "C"), _f(tee_row, "M")

    wn_row = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN)
    WN_T1, WN_TRF = _f(wn_row, "T1"), _f(wn_row, "trf")

    ol_row = _read_row("Outlet_%s.csv" % OUTLET_RATING, DN_BR, ang=0)
    OL_OD, OL_THK = _f(ol_row, "OD"), _f(ol_row, "thk")
    OL_A, OL_B, OL_E = _f(ol_row, "A"), _f(ol_row, "B"), _f(ol_row, "E", 0)
    OL_CONN = ol_row["Conn"].strip()

    MIN_PIPE = min(MIN_PIPE_ABS, OD / 2.0)

    # ---- Work-point skeleton (§9.2) ----------------------------------------
    # Anchor on the tee work point at the origin; nothing below moves the tee.
    WP_tee = Vector(0, 0, 0)
    WP_elbow = WP_tee + BRANCH_DIR * D_DROP           # 32" straight down
    WP_faceA = WP_tee - Yhat * D_FLG_A                # flange A raised face
    WP_faceB = WP_tee + Yhat * D_FLG_B                # flange B raised face
    WP_faceC = WP_elbow + Xhat * D_BOT                # flange C raised face

    # ---- Tee at its work point -------------------------------------------
    # Tee local frame (pFeatures.py): run on local -/+Z (ports 0/1), branch on
    # local +Y (port 2), work point at the local origin.  Want the run on world
    # Y (port 1 -> +Y) and the branch straight down (-Z):
    #   local Z -> +Y,  local Y -> -Z,  local X -> local Y x local Z = +X.
    tee_zdir = Yhat
    tee_ydir = Vector(BRANCH_DIR)
    tee_xdir = tee_ydir.cross(tee_zdir)
    tee = pCmd.makeTee(
        [DN, _f(tee_row, "OD"), _f(tee_row, "OD2"), _f(tee_row, "thk"),
         _f(tee_row, "thk2"), TEE_C, TEE_M, DN],
        rating=SCHED)
    tee.PRating = SCHED
    tee.Label = "[TEE] Tee DN80 3x3 SCH-STD"
    tee.Placement = Placement(WP_tee, Rotation(tee_xdir, tee_ydir, tee_zdir))
    doc.recompute()

    # ---- 90 LR elbow: legs +Z (up to the tee) and +X (to flange C) --------
    # Angle feasibility (§9.3): the two outward leg directions either side of the
    # fitting must differ by exactly the bend angle.
    inlet_dir, outlet_dir = Zhat, Xhat        # port 0 faces up, port 1 faces +X
    if abs(inlet_dir.getAngle(outlet_dir) - math.radians(180.0 - BA)) > 1e-6:
        raise RuntimeError(
            "elbow infeasible: legs are %.3f deg apart, a %.0f deg bend needs %.0f"
            % (math.degrees(inlet_dir.getAngle(outlet_dir)), BA, 180.0 - BA))

    elbow = pCmd.makeElbow([DN, OD, THK, BA, BR], rating=SCHED)
    elbow.PRating = SCHED
    elbow.Label = "[ELL] Elbow DN80 3in SCH-STD 90LR"
    doc.recompute()
    d0, d1 = elbow.PortDirections[0], elbow.PortDirections[1]   # read, never assume
    wp_local = _line_intersect(elbow.Ports[0], d0, elbow.Ports[1], d1)
    Rel = _rot_two(d0, d1, inlet_dir, outlet_dir)
    elbow.Placement = Placement(WP_elbow - Rel.multVec(wp_local), Rel)
    doc.recompute()

    # ---- Three WN flanges, raised face on their work points --------------
    def make_wn(label, face_wp, axis_toward_spool):
        """WN flange with bore = OD-2*thk (§4); local +Z (pipe axis, port 1)
        points `axis_toward_spool`, so the raised face (port 0) lands on
        `face_wp` pointing the opposite way."""
        f = pCmd.makeFlange(
            [DN, "WN", _f(wn_row, "D"), BORE, _f(wn_row, "df"),
             _f(wn_row, "f"), _f(wn_row, "t"), int(wn_row["n"]),
             WN_TRF, _f(wn_row, "drf"), _f(wn_row, "twn"),
             _f(wn_row, "dwn"), _f(wn_row, "ODp"), _f(wn_row, "R"),
             WN_T1, 0, 0],
            doOffset=True, rating=SCHED, fclass=FCLASS)
        f.Label = label
        doc.recompute()
        rot = Rotation(Vector(0, 0, 1), Vector(axis_toward_spool))
        f.Placement = Placement(face_wp - rot.multVec(f.Ports[0]), rot)
        doc.recompute()
        return f

    flangeA = make_wn("[F-A] Flange WN DN80 300# RF (top run, -Y end)",
                      WP_faceA, Yhat)             # pipe axis points +Y to the tee
    flangeB = make_wn("[F-B] Flange WN DN80 300# RF (top run, +Y end)",
                      WP_faceB, Yhat * -1)        # pipe axis points -Y to the tee
    flangeC = make_wn("[F-C] Flange WN DN80 300# RF (bottom run, +X end)",
                      WP_faceC, Xhat * -1)        # pipe axis points -X to the elbow

    # ---- Pipes: derived by spanning the placed fittings' ports -----------
    def mk_pipe(a_obj, a_port, b_obj, b_port, label):
        start = _world(a_obj, a_port)
        vec = _world(b_obj, b_port) - start
        L = vec.Length
        if L <= 1e-6:
            adjust.append((label, L, MIN_PIPE))
            return None, 0.0
        if L < MIN_PIPE:
            short.append((label, L, MIN_PIPE))
        p = pCmd.makePipe(SCHED, [DN, OD, THK, L], pos=start,
                          Z=Vector(vec).normalize())
        p.PRating = SCHED
        p.Label = label
        return p, L

    pipeA, LA = mk_pipe(flangeA, 1, tee, 0, "Pipe DN80 SCH-STD (1'-9\" leg, -Y)")
    pipeB, LB = mk_pipe(flangeB, 1, tee, 1, "Pipe DN80 SCH-STD (3'-6\" leg, +Y)")
    pipeD, LD = mk_pipe(tee, 2, elbow, 0, "Pipe DN80 SCH-STD (32\" drop, -Z)")
    pipeC, LC = mk_pipe(elbow, 1, flangeC, 1, "Pipe DN80 SCH-STD (bottom run, +X)")
    doc.recompute()

    # ---- 1" thredolet on the bottom run, bottom of pipe, 24" from elbow WP -
    # Station is measured from the ELBOW work point; convert to a distance from
    # the bottom pipe's own port 0 (§3.1).  outletPlacementOnPipe takes a Pipe.
    p0 = _world(pipeC, 0)
    run_axis = (_world(pipeC, 1) - p0); run_axis.normalize()
    t_from_p0 = THREDOLET_STATION - (p0 - WP_elbow).dot(run_axis)
    phi = _phi_for_dir(pipeC, THREDOLET_DIR)
    ol_pos, ol_rot = pCmd.outletPlacementOnPipe(pipeC, t=t_from_p0, phi_deg=phi)
    thredolet = pCmd.makeOutlet(
        [OUTLET_RATING, DN_BR, OL_OD, OL_THK, OL_A, OL_B, OL_CONN, 0, OL_E],
        ol_pos, ol_rot, carrierOD=pipeC.OD)
    thredolet.Label = "[TOL] Thredolet 1in 3000# SW (bottom run, down)"
    doc.recompute()

    # ---- Verification out of the BUILT document (§8) --------------------
    wp_elbow_built = _line_intersect(
        _world(elbow, 0),
        elbow.Placement.Rotation.multVec(elbow.PortDirections[0]),
        _world(elbow, 1),
        elbow.Placement.Rotation.multVec(elbow.PortDirections[1]))

    faceA_built = _world(flangeA, 0)
    faceB_built = _world(flangeB, 0)
    faceC_built = _world(flangeC, 0)
    drop_vec = wp_elbow_built - tee.Placement.Base
    tol_world = thredolet.Placement.Base
    tol_sta = (tol_world - wp_elbow_built).dot(Xhat)

    checks = [
        ("flange A face -> tee WP, along -Y", (WP_tee - faceA_built).y, D_FLG_A),
        ("flange A face off-axis (dX)", faceA_built.x, 0.0),
        ("flange A face off-axis (dZ)", faceA_built.z, 0.0),
        ("tee WP -> flange B face, along +Y", (faceB_built - WP_tee).y, D_FLG_B),
        ("flange B face off-axis (dX)", faceB_built.x, 0.0),
        ("flange B face off-axis (dZ)", faceB_built.z, 0.0),
        ("tee WP -> elbow WP, straight down (-Z)", -drop_vec.z, D_DROP),
        ("drop off-axis (dX)", drop_vec.x, 0.0),
        ("drop off-axis (dY)", drop_vec.y, 0.0),
        ("elbow WP -> flange C face, along +X", (faceC_built - wp_elbow_built).x, D_BOT),
        ("flange C face off-axis (dY)", faceC_built.y - wp_elbow_built.y, 0.0),
        ("flange C face off-axis (dZ)", faceC_built.z - wp_elbow_built.z, 0.0),
        ("thredolet CL station from elbow WP (+X)", tol_sta, THREDOLET_STATION),
        ("pipeA seated on tee port 0 (gap)",
         (_world(pipeA, 1) - _world(tee, 0)).Length, 0.0),
        ("pipeB seated on tee port 1 (gap)",
         (_world(pipeB, 1) - _world(tee, 1)).Length, 0.0),
        ("pipeD seated on elbow port 0 (gap)",
         (_world(pipeD, 1) - _world(elbow, 0)).Length, 0.0),
        ("pipeC seated on elbow port 1 (gap)",
         (_world(pipeC, 0) - _world(elbow, 1)).Length, 0.0),
        # Quetzal stores these as Quantities -- float() them before comparing.
        ("WN bore == OD - 2*thk", float(flangeA.d), BORE),
        ("pipeA ID == OD - 2*thk",
         float(pipeA.OD) - 2.0 * float(pipeA.thk), BORE),
    ]
    bad = [c for c in checks if abs(c[1] - c[2]) > 1e-6]

    # every pipe length must be positive
    for lbl, L in (("pipeA", LA), ("pipeB", LB), ("pipeD", LD), ("pipeC", LC)):
        if L <= 0.0:
            bad.append((lbl + " length", L, 1.0))

    # ---- View + save ---------------------------------------------------
    try:
        if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
            FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass

    out_dir = (os.path.dirname(os.path.abspath(__file__))
               if "__file__" in globals() else os.getcwd())
    out_path = os.path.join(out_dir, "make_sketch_3in_300_tee_drop_spool.FCStd")
    doc.saveAs(out_path)

    # ---- Report (§9.6) -----------------------------------------------
    msg = []
    add = msg.append
    add("\n=== Sketch reconstruction: IMG_2619.jpg -- 3in Sch-STD / 300# tee-drop spool ===")
    add("  Spec (boxed note): All pipe 3\" Sch-STD | All flanges 3\" Sch-STD bore WN | 300#")
    add("                     ->  %s / %s / WN RF / %s" % (DN, SCHED, FCLASS))
    add("")
    add("  WORK POINTS (mm; iso axes: X down-right, Y up-right, Z up)")
    add("    WN flange A raised face : (%9.3f, %9.3f, %9.3f)" % tuple(WP_faceA))
    add("    tee work point          : (%9.3f, %9.3f, %9.3f)" % tuple(WP_tee))
    add("    WN flange B raised face : (%9.3f, %9.3f, %9.3f)" % tuple(WP_faceB))
    add("    elbow work point        : (%9.3f, %9.3f, %9.3f)" % tuple(WP_elbow))
    add("    WN flange C raised face : (%9.3f, %9.3f, %9.3f)" % tuple(WP_faceC))
    add("")
    add("  TAKE-OUTS READ FROM tablez/  (nothing below is hardcoded)")
    add("    pipe   Pipe_%s.csv            OD=%.2f  thk=%.2f  bore=%.2f"
        % (SCHED, OD, THK, BORE))
    add("    elbow  Elbow_%s_LR90.csv      BendAngle=%.0f  BendRadius=%.2f (= centre-to-face)"
        % (SCHED, BA, BR))
    add("    tee    Tee_%s.csv             C=%.2f (run)  M=%.2f (branch)"
        % (SCHED, TEE_C, TEE_M))
    add("    WN     Flange_ASME-WN-RF-%s.csv  T1=%.2f  trf=%.2f  face-to-weld=%.2f"
        % (FCLASS, WN_T1, WN_TRF, WN_T1 + WN_TRF))
    add("    outlet Outlet_%s.csv          OD=%.2f  A=%.2f  B=%.2f  E=%.2f  Conn=%s"
        % (OUTLET_RATING, OL_OD, OL_A, OL_B, OL_E, OL_CONN))
    add("")
    add("  PIPE CUT LENGTHS (derived by spanning the placed fittings' ports)")
    for lbl, L in (("1'-9\" leg (flange A weld -> tee)", LA),
                   ("3'-6\" leg (tee -> flange B weld)", LB),
                   ("32\" drop  (tee branch -> elbow)", LD),
                   ("bottom run (elbow -> flange C weld)", LC)):
        add("    %-38s %9.2f mm  = %6.2f in" % (lbl, L, L / IN))
    add("")
    add("  SHORT-PIPE RULE (§9.2.2, limit = min(50, OD/2) = %.2f mm)" % MIN_PIPE)
    if adjust:
        for label, L, lim in adjust:
            add("    ELIMINATED  %-34s stub %.1f mm < %.2f -> direct weld"
                % (label, L, lim))
    if short:
        for label, L, lim in short:
            add("    WARNING     %-34s %.1f mm < %.2f -- built anyway" % (label, L, lim))
    if not adjust and not short:
        add("    (no pipe fell below the limit)")
    add("")
    add("  COMPONENT COUNT vs the sheet")
    add("    WN flange 3  |  90 LR elbow 1  |  3x3 tee 1  |  1\" thredolet 1  |  pipe %d"
        % len([p for p in (pipeA, pipeB, pipeD, pipeC) if p is not None]))
    add("")
    add("  CHECKS (measured out of the built document)")
    for name, got, want in checks:
        add("    %-44s %14.6f  (want %.6f)  %s"
            % (name, got, want, "OK" if abs(got - want) <= 1e-6 else "** MISMATCH **"))
    add("")
    add("  DEFAULTS AND READINGS APPLIED")
    add("    - Iso axes taken as the Quetzal standard (Z up, Y up-right, X down-right);")
    add("      the sheet carries no explicit legend but the geometry matches it.")
    add("    - Terminal flange dims (1'-9\", 3'-6\", 24\"+24\") run to the raised FACE;")
    add("      the 32\" dim runs tee WP -> elbow WP.  Confirmed with the user.")
    add("    - Pipe cut lengths derived by spanning ports; take-outs from tablez/ (§9.2).")
    add("    - Butt-weld fittings from the SCH-STD tables; no SCH-40 fitting tables")
    add("      exist and the walls match at DN80 (5.49 mm) (§6).")
    add("    - WN bore computed as OD - 2*thk = %.2f, not the CSV d column (§4)." % BORE)
    add("    - Tee branch points straight down (-Z); tee run port 0 faces flange A (-Y).")
    add("    - Elbow turns the -Z drop into the +X bottom run (90 deg, feasible).")
    add("    - 1\" thredolet: Outlet_3000lb.csv (SW), on the pipe bottom (-Z),")
    add("      centreline %g\" from the elbow work point.  Per the user." % (THREDOLET_STATION / IN))
    add("    - Three bare WN faces -- no gasket / bolts / blind flange.")
    add("    - Anchored on the tee work point at the origin; nothing moves it.")
    add("    - Sketch scale basis %.4f mm/px is for reference only; no built" % SKETCH_MM_PER_PX)
    add("      geometry depends on it.  All four callout dimensions are exact.")
    add("")
    add("  Saved: %s" % out_path)
    if bad:
        add("  *** %d CHECK(S) FAILED -- see above ***" % len(bad))
    else:
        add("  All checks OK.")
    add("")
    FreeCAD.Console.PrintMessage("\n".join(msg))
    return doc


if __name__ == "__main__":
    build()
