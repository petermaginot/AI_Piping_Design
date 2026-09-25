# make_iso_3in_tee_run.py
#
# Reconstruct the piping model from the hand-drawn isometric IMG_2146.jpg with
# the Quetzal FreeCAD workbench.
#
# Routing (all 3" = DN80, Sch-STD unless noted):
#   SO flange 3" 600#  ->  48" run (+Y)  ->  90 LR elbow 3" Sch-STD
#        ->  36" run (+X)  ->  Tee 3" Sch-STD (equal).
#   The tee carries a WN flange 3" 600# RF on the branch (up, +Z) AND a second
#   identical WN flange on the far run end (+X).
#
# ISOMETRIC DIMENSIONING NOTE:
#   The two dimensions are fixed-axis distances measured to specific features,
#   NOT pipe cut lengths:
#     48" = +Y from the SO flange face to the elbow work point (where the two
#           elbow centerlines cross).
#     36" = +X from the elbow work point (centerline) to the FACE of the
#           weld-neck flange on the far tee run end.
#   Pipe cut lengths are derived by measuring the placed fittings' ports.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute, or paste in the Python console).
# Quetzal's execute() methods need a GUI ViewObject, so this cannot run under
# freecadcmd.  See the guide (skills/quetzal-piping/).

import os
import sys

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


def _read_row(csv_name, psize, branch=None):
    """Row for PSize=psize (and optional PSizeBranch=branch) from tablez/<csv_name>."""
    return qenv.read_row(csv_name, psize, PSizeBranch=branch)


_f = qenv.f                 # float from a CSV row, by column name


def _rot_two(a0, a1, b0, b1):
    """Rotation R such that R*a0 == b0 and R*a1 == b1.

    a0/a1 and b0/b1 are two direction pairs that share the same in-between angle
    (e.g. a fitting's two local port directions and the two world directions we
    want them to point).  Builds an orthonormal frame from each pair and returns
    the rotation that carries one frame onto the other.
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


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

IN = 25.4
DN = "DN80"                 # 3" NPS
SCHED = "SCH-STD"
FCLASS = "600lb"
NORATE = "No rating"

D48 = 48 * IN              # +Y work-point distance: flange face -> elbow WP
D36 = 36 * IN              # +X work-point distance: elbow WP -> tee WP

Xhat = Vector(1, 0, 0)     # 36" run, down-right on the iso
Yhat = Vector(0, 1, 0)     # 48" run, up-right on the iso
Zhat = Vector(0, 0, 1)     # tee branch, up


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Iso_3in_600_TeeRun")

    pipe_row = _read_row("Pipe_%s.csv" % SCHED, DN)
    OD, THK = _f(pipe_row, "OD"), _f(pipe_row, "thk")

    el_row = _read_row("Elbow_%s_LR90.csv" % SCHED, DN)
    tee_row = _read_row("Tee_%s.csv" % SCHED, DN, branch=DN)
    so_row = _read_row("Flange_ASME-SO-RF-%s.csv" % FCLASS, DN)
    wn_row = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN)

    # ---- Work points (mm) -------------------------------------------------
    # 48": SO flange face -> elbow work point, along +Y.
    # 36": elbow work point -> FACE of the far-run WN flange, along +X.  The tee
    # sits upstream of that face by C (tee run half-length) + the WN flange's
    # face-to-weld length (T1 + trf), so back the tee centerline out by that much.
    WP_elbow = Vector(0, 0, 0)
    WP_flangeFace = WP_elbow - Yhat * D48
    runFlangeFace = WP_elbow + Xhat * D36
    wn_face_to_weld = _f(wn_row, "T1") + _f(wn_row, "trf")
    WP_tee = runFlangeFace - Xhat * (_f(tee_row, "C") + wn_face_to_weld)

    # ---- Elbow: put its work point at WP_elbow, inlet -Y, outlet +X --------
    # The Quetzal Elbow's local port layout is not something to assume (its ports
    # sit on the two legs, not on a tidy local axis).  So read the ACTUAL local
    # port directions, orient them onto the desired world directions (inlet faces
    # the flange = -Y, outlet continues to the tee = +X), and anchor the elbow's
    # true work point (intersection of the two port centerlines) at WP_elbow.
    elbow = pCmd.makeElbow(
        [DN, OD, THK, _f(el_row, "BendAngle"), _f(el_row, "BendRadius")],
        rating=SCHED)
    elbow.PRating = SCHED
    elbow.Label = "Elbow 3in Sch-STD 90LR"
    doc.recompute()
    d0, d1 = elbow.PortDirections[0], elbow.PortDirections[1]
    wp_local = _line_intersect(elbow.Ports[0], d0, elbow.Ports[1], d1)
    Rel = _rot_two(d0, d1, Yhat * -1, Xhat)   # port0 -> -Y (flange), port1 -> +X (tee)
    elbow.Placement = Placement(WP_elbow - Rel.multVec(wp_local), Rel)
    doc.recompute()

    # ---- Tee at its work point --------------------------------------------
    # Local run along +/-Z (ports 0/1), branch +Y (port 2).  Want run along X,
    # branch up (+Z): localZ->+X, localY->+Z, localX->+Y.
    tee = pCmd.makeTee(
        [DN, _f(tee_row, "OD"), _f(tee_row, "OD2"), _f(tee_row, "thk"),
         _f(tee_row, "thk2"), _f(tee_row, "C"), _f(tee_row, "M"), DN],
        rating=SCHED)
    tee.PRating = SCHED
    tee.Label = "Tee 3in Sch-STD"
    tee.Placement = Placement(
        WP_tee, Rotation(Vector(0, 1, 0), Vector(0, 0, 1), Vector(1, 0, 0)))
    doc.recompute()

    # ---- SO flange: face at the flange work point, pipe axis +Y -----------
    so = pCmd.makeFlange(
        [DN, "SO", _f(so_row, "D"), _f(so_row, "d"), _f(so_row, "df"),
         _f(so_row, "f"), _f(so_row, "t"), int(so_row["n"]),
         _f(so_row, "trf"), _f(so_row, "drf"), 0, 0, _f(so_row, "ODp"),
         0, _f(so_row, "T1"), 0, 0],
        doOffset=True, rating=NORATE, fclass=FCLASS)
    so.Label = "Flange SO 3in 600#"
    # Orient so the flange pipe axis (local +Z) points +Y, then translate so its
    # raised face (port 0) sits exactly on the flange work point.
    so_rot = Rotation(Vector(0, 0, 1), Yhat)
    so.Placement = Placement(WP_flangeFace - so_rot.multVec(so.Ports[0]), so_rot)
    doc.recompute()

    # ---- Two WN flanges on the tee: branch (port 2, up) and far run (port 1) --
    def make_wn(label):
        f = pCmd.makeFlange(
            [DN, "WN", _f(wn_row, "D"), OD - 2.0 * THK, _f(wn_row, "df"),
             _f(wn_row, "f"), _f(wn_row, "t"), int(wn_row["n"]),
             _f(wn_row, "trf"), _f(wn_row, "drf"), _f(wn_row, "twn"),
             _f(wn_row, "dwn"), _f(wn_row, "ODp"), _f(wn_row, "R"),
             _f(wn_row, "T1"), 0, 0],
            doOffset=True, rating=SCHED, fclass=FCLASS)
        f.Label = label
        return f

    wn_branch = make_wn("Flange WN 3in 600# RF (branch)")
    wn_run = make_wn("Flange WN 3in 600# RF (run end)")
    doc.recompute()
    pCmd.alignTwoPorts(wn_branch, 1, tee, 2)   # weld end -> branch (up, +Z)
    pCmd.alignTwoPorts(wn_run, 1, tee, 1)      # weld end -> far run end (+X)

    # ---- Fill the two straight pipes to span the measured port gaps --------
    def _world(obj, port):
        return obj.Placement.multVec(obj.Ports[port])

    # Pipe 1 (+Y): SO flange weld end (port 1) -> elbow inlet (port 0)
    p1_start = _world(so, 1)
    p1_len = (_world(elbow, 0) - p1_start).Length
    pipe1 = pCmd.makePipe(SCHED, [DN, OD, THK, p1_len], pos=p1_start, Z=Yhat)
    pipe1.PRating = SCHED
    pipe1.Label = "Pipe 3in Sch-STD (48in run)"

    # Pipe 2 (+X): elbow outlet (port 1) -> tee run end facing elbow (port 0)
    p2_start = _world(elbow, 1)
    p2_len = (_world(tee, 0) - p2_start).Length
    pipe2 = pCmd.makePipe(SCHED, [DN, OD, THK, p2_len], pos=p2_start, Z=Xhat)
    pipe2.PRating = SCHED
    pipe2.Label = "Pipe 3in Sch-STD (36in run)"

    doc.recompute()

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
    out_path = os.path.join(out_dir, "make_iso_3in_tee_run.FCStd")
    doc.saveAs(out_path)

    run_face_x = _world(wn_run, 0).x   # WN run-flange raised face, on +X
    FreeCAD.Console.PrintMessage(
        "\n=== Iso reconstruction (IMG_2146) ===\n"
        "  Work points: SO flangeFace=%s  elbow=%s  tee=%s\n"
        "  48in dist (flange face->elbow WP, +Y) = %.1f mm\n"
        "  36in dist (elbow WP->run WN flange face, +X) = %.1f mm\n"
        "  Pipe cut lengths: run1=%.1f mm  run2=%.1f mm\n"
        "  Components: SO flange, 90LR elbow, Tee, 2x WN flange (branch up +Z\n"
        "              and far run end +X), 2 pipes\n"
        "  Saved: %s\n"
        % (tuple(WP_flangeFace), tuple(WP_elbow), tuple(WP_tee),
           (WP_elbow - WP_flangeFace).Length, run_face_x - WP_elbow.x,
           p1_len, p2_len, out_path))
    return doc


if __name__ == "__main__":
    build()
