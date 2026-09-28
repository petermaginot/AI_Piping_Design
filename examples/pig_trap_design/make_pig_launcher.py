# make_pig_launcher.py
#
# Add an NPS 6 x NPS 8, 600# pig launcher to the existing header in
# Header_to_make_piggable.FCStd (same folder), and save the result beside it as
# Header_with_pig_launcher.FCStd.  The input file is copied, never modified.
#
# Existing header (read from the file):
#   "Flange"    6" 600# WN, face +Y at (0, 123.75, 0)  -> trap valve
#   "Flange001" 4" 600# WN, face +Z on Tee001 branch    -> kicker valve
# Both carry a blind (Flange003 / Flange002) that is removed; their gaskets and
# stud sets are re-used for the valves.
#
# Launcher, walking from the trap valve to the closure (+Y):
#   trap valve 6" 600# trunnion ball (gearbox up, handwheel -X, out of the loop)
#   -> WN 6" -> minor pup 6" STD (carries the minor-side 1" sockolet)
#   -> eccentric reducer 8x6 STD, flat on bottom
#   -> major barrel 8" STD (pig space >= 8 ft, reducer weld -> kicker bore edge)
#   -> kicker tee 8x4 STD, branch up, welded direct to
#   -> WN 8" + gasket + studs + blind 8" (closure)
# Kicker (NPS 4 STD): kicker valve 4" 600# trunnion ball on Flange001 -> WN 4"
#   -> LR90 welded direct -> one horizontal leg skewed in plan -> LR90 down
#   -> drop pipe -> WN 4" flange pair (break-out joint) -> kicker tee branch.
# Low-point drain: 2" XS weldolet on the barrel bottom at mid-length -> WN 2"
#   welded direct -> 2" 600# ball valve -> blind 2".
# Barrel vent: 1" sockolet on the barrel top at mid-length -> nipple -> 1"
#   threaded vent valve.
# Vents + equalization: 1" sockolet on the minor pup top and on the kicker leg
#   top (the high point behind the pig) -> nipple -> SW tee -> nipple -> 1"
#   threaded vent valve (outlet left open for a plug); the tee branches are
#   joined by the 1" equalization line with a 1" ball valve (threaded-body
#   dimensions modelled socket-weld: no SW valve table exists) and a 1" socket
#   union centred in the lower horizontal pipe.
# Small bore uses pre-cut nipple lengths (3/4/6/12") wherever a length is
#   free: [P18] 6", [P17] 12", all vent nipples 3".  [P14]/[P15] and [P16]
#   are fixed by the tap locations and are cut to suit.
#
# Every object, existing and new, gets a typed mark ([F1], [P1], ...) numbered
# along an explicit walk order (WALK below).
#
# Weld-inches = sum of welds x NPS OD in inches, an olet-to-run weld counted at
# the branch OD.  The report prints the tally.
#
# Specs: flanges 600# RF; pipe Sch-STD 3" and up, Sch-XS 2" and under;
# small bore 3000# socket weld.  Units mm.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute).  Quetzal's execute() methods need a
# GUI ViewObject, so this cannot run under freecadcmd.  See skills/quetzal-piping/.

import math
import os
import shutil
import sys
from collections import Counter

import FreeCAD
from FreeCAD import Placement, Rotation, Vector

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

HERE = os.path.join(_ROOT, "examples", "pig_trap_design")
SRC = os.path.join(HERE, "Header_to_make_piggable.FCStd")
OUT = os.path.join(HERE, "Header_with_pig_launcher.FCStd")


# ---------------------------------------------------------------------------
# Design inputs -- the only typed numbers; every dimension comes from tablez/
# ---------------------------------------------------------------------------

IN = 25.4
DIMS = dict(
    PIG_LEN=8 * 12 * IN,  # longest pig, 8 ft
    GAP=4 * IN,           # min circ. weld -> olet toe, and olet toe -> olet toe
    FCLASS="600lb",
    SW="3000lb",
    NIP_L=3 * IN,         # cut length of the socket nipples
    # Pre-cut nipple lengths stocked for NPS 2 and smaller.  Where a segment's
    # length is free, it takes one of these; the others absorb the difference.
    STD_NIPPLES=(3 * IN, 4 * IN, 6 * IN, 12 * IN),
    EQ_TOP_L=6 * IN,      # [P18] major tee -> top SW ell: 6" std nipple
    EQ_UPPER_L=12 * IN,   # [P17] top SW ell -> eq valve: 12" std nipple
    T_DRAIN_FRAC=0.5,     # drain weldolet station, fraction of major pipe length
    T_BVENT_FRAC=0.5,     # barrel vent sockolet station, same
)
DN_MIN, DN_MAJ, DN_K, DN_DR, DN_V = "DN150", "DN200", "DN100", "DN50", "DN25"
SCH = {"DN200": "SCH-STD", "DN150": "SCH-STD", "DN100": "SCH-STD",
       "DN50": "SCH-XS", "DN25": "SCH-XS"}
NPS_OD_IN = {"DN200": 8.625, "DN150": 6.625, "DN100": 4.5, "DN50": 2.375,
             "DN25": 1.315}

# Existing objects in the header file
EXIST = dict(trap_gasket="Gasket001", kick_gasket="Gasket",
             blinds=("Flange003", "Flange002"))

# What each existing object is.  The original label is kept after the mark so
# the names used before ("Flange", "Flange001") still find the part.
ORIG_DESC = {
    "Tube004": "Pipe 6in STD (upstream riser)",
    "Elbow001": "Elbow 6in LR90 (upstream riser)",
    "Outlet001": "Sockolet 1/2in 3000# (header vent, upstream elbow)",
    "Tube007": "Nipple 1/2in XS (header vent, upstream elbow)",
    "Valve002": "Vent valve 1/2in threaded (header, upstream elbow)",
    "Tee001": "Tee 6x4 STD (kicker takeoff)",
    "Tube005": "Pipe 6in STD (bypass)",
    "Flange005": "WN 6in 600# (bypass valve, kicker side)",
    "Gasket003": "Gasket DN150 600# (bypass valve, kicker side)",
    "Bolts_Nuts003": "Studs DN150 600# (bypass valve, kicker side)",
    "Valve": "Bypass valve 6in 600# ball",
    "Gasket002": "Gasket DN150 600# (bypass valve, trap side)",
    "Bolts_Nuts002": "Studs DN150 600# (bypass valve, trap side)",
    "Flange004": "WN 6in 600# (bypass valve, trap side)",
    "Tee": "Tee 6in STD (trap tie-in)",
    "Tube": "Pipe 6in (downstream)",
    "Outlet": "Sockolet 1in 3000# (header vent, downstream pipe)",
    "Tube006": "Nipple 1in XS (header vent, downstream pipe)",
    "Valve001": "Vent valve 1in threaded (header, downstream pipe)",
    "Elbow": "Elbow 6in LR90 (downstream riser)",
    "Tube003": "Pipe 6in (downstream riser)",
    "Flange": "WN 6in 600# (trap valve, header side)",
    "Gasket001": "Gasket DN150 600# (trap valve, header side)",
    "Bolts_Nuts001": "Studs DN150 600# (trap valve, header side)",
    "Flange001": "WN 4in 600# (kicker valve, header side)",
    "Gasket": "Gasket DN100 600# (kicker valve, header side)",
    "Bolts_Nuts": "Studs DN100 600# (kicker valve, header side)",
}

# Mark numbering order.  Existing objects by FreeCAD Name, new ones by build key.
WALK = [
    # header, upstream riser -> kicker takeoff -> bypass -> trap tie-in -> downstream
    "Tube004", "Elbow001", "Outlet001", "Tube007", "Valve002", "Tee001",
    "Tube005", "Flange005", "Gasket003", "Bolts_Nuts003", "Valve",
    "Gasket002", "Bolts_Nuts002", "Flange004", "Tee",
    "Tube", "Outlet", "Tube006", "Valve001", "Elbow", "Tube003",
    # trap valve -> barrel -> closure
    "Flange", "Gasket001", "Bolts_Nuts001", "trap", "gT", "bT", "wn6", "pup",
    "red", "maj", "ktee", "wn8", "g8", "b8", "bl8",
    # kicker, header -> barrel
    "Flange001", "Gasket", "Bolts_Nuts", "kv", "gK", "bK", "wn4v", "e1", "ph",
    "e2", "pd", "wn4d", "gKT", "bKT", "wn4t",
    # barrel drain and vent
    "odr", "wn2", "gD1", "bD1", "dv", "gD2", "bD2", "bl2",
    "soB", "n1B", "vB",
    # vent/eq: minor stack, eq line minor -> major, major stack
    "soN", "n1N", "teeN", "n2N", "vN",
    "pB2", "un", "pB1", "eB", "pL", "eqv", "pU", "eA", "pA",
    "teeM", "n1M", "soM", "n2M", "vM",
]

PREFIX = {"Pipe": "P", "Flange": "F", "Valve": "V", "Gasket": "G",
          "Bolts_Nuts": "B", "Outlet": "O", "Tee": "T", "SocketTee": "T",
          "Elbow": "E", "SocketEll": "E", "Reduct": "R", "SocketUnion": "N",
          "Cap": "C", "SocketCap": "C"}

Xh, Yh, Zh = Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)
val = qenv.val


def row(csv_name, psize, **match):
    return qenv.read_row(csv_name, psize, **match)


def f(r, key, default=0.0):
    return qenv.f(r, key, default)


def wpos(o, i):
    return o.Placement.multVec(o.Ports[i])


def wdir(o, i):
    d = o.Placement.Rotation.multVec(o.PortDirections[i])
    d.normalize()
    return d


def rot_two(a0, a1, b0, b1):
    """Rotation R with R*a0 == b0 and R*a1 == b1 (a0/a1 and b0/b1 equal angle)."""
    def frame(u, v):
        x = Vector(u); x.normalize()
        z = x.cross(Vector(v)); z.normalize()
        return Rotation(x, z.cross(x), z)
    return frame(b0, b1).multiply(frame(a0, a1).inverted())


def phi_for_dir(pipe, desired):
    R = pipe.Placement.Rotation
    ex, ey = R.multVec(Xh), R.multVec(Yh)
    return math.degrees(math.atan2(desired.dot(ey), desired.dot(ex)))


def ODt(dn):
    r = row("Pipe_%s.csv" % SCH[dn], dn)
    return f(r, "OD"), f(r, "thk")


def outlet_row(dn, rating):
    return row("Outlet_%s.csv" % rating, dn, Ang="0")


def bl_row(dn):
    return row("Flange_ASME-BL-RF-%s.csv" % DIMS["FCLASS"], dn)


# ---------------------------------------------------------------------------
# Builder: wraps the pCmd makers and records parts, joints and welds
# ---------------------------------------------------------------------------

class Build(object):
    def __init__(self, doc):
        self.doc = doc
        self.parts = {}      # build key -> object (for WALK and the checks)
        self.new = []
        self.joints, self.welds = [], []

    def rc(self):
        self.doc.recompute()

    def reg(self, key, o, label):
        if key in self.parts:
            raise KeyError("duplicate build key %s" % key)
        o.Label = label
        self.parts[key] = o
        self.new.append(o)
        return o

    def joint(self, name, a, ia, b, ib):
        self.joints.append((name, a, ia, b, ib))

    def weld(self, dn, what):
        self.welds.append((dn, what))

    # -- makers ------------------------------------------------------------
    def pipe(self, key, dn, L, label):
        OD, thk = ODt(dn)
        p = pCmd.makePipe(SCH[dn], [dn, OD, thk, L])
        p.PRating = SCH[dn]
        self.rc()
        return self.reg(key, p, label)

    def wn(self, key, dn, label):
        r = row("Flange_ASME-WN-RF-%s.csv" % DIMS["FCLASS"], dn)
        OD, thk = ODt(dn)
        props = [dn, "WN", f(r, "D"), OD - 2 * thk, f(r, "df"), f(r, "f"),
                 f(r, "t"), int(r["n"]), f(r, "trf"), f(r, "drf"), f(r, "twn"),
                 f(r, "dwn"), f(r, "ODp"), f(r, "R"), f(r, "T1"), 0, 0]
        o = pCmd.makeFlange(props, doOffset=True, rating=SCH[dn],
                            fclass=DIMS["FCLASS"])
        self.rc()
        return self.reg(key, o, label)

    def blind(self, key, dn, label):
        r = bl_row(dn)
        props = [dn, "BL", f(r, "D"), 0, f(r, "df"), f(r, "f"), f(r, "t"),
                 int(r["n"]), f(r, "trf"), f(r, "drf"), 0, 0, 0, 0, 0, 0, 0]
        o = pCmd.makeFlange(props, doOffset=True, rating="No rating",
                            fclass=DIMS["FCLASS"])
        self.rc()
        return self.reg(key, o, label)

    def bolt_up(self, gkey, bkey, face_obj, face_port, dn, tag):
        """Gasket + stud set on an open raised face; mate the next part to
        the returned gasket's port 1."""
        g_r = row("Gasket_%s.csv" % DIMS["FCLASS"], dn)
        b_r = row("Bolt_%s.csv" % DIMS["FCLASS"], dn)
        g = pCmd.makeGasket([dn, DIMS["FCLASS"], f(g_r, "IRID"), f(g_r, "SEID"),
                             f(g_r, "SEOD"), f(g_r, "CROD"), f(g_r, "SEthk"),
                             f(g_r, "Rthk")])
        self.rc()
        self.reg(gkey, g, "Gasket %s 600# (%s)" % (dn, tag))
        pCmd.alignTwoPorts(g, 0, face_obj, face_port)
        b = pCmd.makeBolts_Nuts([dn, DIMS["FCLASS"], f(b_r, "dBolt"),
                                 f(b_r, "dNut"), f(b_r, "tNut"), f(b_r, "df"),
                                 int(b_r["n"]), f(b_r, "lBolt"), f(g_r, "SEthk")])
        self.rc()
        self.reg(bkey, b, "Studs %s 600# (%s)" % (dn, tag))
        pCmd.alignTwoPorts(b, 0, face_obj, face_port)
        self.rc()
        return g

    def flanged_valve(self, key, dn, table, actuator, label):
        r, b = row(table, dn), bl_row(dn)
        o = pCmd.makeValve(
            [dn, r["VType"], f(r, "H"), f(r, "Kv"), r["Conn"],
             f(r, "BottomH"), f(r, "TopH")],
            flgPropList=[dn, "BL", f(b, "D"), f(b, "t"), f(b, "f"),
                         int(b["n"]), f(b, "df"), f(b, "drf"), f(b, "trf")],
            actuator=actuator)
        self.rc()
        return self.reg(key, o, label)

    def thd_valve(self, key, dn, conn, label):
        r = row("Valve_Ball-Threaded.csv", dn)
        o = pCmd.makeValve([dn, r["Vtype"], f(r, "OD"), f(r, "ODBody"),
                            f(r, "H"), f(r, "E"), conn])
        self.rc()
        return self.reg(key, o, label)

    def ell_bw(self, key, dn, label):
        r = row("Elbow_%s_LR90.csv" % SCH[dn], dn)
        o = pCmd.makeElbow([dn, f(r, "OD"), f(r, "thk"), f(r, "BendAngle"),
                            f(r, "BendRadius")], rating=SCH[dn])
        o.PRating = SCH[dn] + "_LR90"
        self.rc()
        return self.reg(key, o, label)

    def tee_bw(self, key, dn, dn2, label):
        r = row("Tee_%s.csv" % SCH[dn], dn, PSizeBranch=dn2)
        o = pCmd.makeTee([dn, f(r, "OD"), f(r, "OD2"), f(r, "thk"), f(r, "thk2"),
                          f(r, "C"), f(r, "M"), dn2], rating=SCH[dn])
        o.PRating = SCH[dn]
        self.rc()
        return self.reg(key, o, label)

    def ecc_reducer(self, key, dn, dn2, label):
        r = row("Reduct_%s.csv" % SCH[dn], dn)
        idx = [s.strip() for s in r["PSize2"].split(">")].index(dn2)
        OD2 = float(r["OD2"].split(">")[idx])
        thk2 = float(r["thk2"].split(">")[idx])
        o = pCmd.makeReduct([dn, f(r, "OD"), OD2, f(r, "thk"), thk2,
                             f(r, "H"), dn2], conc=False, rating=SCH[dn])
        o.PRating = SCH[dn]
        self.rc()
        return self.reg(key, o, label)

    def outlet(self, key, dn, rating, carrier, t, out_dir, label):
        r = outlet_row(dn, rating)
        pos, rot = pCmd.outletPlacementOnPipe(carrier, t,
                                              phi_for_dir(carrier, out_dir))
        o = pCmd.makeOutlet([rating, dn, f(r, "OD"), f(r, "thk"), f(r, "A"),
                             f(r, "B"), r["Conn"], 0, f(r, "E")],
                            pos, rot, carrierOD=val(carrier.OD))
        self.rc()
        return self.reg(key, o, label)

    def sw_tee(self, key, dn, label):
        r = row("Tee_%s_SW.csv" % DIMS["SW"], dn, PSizeBranch=dn)
        o = pCmd.makeSocketTee([dn, dn, f(r, "OD"), f(r, "OD2"), f(r, "A"),
                                f(r, "C"), f(r, "D"), f(r, "E"), f(r, "G"),
                                r["Conn"]], rating=DIMS["SW"])
        o.PRating = DIMS["SW"]
        self.rc()
        return self.reg(key, o, label)

    def sw_ell(self, key, dn, label):
        r = row("Elbow_%s_SW.csv" % DIMS["SW"], dn, BendAngle="90")
        o = pCmd.makeSocketElbow([dn, f(r, "OD"), f(r, "BendAngle"), f(r, "A"),
                                  f(r, "C"), f(r, "D"), f(r, "E"), f(r, "G"),
                                  r["Conn"]], rating=DIMS["SW"])
        o.PRating = DIMS["SW"]
        self.rc()
        return self.reg(key, o, label)

    def sw_union(self, key, dn, label):
        # Union_<class>_SW.csv has no header row (skill §6): read positionally.
        r = row("Union_%s_SW.csv" % DIMS["SW"], dn,
                fieldnames=["PSize", "OD", "A", "C", "D", "E", "Conn"])
        o = pCmd.makeSocketUnion([dn, f(r, "OD"), f(r, "A"), f(r, "C"),
                                  f(r, "D"), f(r, "E"), r["Conn"]])
        o.PRating = DIMS["SW"]
        self.rc()
        return self.reg(key, o, label)

    # -- placement ---------------------------------------------------------
    def seat(self, v, port, mate, mate_port, ydir_world):
        """Put v's `port` on mate/mate_port, anti-parallel, with v's local +Y
        (actuator / lever) aimed at ydir_world."""
        flow = wdir(mate, mate_port)
        y = Vector(ydir_world)
        y = y - flow * y.dot(flow)
        if y.Length < 1e-6:
            raise RuntimeError("actuator direction is parallel to the flow axis")
        y.normalize()
        R = rot_two(Vector(v.PortDirections[port]), Vector(0, 1, 0), -flow, y)
        v.Placement = Placement(wpos(mate, mate_port) - R.multVec(v.Ports[port]), R)
        self.rc()

    def place_sw_ell(self, e, WP, out0, out1):
        a0, a1 = Vector(e.PortDirections[0]), Vector(e.PortDirections[1])
        assert abs(a0.getAngle(a1) - math.radians(90)) < 1e-6
        assert abs(out0.getAngle(out1) - math.radians(90)) < 1e-6
        e.Placement = Placement(WP, rot_two(a0, a1, out0, out1))  # WP = origin
        self.rc()

    def vent_stack(self, sfx, carrier, t, tag, branch_dir, handle_dir):
        """Sockolet on top of carrier at station t -> nipple -> SW tee (run
        vertical, branch along branch_dir) -> nipple -> threaded vent valve.
        Build keys so<sfx>, n1<sfx>, tee<sfx>, n2<sfx>, v<sfx>."""
        so = self.outlet("so" + sfx, DN_V, DIMS["SW"], carrier, t, Zh,
                         "Sockolet 1in 3000# (%s)" % tag)
        self.weld(DN_V, "sockolet - carrier (%s)" % tag)
        n1 = self.pipe("n1" + sfx, DN_V, DIMS["NIP_L"],
                       "Nipple 1in XS (%s, olet->tee)" % tag)
        pCmd.alignTwoPorts(n1, 0, so, 0); self.rc()
        self.joint("sockolet / nipple (%s)" % tag, n1, 0, so, 0)
        self.weld(DN_V, "sockolet - nipple (%s)" % tag)
        tee = self.sw_tee("tee" + sfx, DN_V, "SW tee 1in 3000# (%s vent/eq)" % tag)
        bd = Vector(branch_dir); bd.z = 0; bd.normalize()
        Rt = Rotation(bd.cross(Zh), bd, Zh)     # local Y -> branch, Z -> up
        tee.Placement = Placement(wpos(n1, 1) - Rt.multVec(tee.Ports[0]), Rt)
        self.rc()
        self.joint("nipple / tee (%s)" % tag, tee, 0, n1, 1)
        self.weld(DN_V, "nipple - tee (%s)" % tag)
        n2 = self.pipe("n2" + sfx, DN_V, DIMS["NIP_L"],
                       "Nipple 1in XS (%s, tee->vent valve, TOE)" % tag)
        pCmd.alignTwoPorts(n2, 0, tee, 1); self.rc()
        self.joint("tee / vent nipple (%s)" % tag, n2, 0, tee, 1)
        self.weld(DN_V, "tee - vent nipple (%s)" % tag)
        vv = self.thd_valve("v" + sfx, DN_V, "TH",
                            "Vent valve 1in threaded ball (%s)" % tag)
        self.seat(vv, 1, n2, 1, handle_dir)
        self.joint("vent nipple / vent valve (%s)" % tag, vv, 1, n2, 1)
        return so, tee, vv


# ---------------------------------------------------------------------------
# The launcher
# ---------------------------------------------------------------------------

def build(doc):
    B = Build(doc)
    G6 = doc.getObject(EXIST["trap_gasket"])
    G4 = doc.getObject(EXIST["kick_gasket"])
    for n in EXIST["blinds"]:
        doc.removeObject(n)
    B.rc()

    # -- trap valve and barrel spine ----------------------------------------
    trunnion = "Valve_Ball_Trunnion_%sRF.csv" % DIMS["FCLASS"]
    trap = B.flanged_valve("trap", DN_MIN, trunnion, "Gearbox",
                           "Trap valve 6in 600# trunnion ball")
    B.seat(trap, 1, G6, 1, Zh)                           # gearbox up
    B.joint("trap valve / Gasket001", trap, 1, G6, 1)
    gT = B.bolt_up("gT", "bT", trap, 0, DN_MIN, "trap valve, barrel side")
    wn6 = B.wn("wn6", DN_MIN, "WN 6in 600# (trap valve, barrel side)")
    pCmd.alignTwoPorts(wn6, 0, gT, 1); B.rc()
    B.joint("gasket / WN6", wn6, 0, gT, 1)

    B25 = f(outlet_row(DN_V, DIMS["SW"]), "B")
    L_MINOR = 2 * (DIMS["GAP"] + B25 / 2)                # one centred sockolet
    pup = B.pipe("pup", DN_MIN, L_MINOR, "Minor barrel 6in STD")
    pCmd.alignTwoPorts(pup, 0, wn6, 1); B.rc()
    B.joint("WN6 / minor pup", pup, 0, wn6, 1)
    B.weld(DN_MIN, "WN6 - minor pup")

    red = B.ecc_reducer("red", DN_MAJ, DN_MIN, "Ecc reducer 8x6 STD FOB")
    ax = wdir(pup, 1)
    R = Rotation(-Zh, (-ax).cross(-Zh), -ax)             # flat (local +X) -> -Z
    red.Placement = Placement(wpos(pup, 1) - R.multVec(red.Ports[1]), R)
    B.rc()
    B.joint("minor pup / reducer", red, 1, pup, 1)
    B.weld(DN_MIN, "minor pup - reducer")

    # Major pipe: pig space (reducer weld -> kicker bore edge) = PIG_LEN, with
    # the kicker tee welded straight to the closure WN.
    ODk, thkk = ODt(DN_K)
    ID_K = ODk - 2 * thkk
    kt_row = row("Tee_%s.csv" % SCH[DN_MAJ], DN_MAJ, PSizeBranch=DN_K)
    L_MAJOR = DIMS["PIG_LEN"] + ID_K / 2 - f(kt_row, "C")
    maj = B.pipe("maj", DN_MAJ, L_MAJOR, "Major barrel 8in STD")
    pCmd.alignTwoPorts(maj, 0, red, 0); B.rc()
    B.joint("reducer / major", maj, 0, red, 0)
    B.weld(DN_MAJ, "reducer - major barrel")

    ktee = B.tee_bw("ktee", DN_MAJ, DN_K, "Kicker tee 8x4 STD")
    Rk = Rotation(Zh.cross(ax), Zh, ax)                  # run along barrel, branch up
    ktee.Placement = Placement(wpos(maj, 1) - Rk.multVec(ktee.Ports[0]), Rk)
    B.rc()
    B.joint("major / kicker tee", ktee, 0, maj, 1)
    B.weld(DN_MAJ, "major barrel - kicker tee")
    wn8 = B.wn("wn8", DN_MAJ, "WN 8in 600# (closure)")
    pCmd.alignTwoPorts(wn8, 1, ktee, 1); B.rc()
    B.joint("kicker tee / WN8", wn8, 1, ktee, 1)
    B.weld(DN_MAJ, "kicker tee - WN8")
    g8 = B.bolt_up("g8", "b8", wn8, 0, DN_MAJ, "closure")
    bl8 = B.blind("bl8", DN_MAJ, "Blind 8in 600# (closure)")
    pCmd.alignTwoPorts(bl8, 0, g8, 1); B.rc()
    B.joint("closure gasket / blind", bl8, 0, g8, 1)

    # Flange pair on the tee branch: the kicker line's break-out joint.
    wn4t = B.wn("wn4t", DN_K, "WN 4in 600# (kicker tee flange pair, tee side)")
    pCmd.alignTwoPorts(wn4t, 1, ktee, 2); B.rc()
    B.joint("kicker tee / WN4 tee side", wn4t, 1, ktee, 2)
    B.weld(DN_K, "kicker tee - WN4")
    gKT = B.bolt_up("gKT", "bKT", wn4t, 0, DN_K, "kicker tee flange pair")
    wn4d = B.wn("wn4d", DN_K, "WN 4in 600# (kicker tee flange pair, drop side)")
    pCmd.alignTwoPorts(wn4d, 0, gKT, 1); B.rc()
    B.joint("gasket / WN4 drop side", wn4d, 0, gKT, 1)

    # -- kicker line --------------------------------------------------------
    kv = B.flanged_valve("kv", DN_K, trunnion, "Gearbox",
                         "Kicker valve 4in 600# trunnion ball")
    B.seat(kv, 1, G4, 1, Xh)                             # gearbox +X, out of loop
    B.joint("kicker valve / Gasket (Flange001)", kv, 1, G4, 1)
    gK = B.bolt_up("gK", "bK", kv, 0, DN_K, "kicker valve, kicker-line side")
    wn4v = B.wn("wn4v", DN_K, "WN 4in 600# (kicker valve, kicker-line side)")
    pCmd.alignTwoPorts(wn4v, 0, gK, 1); B.rc()
    B.joint("gasket / WN4 valve side", wn4v, 0, gK, 1)

    e1 = B.ell_bw("e1", DN_K, "Kicker ell 1 4in LR90 (up->skew)")
    BR = val(e1.BendRadius)
    d0, d1 = Vector(e1.PortDirections[0]), Vector(e1.PortDirections[1])
    assert abs(d0.getAngle(d1) - math.radians(90)) < 1e-6
    up_end = wpos(wn4v, 1)
    WP1 = up_end + Zh * BR                               # ell welded direct to WN4
    WP2 = Vector(wpos(wn4d, 1).x, wpos(wn4d, 1).y, WP1.z)  # over the tee branch
    d_h = WP2 - WP1; d_h.normalize()
    R1 = rot_two(d0, d1, -Zh, d_h)
    e1.Placement = Placement(up_end - R1.multVec(e1.Ports[0]), R1); B.rc()
    B.joint("WN4 / ell 1", e1, 0, wn4v, 1)
    B.weld(DN_K, "WN4 - ell 1")

    e2 = B.ell_bw("e2", DN_K, "Kicker ell 2 4in LR90 (skew->down)")
    c0, c1 = Vector(e2.PortDirections[0]), Vector(e2.PortDirections[1])
    wp_loc = Vector(e2.Ports[0]) - c0 * BR
    R2 = rot_two(c0, c1, -d_h, -Zh)
    e2.Placement = Placement(WP2 - R2.multVec(wp_loc), R2); B.rc()

    Lh = (wpos(e2, 0) - wpos(e1, 1)).Length
    ph = B.pipe("ph", DN_K, Lh, "Kicker skew leg 4in STD")
    pCmd.alignTwoPorts(ph, 0, e1, 1); B.rc()
    B.joint("ell 1 / skew leg", ph, 0, e1, 1)
    B.joint("skew leg / ell 2", ph, 1, e2, 0)
    B.weld(DN_K, "ell 1 - skew leg"); B.weld(DN_K, "skew leg - ell 2")
    pd = B.pipe("pd", DN_K, (wpos(e2, 1) - wpos(wn4d, 1)).Length,
                "Kicker drop 4in STD")
    pCmd.alignTwoPorts(pd, 0, e2, 1); B.rc()
    B.joint("ell 2 / drop", pd, 0, e2, 1)
    B.joint("drop / WN4 drop side", pd, 1, wn4d, 1)
    B.weld(DN_K, "ell 2 - drop"); B.weld(DN_K, "drop - WN4")

    # -- low-point drain, barrel bottom at mid-length -----------------------
    odr = B.outlet("odr", DN_DR, "Sch-XS", maj, L_MAJOR * DIMS["T_DRAIN_FRAC"], -Zh,
                   "Drain weldolet 2in XS on 8in")
    B.weld(DN_DR, "drain weldolet - barrel")
    wn2 = B.wn("wn2", DN_DR, "WN 2in 600# (drain)")
    pCmd.alignTwoPorts(wn2, 1, odr, 0); B.rc()
    B.joint("drain weldolet / WN2", wn2, 1, odr, 0)
    B.weld(DN_DR, "drain weldolet - WN2")
    gD1 = B.bolt_up("gD1", "bD1", wn2, 0, DN_DR, "drain valve, barrel side")
    dv = B.flanged_valve("dv", DN_DR, "Valve_Ball_%sRF.csv" % DIMS["FCLASS"],
                         "Handle", "Drain valve 2in 600# ball")
    B.seat(dv, 1, gD1, 1, -Xh)                           # lever -X, out of loop
    B.joint("gasket / drain valve", dv, 1, gD1, 1)
    gD2 = B.bolt_up("gD2", "bD2", dv, 0, DN_DR, "drain valve, outlet side")
    bl2 = B.blind("bl2", DN_DR, "Blind 2in 600# (drain outlet)")
    pCmd.alignTwoPorts(bl2, 0, gD2, 1); B.rc()
    B.joint("drain gasket / blind", bl2, 0, gD2, 1)

    # -- barrel high-point vent, barrel top at mid-length -------------------
    soB = B.outlet("soB", DN_V, DIMS["SW"], maj, L_MAJOR * DIMS["T_BVENT_FRAC"], Zh,
                   "Sockolet 1in 3000# (barrel vent)")
    B.weld(DN_V, "sockolet - barrel (barrel vent)")
    n1B = B.pipe("n1B", DN_V, DIMS["NIP_L"], "Nipple 1in XS (barrel vent, TOE)")
    pCmd.alignTwoPorts(n1B, 0, soB, 0); B.rc()
    B.joint("sockolet / nipple (barrel vent)", n1B, 0, soB, 0)
    B.weld(DN_V, "sockolet - nipple (barrel vent)")
    vB = B.thd_valve("vB", DN_V, "TH", "Vent valve 1in threaded ball (barrel vent)")
    B.seat(vB, 1, n1B, 1, -Xh)
    B.joint("nipple / vent valve (barrel vent)", vB, 1, n1B, 1)

    # -- vents + equalization ----------------------------------------------
    T_MINOR = L_MINOR / 2
    P_minor = wpos(pup, 0) + wdir(pup, 1) * T_MINOR
    leg0 = wpos(ph, 0)
    t_near = (Vector(P_minor.x, P_minor.y, leg0.z) - leg0).dot(d_h)
    T_MAJ_TAP = min(max(t_near, DIMS["GAP"] + B25 / 2),
                    Lh - DIMS["GAP"] - B25 / 2)          # keep GAP from both welds
    Q_leg = leg0 + d_h * T_MAJ_TAP
    to_minor = Vector(P_minor.x - Q_leg.x, P_minor.y - Q_leg.y, 0)
    d1 = to_minor - d_h * to_minor.dot(d_h); d1.normalize()

    soM, teeM, vM = B.vent_stack("M", ph, T_MAJ_TAP, "major side, on kicker leg",
                                 d1, d_h)
    # Top ell work point set by a std nipple [P18]: tee branch socket bottom +
    # nipple + the ell's centre-to-socket-bottom E.  [P14]/[P15] take up the rest.
    E_ELL = f(row("Elbow_%s_SW.csv" % DIMS["SW"], DN_V, BendAngle="90"), "E")
    WP_A = wpos(teeM, 2) + d1 * (DIMS["EQ_TOP_L"] + E_ELL)
    d2 = Vector(WP_A.x - P_minor.x, WP_A.y - P_minor.y, 0); d2.normalize()
    soN, teeN, vN = B.vent_stack("N", pup, T_MINOR, "minor side, on minor barrel",
                                 d2, -Xh)
    WP_teeN = teeN.Placement.Base

    eA = B.sw_ell("eA", DN_V, "SW ell 1in 3000# (eq line, top)")
    B.place_sw_ell(eA, WP_A, -d1, -Zh)
    pA = B.pipe("pA", DN_V, (wpos(eA, 0) - wpos(teeM, 2)).Length,
                "Nipple 1in XS 6in (major tee -> ell top)")
    pCmd.alignTwoPorts(pA, 0, teeM, 2); B.rc()
    B.joint("major tee / eq pipe", pA, 0, teeM, 2)
    B.joint("eq pipe / ell top", pA, 1, eA, 0)
    B.weld(DN_V, "major tee - eq pipe"); B.weld(DN_V, "eq pipe - ell top")

    WP_B = Vector(WP_A.x, WP_A.y, WP_teeN.z)
    dB = WP_teeN - WP_B; dB.normalize()
    eB = B.sw_ell("eB", DN_V, "SW ell 1in 3000# (eq line, bottom)")
    B.place_sw_ell(eB, WP_B, Zh, dB)

    rv = row("Valve_Ball-Threaded.csv", DN_V)
    Lv = f(rv, "H") - 2 * f(rv, "E")                     # port-to-port
    # Upper piece a std nipple; the lower piece [P16] is cut to the remainder.
    L_up = DIMS["EQ_UPPER_L"]
    if wpos(eA, 1).z - wpos(eB, 0).z - Lv - L_up < 50.0:
        raise RuntimeError("no room below the eq valve for a %.0f mm upper nipple" % L_up)
    pU = B.pipe("pU", DN_V, L_up, "Nipple 1in XS 12in (ell top -> eq valve)")
    pCmd.alignTwoPorts(pU, 0, eA, 1); B.rc()
    B.joint("ell top / eq pipe", pU, 0, eA, 1)
    B.weld(DN_V, "ell top - eq pipe"); B.weld(DN_V, "eq pipe - eq valve")
    eqv = B.thd_valve("eqv", DN_V, "SW", "Eq valve 1in ball (SW; threaded-body dims)")
    B.seat(eqv, 1, pU, 1, -d1)
    B.joint("eq pipe / eq valve", eqv, 1, pU, 1)
    pL = B.pipe("pL", DN_V, (wpos(eB, 0) - wpos(eqv, 0)).Length,
                "Eq pipe 1in XS (eq valve -> ell bottom)")
    pCmd.alignTwoPorts(pL, 0, eqv, 0); B.rc()
    B.joint("eq valve / eq pipe", pL, 0, eqv, 0)
    B.joint("eq pipe / ell bottom", pL, 1, eB, 0)
    B.weld(DN_V, "eq valve - eq pipe"); B.weld(DN_V, "eq pipe - ell bottom")

    # Lower horizontal eq pipe, split by a socket union at its middle.
    span = (wpos(teeN, 2) - wpos(eB, 1)).Length
    un_r = row("Union_%s_SW.csv" % DIMS["SW"], DN_V,
               fieldnames=["PSize", "OD", "A", "C", "D", "E", "Conn"])
    L_un = 2 * (f(un_r, "A") - f(un_r, "E"))             # union port-to-port
    L_half = (span - L_un) / 2
    pB1 = B.pipe("pB1", DN_V, L_half, "Eq pipe 1in XS (ell bottom -> union)")
    pCmd.alignTwoPorts(pB1, 0, eB, 1); B.rc()
    B.joint("ell bottom / eq pipe", pB1, 0, eB, 1)
    un = B.sw_union("un", DN_V, "Union 1in 3000# SW (eq line)")
    pCmd.alignTwoPorts(un, 0, pB1, 1); B.rc()
    B.joint("eq pipe / union", un, 0, pB1, 1)
    pB2 = B.pipe("pB2", DN_V, L_half, "Eq pipe 1in XS (union -> minor tee)")
    pCmd.alignTwoPorts(pB2, 0, un, 1); B.rc()
    B.joint("union / eq pipe", pB2, 0, un, 1)
    B.joint("eq pipe / minor tee", pB2, 1, teeN, 2)
    B.weld(DN_V, "ell bottom - eq pipe"); B.weld(DN_V, "eq pipe - union")
    B.weld(DN_V, "union - eq pipe"); B.weld(DN_V, "eq pipe - minor tee")
    B.rc()

    B.info = dict(d_h=d_h, ID_K=ID_K, L_MAJOR=L_MAJOR, B25=B25,
                  B50=f(outlet_row(DN_DR, "Sch-XS"), "B"), T_MAJ_TAP=T_MAJ_TAP)
    return B


def apply_marks(doc, B):
    """Typed mark on every object, numbered along WALK; assert full coverage."""
    objs = []
    for k in WALK:
        o = B.parts.get(k) or doc.getObject(k)
        if o is None:
            raise RuntimeError("WALK entry %s not found" % k)
        objs.append(o)
    names = [o.Name for o in objs]
    dup = [n for n, c in Counter(names).items() if c > 1]
    missing = [o.Name for o in doc.Objects if o.Name not in set(names)]
    if dup or missing:
        raise RuntimeError("WALK duplicates %s, missing %s" % (dup, missing))
    count = Counter()
    marks = []
    for k, o in zip(WALK, objs):
        pre = PREFIX[o.PType]
        count[pre] += 1
        mark = "[%s%d]" % (pre, count[pre])
        if k in ORIG_DESC:
            o.Label = "%s %s - %s" % (mark, k, ORIG_DESC[k])
        else:
            o.Label = "%s %s" % (mark, o.Label)
        marks.append(o.Label)
    return marks, count


# ---------------------------------------------------------------------------
# Verification and report (skill §8, §10.2, §11.6)
# ---------------------------------------------------------------------------

def report(B):
    P, I = B.parts, B.info
    out = ["", "=== Pig launcher 6x8 600# on existing header ==="]
    bad = 0
    for name, a, ia, b, ib in B.joints:
        gap = (wpos(a, ia) - wpos(b, ib)).Length
        dot = wdir(a, ia).dot(wdir(b, ib))
        ok = gap < 1e-6 and abs(dot + 1) < 1e-6
        bad += not ok
        out.append("  %-54s gap=%.6f dot=%+.6f%s"
                   % (name, gap, dot, "" if ok else "  <<FAIL"))
    out.append("  joints %d, failures %d" % (len(B.joints), bad))

    pup, maj, ktee = P["pup"], P["maj"], P["ktee"]
    out.append("  FOB bottoms: minor %.4f  major %.4f"
               % (wpos(pup, 0).z - val(pup.OD) / 2, wpos(maj, 0).z - val(maj.OD) / 2))
    ym = (ODt(DN_MAJ)[0] - 2 * ODt(DN_MAJ)[1]) / (ODt(DN_MIN)[0] - 2 * ODt(DN_MIN)[1])
    out.append("  major/minor ID ratio %.3f (need >= 1.20)" % ym)
    edge = ktee.Placement.Base.y - I["ID_K"] / 2
    ps = edge - wpos(maj, 0).y
    out.append("  pig space, reducer weld -> kicker bore edge: %.2f mm = %.2f in "
               "(need %.1f)" % (ps, ps / IN, DIMS["PIG_LEN"]))
    out.append("  incl. reducer + minor pup: %.2f mm = %.2f in"
               % (edge - wpos(pup, 0).y, (edge - wpos(pup, 0).y) / IN))

    def sta(o, pipe):
        return (o.Placement.Base - wpos(pipe, 0)).dot(wdir(pipe, 1))
    for key, pipe, Bw, lbl in [("odr", maj, I["B50"], "drain weldolet"),
                               ("soB", maj, I["B25"], "barrel vent sockolet"),
                               ("soN", pup, I["B25"], "minor sockolet"),
                               ("soM", P["ph"], I["B25"], "major sockolet")]:
        t, L = sta(P[key], pipe), val(pipe.Height)
        out.append("  %-20s t=%.2f (L/2=%.2f)  toe->weld %.2f / %.2f mm (min %.1f)"
                   % (lbl, t, L / 2, t - Bw / 2, L - t - Bw / 2, DIMS["GAP"]))
    un = P["un"]
    uc = (wpos(un, 0) + wpos(un, 1)) * 0.5
    ends = (wpos(P["pB1"], 0), wpos(P["pB2"], 1))
    out.append("  union centre -> pipe ends: %.3f / %.3f mm"
               % ((uc - ends[0]).Length, (uc - ends[1]).Length))
    out.append("  kicker skew %.3f deg from barrel axis, leg dz %.6f, drop %.2f mm"
               % (math.degrees(I["d_h"].getAngle(Yh)),
                  wpos(P["ph"], 1).z - wpos(P["ph"], 0).z, val(P["pd"].Height)))
    for k in ("trap", "kv", "dv", "vB"):
        v = P[k]
        y = v.Placement.Rotation.multVec(Yh)
        out.append("  %-34s actuator dir (%.0f, %.0f, %.0f)"
                   % (v.Label[:34], y.x, y.y, y.z))

    cnt = Counter(dn for dn, _ in B.welds)
    tot = 0.0
    for dn in ("DN200", "DN150", "DN100", "DN50", "DN25"):
        wi = cnt[dn] * NPS_OD_IN[dn]
        tot += wi
        out.append("  welds %-5s %2d x %.3f = %6.3f" % (dn, cnt[dn], NPS_OD_IN[dn], wi))
    out.append("  TOTAL weld-inches %.3f" % tot)
    out.append("  pipe cut lengths (NPS 2 and smaller flagged STD nipple / CUT):")
    small = ("DN15", "DN20", "DN25", "DN32", "DN40", "DN50")
    for o in B.new:
        if getattr(o, "PType", "") == "Pipe":
            L = val(o.Height)
            flag = ""
            if o.PSize in small:
                flag = ("STD nipple" if any(abs(L - s) < 0.01 for s in DIMS["STD_NIPPLES"])
                        else "CUT")
            out.append("    %-66s %8.2f mm %7.2f in  %s"
                       % (o.Label, L, L / IN, flag))
    FreeCAD.Console.PrintMessage("\n".join(out) + "\n")
    if bad:
        raise RuntimeError("%d joint(s) failed to close" % bad)
    return tot


def main():
    # Work on a copy: the input header file is never opened or modified.
    for d in list(FreeCAD.listDocuments().values()):
        if os.path.normcase(os.path.abspath(d.FileName or "")) == os.path.normcase(OUT):
            FreeCAD.closeDocument(d.Name)
    shutil.copyfile(SRC, OUT)
    doc = FreeCAD.openDocument(OUT)
    FreeCAD.setActiveDocument(doc.Name)
    doc.openTransaction("Pig launcher")
    B = build(doc)
    marks, count = apply_marks(doc, B)
    doc.commitTransaction()
    report(B)
    FreeCAD.Console.PrintMessage(
        "  marks: %s\n  %s\n" % (", ".join("%s x%d" % kv for kv in sorted(count.items())),
                                 "\n  ".join(marks)))
    if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.SendMsgToActiveView("ViewFit")
    doc.save()
    FreeCAD.Console.PrintMessage("  Saved: %s\n" % OUT)
    return doc


if __name__ == "__main__":
    main()
