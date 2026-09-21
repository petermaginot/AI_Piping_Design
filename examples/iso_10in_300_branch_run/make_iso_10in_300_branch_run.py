# make_iso_10in_300_branch_run.py
#
# Reconstruct the hand-drawn piping isometric IMG_2150.jpg with the Quetzal
# FreeCAD workbench.  Component numbers reference spool_example_BOM.csv:
#
#   1  10"  Pipe, Sch-STD
#   2  10"  Flange, WN RF, Sch-STD bore, 300#
#   3   2"  Flange, WN RF, Sch-XS bore, 300#
#   4   2"  Flange, RF Blind, 300#
#   5   2"  Weldolet, Sch-XS, Straight
#   6  10"  Elbow, LR, Sch-STD
#   7   2"  Elbow, LR, Sch-XS
#   8   2"  Ball valve, flanged, 300#
#
# TOPOLOGY (confirmed with the user):
#   A 10" Sch-STD / 300# main line forming a U in one horizontal plane, with only
#   TWO 10" pipe sections and TWO 10" elbows:
#
#     [cont] -- WN flg(2) A ==pipe1 (+X, 4'-6")== elbow1(6) ==pipe2 (+Y, 6'-0")== elbow2(6) -- WN flg(2) B -- [cont]
#                              |                                   |                              (raised face -X)
#                     straight branch UP (+Z)             elbow branch DOWN (-Z)
#                     weldolet(5) -> WN flg(3)            weldolet(5) -> 2" elbow(7) -> +X
#                     -> ball valve(8) -> blind(4)        -> WN flg(3) -> valve(8) -> blind(4)
#
#   - Flange A (left): raised face points -X (off-drawing continuation).  pipe1
#     runs +X from it to elbow1.
#   - elbow1 turns pipe1 (+X) into pipe2 (+Y, the 6'-0" run).
#   - elbow2 turns pipe2 (+Y) to -X and carries flange B (item 2) welded DIRECTLY
#     to it (no third pipe), raised face pointing -X.
#   - Left 2" branch: weldolet on TOP of pipe1 (+Z), straight up, no 2" elbow.
#   - Right 2" branch: weldolet on the BOTTOM of pipe2 (-Z), then a 2" LR elbow
#     (item 7) turning the branch horizontal (+X).
#
# ISOMETRIC DIMENSIONING (the guide section 9.2 - dims are to WORK POINTS):
#   6'-0" (field verify) = +Y, elbow1 WP -> elbow2 WP (pipe2).
#   4'-6" (2'-0" + 2'-6", chained) = +X, flange A face -> elbow1 WP / pipe2 CL (pipe1).
#   2'-0"                = +X, flange A face -> left weldolet centerline.
#   The right (elbow) weldolet has no location dimension -> assumed at the CENTER
#   of pipe2.  All these are editable constants below.
#
# Pipe cut lengths are DERIVED by spanning the placed fittings' ports.
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


# ---------------------------------------------------------------------------
# Small helpers (the geometry ones mirror make_iso_3in_tee_run.py)
# ---------------------------------------------------------------------------

_read_row = qenv.read_row   # row for PSize=... from tablez/<csv> (';', BOM)
_f = qenv.f                 # float from a CSV row, by column name


def _rot_two(a0, a1, b0, b1):
    """Rotation R such that R*a0 == b0 and R*a1 == b1 (frames share their angle)."""
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
    """World position of obj.Ports[port]."""
    return obj.Placement.multVec(obj.Ports[port])


def _phi_for_dir(pipe, desired):
    """Circumferential clock (deg) so an outlet on `pipe` points at `desired`.

    outletPlacementOnPipe measures phi from the pipe's local +X (CCW about the
    pipe axis).  The outward radial in world is cos(phi)*ex + sin(phi)*ey where
    ex/ey are the pipe's local X/Y axes in world coords, so phi = atan2 of the
    desired direction's components in that (ex, ey) frame.  Reading the pipe's
    actual rotation avoids hand-guessing the clock angle.
    """
    Rp = pipe.Placement.Rotation
    ex = Rp.multVec(Vector(1, 0, 0))
    ey = Rp.multVec(Vector(0, 1, 0))
    return math.degrees(math.atan2(Vector(desired).dot(ey), Vector(desired).dot(ex)))


# ---------------------------------------------------------------------------
# Spec / editable constants
# ---------------------------------------------------------------------------

IN = 25.4
FCLASS = "300lb"
NORATE = "No rating"

DN10 = "DN250"             # 10" NPS main line
SCH10 = "SCH-STD"
DN2 = "DN50"               # 2" NPS branches
SCH2 = "SCH-XS"

# --- Work-point distances (edit to the field measurements) -----------------
LEG_LEFT = 54 * IN                 # 4'-6" (2'-6"+2'-0"): flange A face -> elbow1 WP / pipe2 CL, +X (pipe1)
RUN_TOP = 72 * IN                  # 6'-0" (field verify): elbow1 WP -> elbow2 WP, +Y (pipe2)
WELDOLET_L_FROM_FLANGE = 24 * IN   # 2'-0": flange A face -> left weldolet CL, +X (chained before the 2'-6" reach to elbow1)
# Right (elbow) weldolet: no dimension -> placed at the center of pipe2.

# Iso axis unit vectors (Quetzal standard: Z up, Y up-right +30, X down-right -30)
Xhat = Vector(1, 0, 0)     # end legs, down-right on the iso
Yhat = Vector(0, 1, 0)     # 6'-0" top run, up-right on the iso
Zhat = Vector(0, 0, 1)     # branch takeoffs, up


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Iso_10in_300_BranchRun")

    # ---- Table rows -------------------------------------------------------
    p10 = _read_row("Pipe_%s.csv" % SCH10, DN10)
    OD10, THK10 = _f(p10, "OD"), _f(p10, "thk")
    p2 = _read_row("Pipe_%s.csv" % SCH2, DN2)
    OD2, THK2 = _f(p2, "OD"), _f(p2, "thk")

    el10 = _read_row("Elbow_%s_LR90.csv" % SCH10, DN10)
    el2 = _read_row("Elbow_%s_LR90.csv" % SCH2, DN2)
    wn10 = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN10)
    wn2 = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN2)
    bl2 = _read_row("Flange_ASME-BL-RF-%s.csv" % FCLASS, DN2)
    ol = _read_row("Outlet_%s.csv" % SCH2, DN2, Ang="0")   # straight branch (BW)
    vlv = _read_row("Valve_Ball_%sRF.csv" % FCLASS, DN2)

    # ---- Work points (mm) -------------------------------------------------
    WP_elbow1 = Vector(0, 0, 0)
    WP_elbow2 = WP_elbow1 + Yhat * RUN_TOP
    F_A = WP_elbow1 - Xhat * LEG_LEFT           # flange A raised face
    WELDOLET_L_IP = F_A + Xhat * WELDOLET_L_FROM_FLANGE

    # ---- Flange prop builders --------------------------------------------
    def wn_props(row, bore):
        return [row["PSize"].strip(), "WN", _f(row, "D"), bore, _f(row, "df"),
                _f(row, "f"), _f(row, "t"), int(float(row["n"])),
                _f(row, "trf"), _f(row, "drf"), _f(row, "twn"), _f(row, "dwn"),
                _f(row, "ODp"), _f(row, "R"), _f(row, "T1"), 0, 0]

    def bl_props(row):
        return [row["PSize"].strip(), "BL", _f(row, "D"), 0, _f(row, "df"),
                _f(row, "f"), _f(row, "t"), int(float(row["n"])),
                _f(row, "trf"), _f(row, "drf"), 0, 0, 0, 0, 0, 0, 0]

    # ---- 10" elbows (item 6): anchor each WP at its IP --------------------
    def place_elbow10(inlet_dir, outlet_dir, WP, label):
        e = pCmd.makeElbow(
            [DN10, OD10, THK10, _f(el10, "BendAngle"), _f(el10, "BendRadius")],
            rating=SCH10)
        e.PRating = SCH10
        e.Label = label
        doc.recompute()
        d0, d1 = e.PortDirections[0], e.PortDirections[1]
        wp_local = _line_intersect(e.Ports[0], d0, e.Ports[1], d1)
        R = _rot_two(d0, d1, inlet_dir, outlet_dir)
        e.Placement = Placement(WP - R.multVec(wp_local), R)
        doc.recompute()
        return e

    # elbow1: pipe1 (+X) -> pipe2 (+Y).   elbow2: pipe2 (+Y) -> flange B (-X).
    elbow1 = place_elbow10(Xhat * -1, Yhat, WP_elbow1, "Elbow 10in Sch-STD 90LR (1)")
    elbow2 = place_elbow10(Yhat * -1, Xhat * -1, WP_elbow2, "Elbow 10in Sch-STD 90LR (2)")

    # ---- Flange A (item 2): raised face on F_A, weld end toward +X --------
    flangeA = pCmd.makeFlange(wn_props(wn10, OD10 - 2.0 * THK10),
                              doOffset=True, rating=SCH10, fclass=FCLASS)
    flangeA.Label = "Flange WN 10in 300# (A)"
    doc.recompute()
    rotA = Rotation(Vector(0, 0, 1), Xhat)      # local +Z (weld end) -> +X
    flangeA.Placement = Placement(F_A - rotA.multVec(flangeA.Ports[0]), rotA)
    doc.recompute()

    # ---- Flange B (item 2): welded DIRECTLY to elbow2's outlet (no pipe) --
    flangeB = pCmd.makeFlange(wn_props(wn10, OD10 - 2.0 * THK10),
                              doOffset=True, rating=SCH10, fclass=FCLASS)
    flangeB.Label = "Flange WN 10in 300# (B)"
    doc.recompute()
    pCmd.alignTwoPorts(flangeB, 1, elbow2, 1)   # weld end -> elbow2 outlet; face -> -X
    doc.recompute()

    # ---- Two 10" pipes (item 1): span the placed fitting ports -----------
    def fill_pipe(startWP, endWP, axis, label):
        L = (endWP - startWP).Length
        p = pCmd.makePipe(SCH10, [DN10, OD10, THK10, L], pos=startWP, Z=axis)
        p.PRating = SCH10
        p.Label = label
        return p

    pipe1 = fill_pipe(_world(flangeA, 1), _world(elbow1, 0), Xhat,
                      "Pipe 10in Sch-STD (pipe1, 4ft6 leg)")
    pipe2 = fill_pipe(_world(elbow1, 1), _world(elbow2, 0), Yhat,
                      "Pipe 10in Sch-STD (pipe2, 6ft run)")
    doc.recompute()

    # ---- Weldolets (item 5) ----------------------------------------------
    def make_weldolet(host_pipe, ip_world, out_dir, label):
        p0 = _world(host_pipe, 0)
        axis = (_world(host_pipe, 1) - p0); axis.normalize()
        t = (ip_world - p0).dot(axis)
        phi = _phi_for_dir(host_pipe, out_dir)
        pos, rot = pCmd.outletPlacementOnPipe(host_pipe, t=t, phi_deg=phi)
        o = pCmd.makeOutlet(
            ["Sch-XS", DN2, _f(ol, "OD"), _f(ol, "thk"), _f(ol, "A"),
             _f(ol, "B"), ol["Conn"].strip(), int(float(ol["Ang"])), 0.0],
            pos, rot, carrierOD=host_pipe.OD)
        o.Label = label
        return o

    # Left weldolet: TOP of pipe1 (+Z), at 2'-0" from flange A.
    outletL = make_weldolet(pipe1, WELDOLET_L_IP, Zhat, "Weldolet 2in Sch-XS (L, up)")
    # Right weldolet: BOTTOM of pipe2 (-Z), at the center of pipe2.
    pipe2_mid = (_world(pipe2, 0) + _world(pipe2, 1)) * 0.5
    outletR = make_weldolet(pipe2, pipe2_mid, Zhat * -1, "Weldolet 2in Sch-XS (R, down)")
    doc.recompute()

    # ---- Branch stack builder: WN flg(3) -> ball valve(8) -> blind flg(4) -
    def make_2in_flange(row_props, rating, label):
        f = pCmd.makeFlange(row_props, doOffset=True, rating=rating, fclass=FCLASS)
        f.Label = label
        return f

    def build_branch_stack(weld_obj, weld_port, tag):
        """Weld a 2" WN flange to weld_obj/weld_port, then valve + blind cap."""
        wn = make_2in_flange(wn_props(wn2, OD2 - 2.0 * THK2), SCH2,
                             "Flange WN 2in 300# (%s)" % tag)
        doc.recompute()
        pCmd.alignTwoPorts(wn, 1, weld_obj, weld_port)   # weld end -> outlet/elbow

        valve = pCmd.makeValve(
            [DN2, vlv["VType"].strip(), _f(vlv, "H"), _f(vlv, "Kv", 0.0), FCLASS, 0, 0],
            flgPropList=[bl2["PSize"].strip(), "BL", _f(bl2, "D"), _f(bl2, "t"),
                         _f(bl2, "f"), int(float(bl2["n"])), _f(bl2, "df"),
                         _f(bl2, "drf"), _f(bl2, "trf")],
            actuator="Handle")
        valve.Label = "Ball valve 2in 300# (%s)" % tag
        doc.recompute()
        pCmd.alignTwoPorts(valve, 1, wn, 0)              # valve -> flange raised face

        blind = make_2in_flange(bl_props(bl2), NORATE,
                                "Flange BL 2in 300# (%s)" % tag)
        doc.recompute()
        pCmd.alignTwoPorts(blind, 0, valve, 0)           # blind face -> valve far end
        doc.recompute()
        return wn, valve, blind

    # Left branch: straight up off the weldolet (no 2" elbow).
    build_branch_stack(outletL, 0, "L")

    # Right branch: weldolet (down) -> 2" LR elbow(7) turning -Z to +X, then stack.
    elbow2b = pCmd.makeElbow(
        [DN2, OD2, THK2, _f(el2, "BendAngle"), _f(el2, "BendRadius")],
        rating=SCH2)
    elbow2b.PRating = SCH2
    elbow2b.Label = "Elbow 2in Sch-XS 90LR (R branch)"
    doc.recompute()
    d0, d1 = elbow2b.PortDirections[0], elbow2b.PortDirections[1]
    Rb = _rot_two(d0, d1, Zhat, Xhat)   # inlet faces +Z (up to the weldolet), outlet +X
    elbow2b.Placement = Placement(_world(outletR, 0) - Rb.multVec(elbow2b.Ports[0]), Rb)
    doc.recompute()
    build_branch_stack(elbow2b, 1, "R")

    doc.recompute()

    # ---- View + save ------------------------------------------------------
    if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
        try:
            FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    # Save beside this macro file.  Never write into the Quetzal installation:
    # that is somebody else's checkout (see the guide, section 7.1).
    try:
        out_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        out_dir = os.getcwd()  # pasted into the console: no __file__ to anchor to
    out_path = os.path.join(out_dir, "make_iso_10in_300_branch_run.FCStd")
    doc.saveAs(out_path)

    # ---- Summary ----------------------------------------------------------
    FreeCAD.Console.PrintMessage(
        "\n=== Iso reconstruction (IMG_2150) ===\n"
        "  Main line: 10in (DN250) Sch-STD, 300#.  Branches: 2in (DN50) Sch-XS.\n"
        "  U-shape: flange A -> pipe1(+X) -> elbow1 -> pipe2(+Y) -> elbow2 -> flange B.\n"
        "  Work points: elbow1=%s  elbow2=%s   flange A face=%s\n"
        "  pipe1 (2'-6\", +X)  = %.1f mm   pipe2 (6'-0\", +Y) = %.1f mm\n"
        "  10in pipe ID = %.2f (OD %.2f - 2*thk %.2f);  WN flange bore = %.2f\n"
        "  Flange B raised face at %s (points -X)\n"
        "  Branches: LEFT weldolet up (+Z) on pipe1 @2'-0\"; RIGHT weldolet down\n"
        "            (-Z) @ pipe2 center -> 2in elbow -> +X.\n"
        "  Components: 2x pipe(1), 2x WN flg 10in(2), 2x WN flg 2in(3),\n"
        "              2x blind flg 2in(4), 2x weldolet(5), 2x elbow 10in(6),\n"
        "              1x elbow 2in(7), 2x ball valve(8)\n"
        "  Saved: %s\n"
        % (tuple(WP_elbow1), tuple(WP_elbow2), tuple(F_A),
           pipe1.Height.Value, pipe2.Height.Value,
           OD10 - 2 * THK10, OD10, THK10, OD10 - 2 * THK10,
           tuple(_world(flangeB, 0)), out_path))
    return doc


if __name__ == "__main__":
    build()
