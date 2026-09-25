# make_spool_8in_600_elbow.py
#
# Build (with the Quetzal FreeCAD workbench) an 8" 600# spool:
#
#   WN flange (600# RF, Sch-STD bore) -- 8" Sch-STD pipe (36") -- 8" Sch-STD
#   90 LR elbow -- 8" Sch-STD pipe (24") -- SO flange (600# RF)
#
# 8" NPS = DN200.  Units are mm (imperial input x 25.4).
# Both flange raised faces are left bare (no gaskets / bolts / blinds).
#
# RUN IN THE FreeCAD GUI (Macro -> Execute, or paste in the Python console).
# Quetzal's execute() methods need a GUI ViewObject, so this cannot run under
# freecadcmd.  See the guide (skills/quetzal-piping/).

import os
import sys

import FreeCAD

try:
    import FreeCADGui
    _HAS_GUI = True
except Exception:
    _HAS_GUI = False


# ---------------------------------------------------------------------------
# Bootstrap: find quetzal_env at the repo root, then the Quetzal workbench
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
# Helpers
# ---------------------------------------------------------------------------

_read_row = qenv.read_row   # row for PSize=... from tablez/<csv> (';', BOM)
_f = qenv.f                 # float from a CSV row, by column name


IN = 25.4             # mm per inch
DN = "DN200"          # 8" NPS
SCHED = "SCH-STD"     # pipe schedule -> Pipe_SCH-STD.csv, Elbow_SCH-STD_LR90.csv
FCLASS = "600lb"      # flange pressure class
NORATE = "No rating"  # PRating for non-WN flanges (matches insertFlangeForm)

L1 = 36 * IN          # 914.4 mm - pipe between the WN flange and the elbow
L2 = 24 * IN          # 609.6 mm - pipe between the elbow and the SO flange


# ---------------------------------------------------------------------------
# propList builders (map CSV columns by NAME, never by position)
# ---------------------------------------------------------------------------

def _pipe_props(length_mm):
    r = _read_row("Pipe_%s.csv" % SCHED, DN)
    return [DN, _f(r, "OD"), _f(r, "thk"), length_mm], _f(r, "OD"), _f(r, "thk")


def _wn_flange_props(pipe_OD, pipe_thk):
    r = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN)
    bore = pipe_OD - 2.0 * pipe_thk          # WN bore = pipe bore, per insertFlangeForm
    return [DN, "WN", _f(r, "D"), bore, _f(r, "df"), _f(r, "f"), _f(r, "t"),
            int(r["n"]), _f(r, "trf"), _f(r, "drf"), _f(r, "twn"), _f(r, "dwn"),
            _f(r, "ODp"), _f(r, "R"), _f(r, "T1"), 0, 0]


def _so_flange_props():
    r = _read_row("Flange_ASME-SO-RF-%s.csv" % FCLASS, DN)
    # SO table has no neck columns (twn/dwn/R) -> those propList slots are 0.
    return [DN, "SO", _f(r, "D"), _f(r, "d"), _f(r, "df"), _f(r, "f"), _f(r, "t"),
            int(r["n"]), _f(r, "trf"), _f(r, "drf"), 0, 0,
            _f(r, "ODp"), 0, _f(r, "T1"), 0, 0]


def _elbow_props():
    # NOTE: Elbow_SCH-STD_LR90.csv has a trailing "A" header column with no data
    # in the rows - read only OD/thk/BendAngle/BendRadius.
    r = _read_row("Elbow_%s_LR90.csv" % SCHED, DN)
    return [DN, _f(r, "OD"), _f(r, "thk"), _f(r, "BendAngle"), _f(r, "BendRadius")]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Spool_8in_SchSTD_600")

    # -- Pipe 1: 8" Sch-STD, 36" (stays at origin; everything mates to it) ---
    p1_props, OD, thk = _pipe_props(L1)
    pipe1 = pCmd.makePipe(SCHED, p1_props)
    pipe1.PRating = SCHED
    pipe1.Label = "Pipe 8in Sch-STD 36in"
    doc.recompute()

    # -- WN flange (600# RF, Sch-STD bore) on Port 0 of pipe 1 --------------
    wn = pCmd.makeFlange(_wn_flange_props(OD, thk), doOffset=True,
                         rating=SCHED, fclass=FCLASS)
    wn.Label = "Flange WN 8in 600# RF"
    doc.recompute()
    pCmd.alignTwoPorts(wn, 1, pipe1, 0)          # weld end -> pipe Port 0

    # -- 90 LR elbow on Port 1 of pipe 1 ------------------------------------
    elbow = pCmd.makeElbow(_elbow_props(), rating=SCHED)
    elbow.PRating = SCHED
    elbow.Label = "Elbow 8in Sch-STD 90LR"
    doc.recompute()
    pCmd.alignTwoPorts(elbow, 0, pipe1, 1)       # elbow inlet -> pipe Port 1

    # -- Pipe 2: 8" Sch-STD, 24", onto the elbow outlet ---------------------
    p2_props, _, _ = _pipe_props(L2)
    pipe2 = pCmd.makePipe(SCHED, p2_props)
    pipe2.PRating = SCHED
    pipe2.Label = "Pipe 8in Sch-STD 24in"
    doc.recompute()
    pCmd.alignTwoPorts(pipe2, 0, elbow, 1)       # pipe2 Port 0 -> elbow outlet

    # -- SO flange (600# RF) on Port 1 of pipe 2 ----------------------------
    so = pCmd.makeFlange(_so_flange_props(), doOffset=True,
                         rating=NORATE, fclass=FCLASS)
    so.Label = "Flange SO 8in 600# RF"
    doc.recompute()
    pCmd.alignTwoPorts(so, 1, pipe2, 1)          # SO pipe end -> pipe2 Port 1

    doc.recompute()

    try:
        if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
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
    out_path = os.path.join(out_dir, "make_spool_8in_600_elbow.FCStd")
    doc.saveAs(out_path)

    # -- Report / sanity checks (the guide section 8) ---------------------
    trf, T1 = wn.trf, wn.T1                      # raised face thk, hub height
    E = elbow.BendRadius                         # 90deg take-out = R*tan(45) = R
    leg1 = float(trf) + float(T1) + L1 + float(E)
    leg2 = float(E) + L2 + 2.0 * float(so.trf)
    FreeCAD.Console.PrintMessage(
        "\n=== 8in 600# Sch-STD elbow spool built ===\n"
        "  Flange: WN 8\" 600# RF, bore %.2f mm (= OD %.2f - 2 x thk %.2f)\n"
        "  Pipe 1: 8\" Sch-STD x %.1f mm (36\")\n"
        "  Elbow : 8\" Sch-STD 90 LR, BendRadius %.1f mm (take-out %.1f mm)\n"
        "  Pipe 2: 8\" Sch-STD x %.1f mm (24\")\n"
        "  Flange: SO 8\" 600# RF\n"
        "  Extents: leg 1 (WN face -> elbow work point) %.2f mm\n"
        "           leg 2 (elbow work point -> SO face)  %.2f mm\n"
        "  Checks : pipe1.Height=%s  pipe2.Height=%s  WN d=%.2f\n"
        "           wn.FlangeType=%s/%s  so.FlangeType=%s/%s\n"
        "  Saved : %s\n"
        % (float(wn.d), OD, thk, L1, float(elbow.BendRadius), float(E), L2,
           leg1, leg2, pipe1.Height, pipe2.Height, float(wn.d),
           wn.FlangeType, wn.FClass, so.FlangeType, so.FClass, out_path)
    )
    return doc


if __name__ == "__main__":
    build()
