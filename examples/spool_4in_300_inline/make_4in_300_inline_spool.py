# make_4in_300_inline_spool.py
#
# Build (with the Quetzal FreeCAD workbench) an in-line spool:
#
#   [blind flange | bolts+gasket] = WN flange -- 4" Sch40 pipe (36", with a
#   1" 3000# straight sockolet 16" from Port 0 @ 90deg) -- 4" Sch-STD 90 LR
#   elbow -- 4" Sch40 pipe (72") -- SO flange = [bolts+gasket | blind flange]
#
# 4" NPS = DN100.  Units are mm (imperial input x 25.4).
#
# RUN IN THE FreeCAD GUI (Macro -> Execute, or paste in the Python console).
# Quetzal's execute() methods need a GUI ViewObject, so this cannot run under
# freecadcmd.  See the guide (docs/freecad-quetzal-guide.md).

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


IN = 25.4  # mm per inch
DN = "DN100"          # 4" NPS
FCLASS = "300lb"      # flange / gasket / bolt pressure class
NORATE = "No rating"  # PRating for non-WN flanges (matches insertFlangeForm)


# ---------------------------------------------------------------------------
# propList builders (map CSV columns by NAME, never by position)
# ---------------------------------------------------------------------------

def _pipe_props(sched, length_mm):
    r = _read_row("Pipe_%s.csv" % sched, DN)
    return [DN, _f(r, "OD"), _f(r, "thk"), length_mm], _f(r, "OD"), _f(r, "thk")


def _wn_flange_props(pipe_OD, pipe_thk):
    r = _read_row("Flange_ASME-WN-RF-%s.csv" % FCLASS, DN)
    bore = pipe_OD - 2.0 * pipe_thk          # WN bore = pipe bore, per insertFlangeForm
    return [DN, "WN", _f(r, "D"), bore, _f(r, "df"), _f(r, "f"), _f(r, "t"),
            int(r["n"]), _f(r, "trf"), _f(r, "drf"), _f(r, "twn"), _f(r, "dwn"),
            _f(r, "ODp"), _f(r, "R"), _f(r, "T1"), 0, 0]


def _so_flange_props():
    r = _read_row("Flange_ASME-SO-RF-%s.csv" % FCLASS, DN)
    return [DN, "SO", _f(r, "D"), _f(r, "d"), _f(r, "df"), _f(r, "f"), _f(r, "t"),
            int(r["n"]), _f(r, "trf"), _f(r, "drf"), 0, 0,
            _f(r, "ODp"), 0, _f(r, "T1"), 0, 0]


def _bl_flange_props():
    r = _read_row("Flange_ASME-BL-RF-%s.csv" % FCLASS, DN)
    # Blind: no bore, no neck.
    return [DN, "BL", _f(r, "D"), 0, _f(r, "df"), _f(r, "f"), _f(r, "t"),
            int(r["n"]), _f(r, "trf"), _f(r, "drf"), 0, 0, 0, 0, 0, 0, 0]


def _elbow_props():
    r = _read_row("Elbow_SCH-STD_LR90.csv", DN)
    return [DN, _f(r, "OD"), _f(r, "thk"), _f(r, "BendAngle"), _f(r, "BendRadius")]


def _outlet_props():
    # 1" (DN25) straight (Ang=0), socket-weld sockolet on the 4" run.
    r = _read_row("Outlet_3000lb.csv", "DN25", Ang="0")
    # makeOutlet order: [rating, DN, OD, thk, A, B, endType, angle, E]
    return ["3000lb", "DN25", _f(r, "OD"), _f(r, "thk"),
            _f(r, "A"), _f(r, "B"), r["Conn"].strip(),
            int(r["Ang"]), _f(r, "E")]


def _gasket_props():
    r = _read_row("Gasket_%s.csv" % FCLASS, DN)
    return ([DN, FCLASS, _f(r, "IRID"), _f(r, "SEID"), _f(r, "SEOD"),
             _f(r, "CROD"), _f(r, "SEthk"), _f(r, "Rthk")], _f(r, "SEthk"))


def _bolt_props(se_thk):
    r = _read_row("Bolt_%s.csv" % FCLASS, DN)
    return [DN, FCLASS, _f(r, "dBolt"), _f(r, "dNut"), _f(r, "tNut"),
            _f(r, "df"), int(r["n"]), _f(r, "lBolt"), se_thk]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build():
    doc = FreeCAD.newDocument("Spool_4in_Sch40_300")

    # -- Pipe 1: 4" Sch40, 36" (stays at origin; everything mates to it) ----
    p1_props, OD, thk = _pipe_props("SCH-40", 36 * IN)
    pipe1 = pCmd.makePipe("SCH-40", p1_props)
    pipe1.PRating = "SCH-40"
    pipe1.Label = "Pipe 4in Sch40 36in"
    doc.recompute()

    # -- 1" 3000# straight sockolet, 16" from Port 0, clocked at 90deg ------
    # phi_deg = circumferential position on the pipe (90deg -> local +Y).
    # Change phi_deg to reorient the branch around the pipe axis.
    pos, rot = pCmd.outletPlacementOnPipe(pipe1, t=16 * IN, phi_deg=90.0)
    outlet = pCmd.makeOutlet(_outlet_props(), pos, rot, carrierOD=OD)
    outlet.Label = "Sockolet 1in 3000#"

    # -- WN flange (300#) on Port 0 of pipe 1 -------------------------------
    wn = pCmd.makeFlange(_wn_flange_props(OD, thk), doOffset=True,
                         rating="SCH-40", fclass=FCLASS)
    wn.Label = "Flange WN 4in 300#"
    doc.recompute()
    pCmd.alignTwoPorts(wn, 1, pipe1, 0)          # weld end -> pipe Port 0

    # -- 90 LR elbow on Port 1 of pipe 1 ------------------------------------
    elbow = pCmd.makeElbow(_elbow_props(), rating="SCH-STD")
    elbow.PRating = "SCH-STD"
    elbow.Label = "Elbow 4in Sch-STD 90LR"
    doc.recompute()
    pCmd.alignTwoPorts(elbow, 0, pipe1, 1)       # elbow inlet -> pipe Port 1

    # -- Pipe 2: 4" Sch40, 72", onto the elbow outlet -----------------------
    p2_props, _, _ = _pipe_props("SCH-40", 72 * IN)
    pipe2 = pCmd.makePipe("SCH-40", p2_props)
    pipe2.PRating = "SCH-40"
    pipe2.Label = "Pipe 4in Sch40 72in"
    doc.recompute()
    pCmd.alignTwoPorts(pipe2, 0, elbow, 1)       # pipe2 Port 0 -> elbow outlet

    # -- SO flange (300#) on Port 1 of pipe 2 -------------------------------
    so = pCmd.makeFlange(_so_flange_props(), doOffset=True,
                         rating=NORATE, fclass=FCLASS)
    so.Label = "Flange SO 4in 300#"
    doc.recompute()
    pCmd.alignTwoPorts(so, 1, pipe2, 1)          # SO pipe end -> pipe2 Port 1

    # -- Gasket + bolts + blind flange on each raised face (flange Port 0) --
    def cap_off(flange, tag):
        gk_props, se_thk = _gasket_props()
        gasket = pCmd.makeGasket(gk_props)
        gasket.Label = "Gasket 4in 300# (%s)" % tag
        bolts = pCmd.makeBolts_Nuts(_bolt_props(se_thk))
        bolts.Label = "Bolts 4in 300# (%s)" % tag
        blind = pCmd.makeFlange(_bl_flange_props(), doOffset=True,
                                rating=NORATE, fclass=FCLASS)
        blind.Label = "Flange BL 4in 300# (%s)" % tag
        doc.recompute()
        pCmd.alignTwoPorts(gasket, 0, flange, 0)   # gasket face -> flange face
        pCmd.alignTwoPorts(bolts, 0, flange, 0)    # bolt set spans the joint
        doc.recompute()
        pCmd.alignTwoPorts(blind, 0, gasket, 1)    # blind face -> gasket far face
        return gasket, bolts, blind

    cap_off(wn, "WN end")
    cap_off(so, "SO end")

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
    out_path = os.path.join(out_dir, "make_4in_300_inline_spool.FCStd")
    doc.saveAs(out_path)

    FreeCAD.Console.PrintMessage(
        "\n=== 4in 300# in-line spool built ===\n"
        "  Pipe 1: 4\" Sch40 x 914.4 mm (36\")  + 1\" 3000# sockolet @406.4mm/90deg\n"
        "  Elbow : 4\" Sch-STD 90 LR\n"
        "  Pipe 2: 4\" Sch40 x 1828.8 mm (72\")\n"
        "  Ends  : WN flange (pipe1) & SO flange (pipe2), each with\n"
        "          gasket + bolts + blind flange (300# RF)\n"
        "  Saved : %s\n" % out_path
    )
    return doc


if __name__ == "__main__":
    build()
