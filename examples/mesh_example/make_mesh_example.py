# make_mesh_example.py
#
# Simplified FreeCAD model of the scanned scene in this folder
# (Untitled_Scan_11_23_55.dae, phone LiDAR, plus photos img_1.png / img_2.png):
#
#   * a 4" (NPS 4) stub out of a sump, built with Quetzal: SO flange at grade, Sch-40
#     riser, 3000# socket-weld 90 ell, Sch-40 pipe, 150# SO flange pair with
#     gasket and stud set, Sch-40 pipe, 3000# socket-weld cap;
#   * three 1" conduit runs (enclosure / A/C unit -> grade junction box),
#     built with Quetzal as DN25 Sch-40 pipe (same OD as 1" rigid conduit)
#     with 5-3/4" radius sweeps;
#   * Part solids for everything else: concrete slab and round pad, sump
#     hatch, Unistrut stand, stainless enclosure, A/C unit, disconnect box,
#     grade junction box and the grey pedestal box.
#   * the scan itself as a hidden mesh overlay (only if the .dae is present;
#     *.dae is gitignored).
#
# The scan, its texture and the photos are kept local only (gitignored); the
# script does not need the photos, and the scan is optional.
#
# Vegetation, the utility pole, the terrain, conduit fittings and anything
# below grade are not modelled.  See the source tags on every constant:
#   SCAN       measured from the scan mesh in the site frame (error bar given)
#   PHOTO      estimated from img_1 / img_2 by proportion
#   USER       stated by the user
#   CATALOGUE  read from the Quetzal tablez/ or a manufacturer standard
#   ASSUMED    not observable; a placeholder to replace with a tape measure
#
# Site frame: mm, Z up (gravity, from the phone's IMU; the enclosure front
# face is vertical to 0.05 deg).  Origin on the 4" riser axis, z = 0 the top
# of the round concrete pad at the riser.  +Y runs from the riser towards the
# enclosure, which faces -Y.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute).  Quetzal's execute() methods need
# a GUI ViewObject.  See skills/scan-to-model and skills/quetzal-piping.

import math
import os
import sys

import FreeCAD
import Part
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
_read_row = qenv.read_row   # row for PSize=... from tablez/<csv> (';', BOM)
_f = qenv.f                 # float from a CSV row, by column name

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.join(_ROOT, "examples", "mesh_example")

IN = 25.4
DOC_NAME = "MeshExample"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# -- Scan -> site transform (applied to the scan after its Y-up -> Z-up swap)
SCAN_FILE = os.path.join(_HERE, "Untitled_Scan_11_23_55.dae")
SCAN_ROT_DEG = 28.1036               # SCAN: squares the enclosure front to X
SCAN_SHIFT = (-320.0, 1400.0, 709.2)  # SCAN: riser axis to x=y=0, pad top to z=0

# -- Concrete -------------------------------------------------------------
SLAB_X = (-1800.0, -450.0)   # SCAN +-40: left edge crisp; right edge hidden under the pad
SLAB_Y = (140.0, 1650.0)     # SCAN: front edge crisp (+-20); back edge in vegetation (+-100)
SLAB_TOP = -27.0             # SCAN +-10 (falls ~1.5 deg; modelled level)
SLAB_THK = 150.0             # ASSUMED (front edge stands ~115 above the grass)
# Concrete sump disc.  Circle fitted to its edge against the vegetation on the
# two arcs the scan sees clearly (rms 34 mm); the (+X, -Y) side is buried by
# vegetation and the slab hides the (-X) side.
PAD_C = (453.0, 874.0)       # SCAN +-35
PAD_R = 1228.0               # SCAN +-35
PAD_TOP = 0.0                # SCAN: datum
PAD_THK = 200.0              # ASSUMED
PAD_HATCH_MARGIN = 0.0       # USER: the hatch sits entirely on the disc (checked)

# -- Sump hatch (frame + chequer plate, sitting on the disc) ----------------
HATCH_C = (820.3, 1106.1)    # SCAN +-30
HATCH_ANG = -46.8            # SCAN +-1: direction of the long side
HATCH_L, HATCH_W = 1350.0, 990.0   # SCAN +-30: far end where the flat plate meets grass
HATCH_TOP = 99.0             # SCAN +-15 (falls ~1.3 deg; modelled level)

# -- Enclosures (envelopes) --------------------------------------------------
ENCL_X = (-1600.0, -760.0)   # SCAN +-15: stainless enclosure
ENCL_Y = (1075.0, 1445.0)    # SCAN: front +-5, back face +-30
ENCL_Z = (559.0, 1659.0)     # SCAN: bottom +-15; top from up-facing facets +-40
AC_X = (-760.0, -420.0)      # SCAN +-20: A/C unit on the enclosure's +X side
AC_Y = (1090.0, 1410.0)      # SCAN +-20
AC_Z = (649.0, 1539.0)       # SCAN +-30
DISC_X = (-420.0, -330.0)    # PHOTO +-60: disconnect box on the A/C's +X face
DISC_Y = (1180.0, 1330.0)    # PHOTO +-60
DISC_Z = (1079.0, 1269.0)    # PHOTO +-80
# Grey pedestal box.  USER: it stands against the sump disc, one face tangent
# to the disc edge.  Solved from the disc: keep the scanned bearing of its
# centre from the disc centre, turn its W side radial (closest to the scanned
# 35 deg rotation), and put its centre at PAD_R + W/2.
PED_C_SCAN = (-94.0, 2085.0)  # SCAN +-20: scanned centre (now a check, not an input)
PED_L, PED_W = 200.0, 190.0   # SCAN +-25: L tangential, W radial
PED_BEARING = math.degrees(math.atan2(PED_C_SCAN[1] - PAD_C[1], PED_C_SCAN[0] - PAD_C[0]))
PED_ANG = PED_BEARING - 90.0  # L side along the tangent (scanned 35 +-3)
PED_C = (PAD_C[0] + (PAD_R + PED_W / 2) * math.cos(math.radians(PED_BEARING)),
         PAD_C[1] + (PAD_R + PED_W / 2) * math.sin(math.radians(PED_BEARING)))
PED_Z = (PAD_TOP - PAD_THK, 909.0)  # SCAN top +-10; USER: base down to the disc bottom
# Grade junction box.  Its front face runs parallel to the hatch's near edge
# (img_1); the conduits run along X and make a 45 deg bend into its -V face,
# so it is taken at -45 deg (scan -46.8..-50 +-3) for square 45 deg entries.
JBOX_C = (-148.6, 1549.8)    # SCAN +-40: centre
JBOX_ANG = -45.0             # PHOTO/SCAN +-3: direction of its A side
JBOX_A = 230.0               # PHOTO +-40: conduit face (scaled from the 1" conduit OD)
JBOX_B = 400.0               # PHOTO +-60: front face in img_1
JBOX_Z = (0.0, 175.0)        # PHOTO +-25 (USER: shorter than modelled); base on grade

# -- Unistrut stand (1-5/8" channel) -----------------------------------------
STRUT = 41.3                 # CATALOGUE: P1000 channel, 1-5/8"
# Four legs (USER: four in the photo).  Keyed by mark, so marks stay stable:
# S1 (an assumed front-left leg) was removed - it does not exist.  S6 (the
# front rail) went too: with S3 moved to the back, S2 is its only leg.
# mark: (x, y, top), top one of "rail", "enclosure bottom", "enclosure top"
STAND_POSTS = {
    2: (-1080.0, 1160.0, "enclosure bottom"),  # SCAN +-30: front leg under the enclosure
    # USER: S3 attaches to the back of the enclosure - the tall right-hand
    # post in img_1, up to the enclosure top.  x SCAN +-30.
    3: (-780.0, ENCL_Y[1] + STRUT / 2, "enclosure top"),
    4: (-1680.0, 1420.0, "rail"),  # SCAN x; y ASSUMED (scan blob at y 1500, in vegetation)
    5: (-1080.0, 1420.0, "rail"),  # SCAN x; y ASSUMED (scan blob at y 1600)
}
RAILS = {7: 1420.0}          # mark: y of a rail under the enclosure, between its legs

# -- 4" stub (Quetzal) ---------------------------------------------------------
DN_STUB = "DN100"              # USER: NPS 4 (corrected from NPS 3)
PIPE_SCHED = "SCH-40"        # USER
FLG_CLASS = "150lb"          # USER: 150# slip-on, raised face
SW_CLASS = "3000lb"          # USER: socket ell and socket cap (3000# assumed class)
Z_LEG = 322.0                # SCAN +-10: horizontal leg centreline
LEG_AZ = -44.4               # SCAN +-2: plan direction of the horizontal leg
JOINT_S = 212.0              # SCAN +-15: flange-pair gasket centre, from the riser axis
CAP_TIP_S = 330.0            # SCAN +-15: end of the cap, from the riser axis

# -- 1" conduit (Quetzal; DN25 Sch-40 = 1" rigid conduit OD) -------------------
DN1 = "DN25"
SWEEP_R = 5.75 * IN          # USER: NEC Ch. 9 Table 2, 1" one-shot sweep radius
# Four runs (img_1, img_2), each dropping out of the enclosure bottom and
# sweeping 90 deg to run along +X (parallel to the slab front edge, USER).
#  * K1, K2, K3 bend 45 deg into the junction box's -V face, square to it.
#  * K1 drops at the enclosure's front edge, runs high, and makes one jog
#    (USER) - a single diagonal leg that climbs back over K2, K3 and K4 and
#    drops to its run level - to enter the back end of the box face.
#  * K4 (USER) goes to the pedestal box instead: it runs low, under K1, turns
#    north past the box's west corner and enters the pedestal's face that
#    looks back at the enclosure, square to it.
# An LB conduit body at the box is not modelled.
# Junction-box runs: name, riser (x, y), run z, entry station along the box
# face from its centre (+ towards the hatch), and for a jogged run
# (z high, jog start x, jog end x, run y after the jog).
JBOX_RUNS = [
    ("K1", (-1170.0, 1110.0), 130.0, -70.0, (250.0, -800.0, -620.0, 1370.0)),  # PHOTO +-60
    ("K2", (-880.0, 1230.0), 60.0, 70.0, None),      # PHOTO +-50: front, lowest
    ("K3", (-835.0, 1280.0), 60.0, 25.0, None),      # PHOTO +-50
]
# Pedestal run: name, riser (x, y), run z, x of its turn north (clear of the box).
PED_RUN = ("K4", (-830.0, 1380.0), 40.0, -420.0)    # PHOTO +-50; z ASSUMED (under K1)

MIN_PIPE_ABS = 50.0          # short-pipe rule, skill quetzal-piping §9.2.2

# -- Colours -------------------------------------------------------------
C_CONC = (0.74, 0.73, 0.69)
C_STEEL = (0.52, 0.55, 0.58)
C_SS = (0.80, 0.80, 0.76)
C_GREY = (0.66, 0.68, 0.70)
C_STRUT = (0.72, 0.74, 0.76)
C_PIPE = (0.45, 0.47, 0.50)
C_CAP = (0.95, 0.95, 0.95)
C_COND = (0.78, 0.80, 0.82)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_dir(deg):
    t = math.radians(deg)
    return Vector(math.cos(t), math.sin(t), 0)


def _wpos(o, i):
    return o.Placement.multVec(o.Ports[i])


def _wdir(o, i):
    d = o.Placement.Rotation.multVec(o.PortDirections[i])
    d.normalize()
    return d


def _rot_two(a0, a1, b0, b1):
    """Rotation R with R*a0 == b0 and R*a1 == b1 (a0, a1 and b0, b1 at the same angle)."""
    def frame(u, v):
        x = Vector(u); x.normalize()
        z = x.cross(Vector(v)); z.normalize()
        return Rotation(x, z.cross(x), z)
    return frame(b0, b1).multiply(frame(a0, a1).inverted())


def _line_intersect(p0, d0, p1, d1):
    """Closest point between two lines (the fitting's work point)."""
    w = p0 - p1
    a, b, c = d0.dot(d0), d0.dot(d1), d1.dot(d1)
    d, e = d0.dot(w), d1.dot(w)
    den = a * c - b * b
    s = (b * e - c * d) / den
    t = (a * e - b * d) / den
    return (p0 + d0 * s + p1 + d1 * t) * 0.5


def _place_fitting(obj, wp, out0, out1):
    """Put a two-port fitting's work point at wp with its ports facing out0, out1."""
    d0, d1 = Vector(obj.PortDirections[0]), Vector(obj.PortDirections[1])
    wp_local = _line_intersect(Vector(obj.Ports[0]), d0, Vector(obj.Ports[1]), d1)
    R = _rot_two(d0, d1, out0, out1)
    obj.Placement = Placement(wp - R.multVec(wp_local), R)


def _seat_axial(obj, port, mate, mate_port, up_ref):
    """Seat an axisymmetric part (flange, gasket, stud set, pipe) whose ports
    lie on local Z, port `port` on mate/mate_port, with its local X rolled
    towards up_ref, so bolt holes on mated parts share one clock."""
    mdir = _wdir(mate, mate_port)
    ldir = Vector(obj.PortDirections[port])
    zdir = mdir * (-1.0 if ldir.z > 0 else 1.0)       # where local +Z must point
    x = Vector(up_ref) - zdir * Vector(up_ref).dot(zdir)
    if x.Length < 1e-6:
        x = Vector(1, 0, 0) - zdir * zdir.x
    x.normalize()
    R = Rotation(x, zdir.cross(x), zdir)
    obj.Placement = Placement(_wpos(mate, mate_port) - R.multVec(obj.Ports[port]), R)


def _solid(doc, name, label, shape, colour, container, transparency=0):
    o = doc.addObject("Part::Feature", name)
    o.Label = label
    o.Shape = shape
    if _HAS_GUI and o.ViewObject is not None:
        o.ViewObject.ShapeColor = colour
        o.ViewObject.Transparency = transparency
    container.addObject(o)
    return o


def _box(x, y, z):
    """Axis-aligned box from (lo, hi) pairs."""
    return Part.makeBox(x[1] - x[0], y[1] - y[0], z[1] - z[0],
                        Vector(x[0], y[0], z[0]))


def _rbox(c, ang, L, W, z0, z1):
    """Box L x W centred on plan point c, its L side along plan angle ang."""
    b = Part.makeBox(L, W, z1 - z0, Vector(-L / 2, -W / 2, z0))
    b.rotate(Vector(0, 0, 0), Vector(0, 0, 1), ang)
    b.translate(Vector(c[0], c[1], 0))
    return b


def _part(doc, name):
    p = doc.addObject("App::Part", name)
    p.Label = name
    return p


# -- propLists, CSV columns by name ------------------------------------------

def _pipe(dn, length, label, container, report):
    r = _read_row("Pipe_%s.csv" % PIPE_SCHED, dn)
    lim = min(MIN_PIPE_ABS, _f(r, "OD") / 2.0)
    if length < lim:
        report.append("SHORT PIPE %s: %.1f mm < %.1f mm (§9.2.2)" % (label, length, lim))
    if length <= 0:
        raise RuntimeError("%s has non-positive length %.2f" % (label, length))
    p = pCmd.makePipe(PIPE_SCHED, [dn, _f(r, "OD"), _f(r, "thk"), length])
    p.PRating = PIPE_SCHED
    p.Label = label
    container.addObject(p)
    return p


def _so_flange(label, container):
    r = _read_row("Flange_ASME-SO-RF-%s.csv" % FLG_CLASS, DN_STUB)
    props = [DN_STUB, "SO", _f(r, "D"), _f(r, "d"), _f(r, "df"), _f(r, "f"), _f(r, "t"),
             int(r["n"]), _f(r, "trf"), _f(r, "drf"), 0, 0,
             _f(r, "ODp"), 0, _f(r, "T1"), 0, 0]
    fl = pCmd.makeFlange(props, doOffset=True, rating="No rating", fclass=FLG_CLASS)
    fl.Label = label
    container.addObject(fl)
    return fl


def _gasket(label, container):
    r = _read_row("Gasket_%s.csv" % FLG_CLASS, DN_STUB)
    g = pCmd.makeGasket([DN_STUB, FLG_CLASS, _f(r, "IRID"), _f(r, "SEID"), _f(r, "SEOD"),
                         _f(r, "CROD"), _f(r, "SEthk"), _f(r, "Rthk")])
    g.Label = label
    container.addObject(g)
    return g, _f(r, "SEthk")


def _studs(label, sethk, container):
    r = _read_row("Bolt_%s.csv" % FLG_CLASS, DN_STUB)
    b = pCmd.makeBolts_Nuts([DN_STUB, FLG_CLASS, _f(r, "dBolt"), _f(r, "dNut"), _f(r, "tNut"),
                             _f(r, "df"), int(_f(r, "n")), _f(r, "lBolt"), sethk])
    b.Label = label
    container.addObject(b)
    return b


def _socket_ell(label, container):
    r = _read_row("Elbow_%s_SW.csv" % SW_CLASS, DN_STUB, BendAngle="90")
    e = pCmd.makeSocketElbow([DN_STUB, _f(r, "OD"), _f(r, "BendAngle"), _f(r, "A"), _f(r, "C"),
                              _f(r, "D"), _f(r, "E"), _f(r, "G"), r["Conn"]],
                             rating=SW_CLASS)
    e.PRating = SW_CLASS
    e.Label = label
    container.addObject(e)
    return e


def _socket_cap(label, container):
    r = _read_row("Cap_%s_SW.csv" % SW_CLASS, DN_STUB)
    c = pCmd.makeSocketCap([DN_STUB, _f(r, "OD"), _f(r, "A"), _f(r, "C"), _f(r, "E"), r["Conn"]])
    c.PRating = SW_CLASS
    c.Label = label
    container.addObject(c)
    return c


def _sweep(label, container):
    r = _read_row("Pipe_%s.csv" % PIPE_SCHED, DN1)
    e = pCmd.makeElbow([DN1, _f(r, "OD"), _f(r, "thk"), 90.0, SWEEP_R], rating=PIPE_SCHED)
    e.PRating = PIPE_SCHED
    e.Label = label
    container.addObject(e)
    return e


def _colour(objs, rgb):
    if not _HAS_GUI:
        return
    for o in objs:
        if o.ViewObject is not None:
            o.ViewObject.ShapeColor = rgb


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _build_site(doc, report):
    fnd = _part(doc, "Foundations")
    slab = _box(SLAB_X, SLAB_Y, (SLAB_TOP - SLAB_THK, SLAB_TOP))
    hatch = _rbox(HATCH_C, HATCH_ANG, HATCH_L, HATCH_W, PAD_TOP, HATCH_TOP)
    pad = Part.makeCylinder(PAD_R, PAD_THK, Vector(PAD_C[0], PAD_C[1], PAD_TOP - PAD_THK))
    pad = pad.cut(slab)                     # the disc runs in under the slab edge
    # Constraint (USER): the hatch sits entirely on the disc.
    c = Vector(PAD_C[0], PAD_C[1], 0)
    clear = min(PAD_R - Vector(v.Point.x, v.Point.y, 0).sub(c).Length for v in hatch.Vertexes)
    if clear < PAD_HATCH_MARGIN:
        raise RuntimeError("hatch corner %.1f mm outside the sump disc" % -clear)
    report.append("Hatch on disc: nearest corner %.1f mm inside the disc edge" % clear)
    _solid(doc, "Slab", "Slab - concrete, under the enclosure stand", slab, C_CONC, fnd)
    _solid(doc, "Pad", "Pad - concrete, round, at the riser", pad, C_CONC, fnd)

    st = _part(doc, "Structures")
    _solid(doc, "Hatch", "Sump hatch - frame and chequer plate (envelope)", hatch, C_STEEL, st)
    h = STRUT / 2.0
    rail_z0 = ENCL_Z[0] - STRUT
    tops = {"rail": rail_z0, "enclosure bottom": ENCL_Z[0], "enclosure top": ENCL_Z[1]}
    for i, (x, y, top) in sorted(STAND_POSTS.items()):
        _solid(doc, "Post%d" % i, "[S%d] Unistrut post 1-5/8in" % i,
               _box((x - h, x + h), (y - h, y + h), (SLAB_TOP, tops[top])), C_STRUT, st)
    for j, y in sorted(RAILS.items()):
        xs = [px for px, py, top in STAND_POSTS.values()
              if top == "rail" and abs(py - y) < 1e-6]                 # this rail's legs
        _solid(doc, "Rail%d" % j, "[S%d] Unistrut rail 1-5/8in" % j,
               _box((min(xs) - h, max(xs) + h), (y - h, y + h), (rail_z0, ENCL_Z[0])),
               C_STRUT, st)

    eq = _part(doc, "Equipment")
    _solid(doc, "Enclosure", "Enclosure - stainless (envelope)",
           _box(ENCL_X, ENCL_Y, ENCL_Z), C_SS, eq)
    _solid(doc, "ACUnit", "A/C unit on enclosure (envelope)", _box(AC_X, AC_Y, AC_Z), C_SS, eq)
    _solid(doc, "Disconnect", "Disconnect box on A/C unit (envelope, from photo)",
           _box(DISC_X, DISC_Y, DISC_Z), C_SS, eq)
    _solid(doc, "Pedestal", "Pedestal box - grey (envelope)",
           _rbox(PED_C, PED_ANG, PED_L, PED_W, PED_Z[0], PED_Z[1]), C_GREY, eq)
    report.append("Pedestal: bearing %.1f deg from disc centre, turned to %.1f deg (scanned 35), "
                  "centre moved %.1f mm from the scanned centre"
                  % (PED_BEARING, PED_ANG, math.hypot(PED_C[0] - PED_C_SCAN[0],
                                                      PED_C[1] - PED_C_SCAN[1])))
    _solid(doc, "JBox", "Junction box at grade - stainless (envelope)",
           _rbox(JBOX_C, JBOX_ANG, JBOX_A, JBOX_B, JBOX_Z[0], JBOX_Z[1]), C_SS, eq)


def _build_stub(doc, report):
    """[F1] SO flange at grade - [P1] riser - [E1] SW ell - [P2] - [F2] SO /
    [G1] gasket / [B1] studs / [F3] SO - [P3] - [C1] SW cap."""
    pp = _part(doc, "Piping")
    up, down = Vector(0, 0, 1), Vector(0, 0, -1)
    leg = _plan_dir(LEG_AZ)

    f1 = _so_flange("[F1] Flange SO 4in 150# RF (grade, sump tie-in)", pp)
    e1 = _socket_ell("[E1] Socket ell 4in 3000# SW 90", pp)
    f2 = _so_flange("[F2] Flange SO 4in 150# RF (ell side)", pp)
    g1, sethk = _gasket("[G1] Gasket 4in 150#", pp)
    b1 = _studs("[B1] Stud set 4in 150#", sethk, pp)
    f3 = _so_flange("[F3] Flange SO 4in 150# RF (cap side)", pp)
    c1 = _socket_cap("[C1] Socket cap 4in 3000# SW", pp)
    doc.recompute()

    # F1: raised face down on the pad top, on the riser axis.  Its open face
    # is the tie-in to the sump below grade, which is not modelled.
    f1.Placement = Placement(Vector(0, 0, PAD_TOP) - Vector(f1.Ports[0]), Rotation())
    # E1: work point on the riser axis at the leg centreline; inlet down, outlet along the leg.
    _place_fitting(e1, Vector(0, 0, Z_LEG), down, leg)

    so_face_to_pipe = (Vector(f2.Ports[1]) - Vector(f2.Ports[0])).Length  # = 2 trf
    E_ell = (_wpos(e1, 1) - Vector(0, 0, Z_LEG)).Length
    A_cap, E_cap = qenv.val(c1.A), qenv.val(c1.E)

    # Pipe lengths from the scanned stations, through the catalogue take-outs.
    L1 = (_wpos(e1, 0) - _wpos(f1, 1)).Length
    L2 = JOINT_S - sethk / 2.0 - so_face_to_pipe - E_ell
    L3 = CAP_TIP_S - (A_cap - E_cap) - (JOINT_S + sethk / 2.0 + so_face_to_pipe)

    p1 = _pipe(DN_STUB, L1, "[P1] Pipe 4in Sch-40 riser", pp, report)
    p2 = _pipe(DN_STUB, L2, "[P2] Pipe 4in Sch-40 (ell to flange)", pp, report)
    p3 = _pipe(DN_STUB, L3, "[P3] Pipe 4in Sch-40 (flange to cap)", pp, report)
    doc.recompute()

    _seat_axial(p1, 0, f1, 1, leg)
    _seat_axial(p2, 0, e1, 1, up)
    doc.recompute()
    _seat_axial(f2, 1, p2, 1, up)
    doc.recompute()
    _seat_axial(g1, 0, f2, 0, up)
    _seat_axial(b1, 0, f2, 0, up)
    doc.recompute()
    _seat_axial(f3, 0, g1, 1, up)
    doc.recompute()
    _seat_axial(p3, 0, f3, 1, up)
    doc.recompute()
    _seat_axial(c1, 0, p3, 1, up)
    doc.recompute()

    _colour([p1, p2, p3, e1, f1, f2, f3, b1], C_PIPE)
    _colour([c1], C_CAP)
    report.append("Stub: L1 riser %.1f, L2 %.1f, L3 %.1f mm; ell E %.1f, SO face->pipe %.1f, "
                  "gasket %.1f, cap A-E %.1f" % (L1, L2, L3, E_ell, so_face_to_pipe, sethk,
                                                 A_cap - E_cap))
    return dict(F1=f1, P1=p1, E1=e1, P2=p2, F2=f2, G1=g1, B1=b1, F3=f3, P3=p3, C1=c1)


def _jbox_points(riser, z_run, u_entry, jog):
    """Work points of a junction-box run, enclosure underside to the box face."""
    e, nv = _plan_dir(JBOX_ANG), _plan_dir(JBOX_ANG + 90)
    face = Vector(JBOX_C[0], JBOX_C[1], 0) - nv * (JBOX_B / 2)      # centre of the -V face
    entry = face + e * u_entry + Vector(0, 0, z_run)
    rx, ry = riser
    pts = [Vector(rx, ry, ENCL_Z[0])]
    if jog is None:
        y_run = ry
        pts.append(Vector(rx, ry, z_run))
    else:                                                  # high run, one diagonal jog
        z_hi, x0, x1, y_run = jog
        pts += [Vector(rx, ry, z_hi), Vector(x0, ry, z_hi), Vector(x1, y_run, z_run)]
    wp45 = entry - nv * ((entry.y - y_run) / nv.y)         # 45 bend, on the run line
    return pts + [wp45, entry]


def _ped_points(riser, z_run, x_turn):
    """Work points of the pedestal run: along +X, north, then square into the
    pedestal face that looks back at the enclosure."""
    t = _plan_dir(PED_ANG)                                 # the pedestal's L axis
    entry = Vector(PED_C[0], PED_C[1], z_run) - t * (PED_L / 2)
    back = (entry.x - x_turn) / t.x                        # entry line meets x = x_turn
    rx, ry = riser
    return [Vector(rx, ry, ENCL_Z[0]), Vector(rx, ry, z_run), Vector(x_turn, ry, z_run),
            entry - t * back, entry]


def _build_conduit(doc, report):
    """Each run is a polyline of work points: a bend at every interior point
    (its angle from the two legs), and pipes spanning the bends' ports."""
    kk = _part(doc, "Conduit")
    r = _read_row("Pipe_%s.csv" % PIPE_SCHED, DN1)
    out = {}
    routes = [(n, _jbox_points(rs, z, u, jog), "junction box") for n, rs, z, u, jog in JBOX_RUNS]
    routes.append((PED_RUN[0], _ped_points(*PED_RUN[1:]), "pedestal box"))
    for name, pts, target in routes:
        letters = "abcdefghijklm"
        objs, ends, angles = [], [pts[0]], []
        for i in range(1, len(pts) - 1):
            d_in = pts[i] - pts[i - 1]; d_in.normalize()
            d_out = pts[i + 1] - pts[i]; d_out.normalize()
            ba = round(math.degrees(d_in.getAngle(d_out)), 6)
            b = pCmd.makeElbow([DN1, _f(r, "OD"), _f(r, "thk"), ba, SWEEP_R], rating=PIPE_SCHED)
            b.PRating = PIPE_SCHED
            b.Label = "[%s%s] Conduit 1in bend %g deg R5-3/4in" % (name, letters[2 * i - 1], ba)
            kk.addObject(b)
            doc.recompute()
            _place_fitting(b, pts[i], d_in * -1, d_out)
            ends += [_wpos(b, 0), _wpos(b, 1)]
            objs.append(b)
            angles.append(ba)
        ends.append(pts[-1])
        lengths = []
        for k in range(0, len(ends), 2):
            a, b_ = ends[k], ends[k + 1]
            what = "riser" if k == 0 else ("to " + target if k == len(ends) - 2 else "run")
            p = _pipe(DN1, (b_ - a).Length,
                      "[%s%s] Conduit 1in %s (DN25 Sch-40)" % (name, letters[k], what), kk, report)
            doc.recompute()
            d = b_ - a; d.normalize()
            p.Placement = Placement(a, Rotation(Vector(0, 0, 1), d))
            objs.append(p)
            lengths.append((b_ - a).Length)
        doc.recompute()
        _colour(objs, C_COND)
        report.append("%s to %s: bends %s deg; pipes %s mm" % (
            name, target, " / ".join("%g" % x for x in angles), ", ".join("%.1f" % L for L in lengths)))
        out[name] = objs
    return out


def _add_scan(doc):
    """The scan as a hidden mesh overlay in the site frame (skipped if absent)."""
    if not os.path.isfile(SCAN_FILE):
        return None
    import numpy as np
    import Mesh
    import scan_tools as st
    S = st.load_dae(SCAN_FILE, texture=None, cache=False)
    V = st.yup_to_zup(S["V"])
    M = st.rot_z(SCAN_ROT_DEG)
    M[:3, 3] = SCAN_SHIFT
    V = st.apply(M, V)
    tris = V[S["F"]].reshape(-1, 9).tolist()
    m = Mesh.Mesh([[t[0:3], t[3:6], t[6:9]] for t in tris])
    grp = _part(doc, "Scan")
    o = doc.addObject("Mesh::Feature", "ScanMesh")
    o.Label = "Scan mesh (site frame)"
    o.Mesh = m
    grp.addObject(o)
    if _HAS_GUI and o.ViewObject is not None:
        o.ViewObject.Visibility = False
    return o


def build(save=False, with_scan=True):
    if DOC_NAME in FreeCAD.listDocuments():
        FreeCAD.closeDocument(DOC_NAME)
    doc = FreeCAD.newDocument(DOC_NAME)
    report = []
    doc.openTransaction("Build mesh example")
    _build_site(doc, report)
    stub = _build_stub(doc, report)
    cond = _build_conduit(doc, report)
    if with_scan:
        _add_scan(doc)
    doc.recompute()
    doc.commitTransaction()

    try:
        if _HAS_GUI and FreeCADGui.ActiveDocument is not None:
            FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass

    out_path = os.path.join(_HERE, "mesh_example.FCStd")
    if save:
        doc.saveAs(out_path)
    FreeCAD.Console.PrintMessage(
        "\n=== Mesh example built: %d objects ===\n  %s\n  %s\n"
        % (len(doc.Objects), "\n  ".join(report),
           ("Saved: " + out_path) if save else "Not saved"))
    return doc, stub, cond, report


if __name__ == "__main__":
    build(save=True)
