"""Lock-out animation for the pig-launcher header (Header_with_pig_launcher.FCStd).

Run inside the live FreeCAD GUI session, with that file the active document:

    exec(open(r"<path>/valve_lockout_animation.py").read(),
         {"__file__": r"<path>/valve_lockout_animation.py", "__name__": "lockout"})
    build()          # once: split the valves into body + handle, add angle drivers
    play()           # run the whole sequence in the 3D view (returns at once)
    stop()           # stop a running play
    reset()          # back to the start state (valves closed/red, blinds on)

Sequence (all three valves start closed):
    1. Open V7
    2. Remove studs B10 and blind F12 from the drain outlet, then open V6
    3. Remove studs B5 and blind F6 from the barrel closure
    V10 stays closed.

Why the valves are split: Quetzal fuses the handle into the valve solid and rebuilds it
on recompute, so the handle cannot be rotated in place. build() leaves each Quetzal valve
untouched (hidden) and shows an animation-only body + handle pair that follows its
Placement. Angle 0 = open (handle parallel to flow), 90 = closed.

The timeline is played by anim_tools.Player on a Qt timer, so the GUI stays live while it
runs. For a single frame, use anim_tools.step_to(_timeline(), i, u) or state().

Expression note: this FreeCAD install needs ';' between expression arguments.
"""
import json
import os
import sys

import Part
import FreeCAD as App
import FreeCADGui as Gui


def _repo_root():
    """Walk up from this file to the directory that holds anim_tools.py."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()  # __file__ undefined when exec()'d from the console
    while True:
        if os.path.isfile(os.path.join(here, "anim_tools.py")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise RuntimeError(
                "Cannot find anim_tools.py at or above %s -- run this macro "
                "from its place in the AI_Piping_Design repo." % here)
        here = parent


_ROOT = _repo_root()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import anim_tools as at  # noqa: E402

OPEN, CLOSED = 0.0, 90.0

# tag -> short name used for the animation objects
VALVES = {"V6": "AnimV6", "V7": "AnimV7", "V10": "AnimV10"}
MOVERS = ("B10", "F12", "B5", "F6")      # studs and blinds that get removed
SLIDE = {"F12": 250.0, "F6": 400.0}      # mm the blind travels before it is hidden
STUD_CLEARANCE = 20.0                    # mm the studs travel past the blind's outer face
MOVE_SEC = 1.5                           # seconds per valve turn or removal


def _doc():
    return App.ActiveDocument


def _by_tag(tag):
    return at.mark(_doc(), tag)


def _grp():
    g = _doc().getObject("Anim_Valves")
    return g or _doc().addObject("App::DocumentObjectGroup", "Anim_Valves")


def _split_height(valve):
    """Local-Y height above which the geometry is stem + handle."""
    if str(valve.Conn) == "TH":
        return float(valve.ODBody) / 2.0
    return float(valve.FlgD) / 2.0           # flanged: top of body / flange OD


def build():
    doc = _doc()
    grp = _grp()
    for tag, name in VALVES.items():
        for n in (name + "_Handle", name + "_Body", name):
            if doc.getObject(n):
                doc.removeObject(n)
    for old in ("AnimHandle7", "AnimBody7", "AnimValve7"):   # first prototype
        if doc.getObject(old):
            doc.removeObject(old)

    big = 2000.0
    for tag, name in VALVES.items():
        v = _by_tag(tag)
        loc = v.Shape.copy()
        loc.Placement = App.Placement()
        y0 = _split_height(v) + 1e-3
        upper = Part.makeBox(big, big, big, App.Vector(-big / 2, y0, -big / 2))
        lower = Part.makeBox(big, big, big, App.Vector(-big / 2, y0 - big, -big / 2))

        drv = doc.addObject("App::VarSet", name)
        drv.addProperty("App::PropertyAngle", "Handle_Angle", "Anim",
                        "0 = open (handle parallel to flow), 90 = closed")
        drv.Handle_Angle = CLOSED
        body = doc.addObject("Part::Feature", name + "_Body")
        body.Shape = loc.common(lower)
        hdl = doc.addObject("Part::Feature", name + "_Handle")
        hdl.Shape = loc.common(upper)
        body.setExpression("Placement", "%s.Placement" % v.Name)
        hdl.setExpression(
            "Placement",
            "%s.Placement * placement(vector(0mm;0mm;0mm); vector(0;1;0); %s.Handle_Angle)"
            % (v.Name, name))
        for o in (drv, body, hdl):
            grp.addObject(o)
        v.Visibility = False
    doc.recompute()
    reset()


def _set_angle(tag, angle):
    name = VALVES[tag]
    d = _doc().getObject(name)
    d.Handle_Angle = angle
    # The handle Placement is an expression of Handle_Angle; it only updates on recompute.
    _doc().getObject(name + "_Handle").recompute()
    col = at.OPEN_RGB if angle < 45.0 else at.CLOSED_RGB
    for suffix in ("_Body", "_Handle"):
        _doc().getObject(name + suffix).ViewObject.ShapeColor = col


# --- scene state ---------------------------------------------------------------------
def _homes():
    """Record the movers' start state on the Anim_Valves group (anim_tools.save_homes),
    so it survives a macro reload or an interrupted play(). Must first run at the start
    state; build() does this before anything has moved. An older version of this macro
    kept the placements as JSON in HomeJson; those are carried over."""
    g = _grp()
    if getattr(g, "HomeJson", "") and not hasattr(g, "AnimHome"):
        g.addProperty("App::PropertyMap", "AnimHome", "Animation")
        g.AnimHome = {
            _by_tag(t).Name: json.dumps({"base": b, "q": q, "vis": True, "tr": 0})
            for t, (b, q) in json.loads(g.HomeJson).items()}
    at.save_homes(g, [_by_tag(t) for t in MOVERS])
    return g


def _slide_dir(blind, studs):
    """Axis-aligned direction from the studs toward the blind (exact, so no drift)."""
    d = blind.Shape.BoundBox.Center - studs.Shape.BoundBox.Center
    comp = [d.x, d.y, d.z]
    i = max(range(3), key=lambda k: abs(comp[k]))
    out = [0.0, 0.0, 0.0]
    out[i] = 1.0 if comp[i] > 0 else -1.0
    return App.Vector(*out)


def _stud_travel(studs, blind, direction):
    """Distance the studs must be pulled along `direction` (out through the blind) until
    their trailing end clears the blind's outer face."""
    i = max(range(3), key=lambda k: abs([direction.x, direction.y, direction.z][k]))
    sign = [direction.x, direction.y, direction.z][i]
    sb, bb = studs.Shape.BoundBox, blind.Shape.BoundBox
    lo_s, hi_s = [(sb.XMin, sb.XMax), (sb.YMin, sb.YMax), (sb.ZMin, sb.ZMax)][i]
    lo_b, hi_b = [(bb.XMin, bb.XMax), (bb.YMin, bb.YMax), (bb.ZMin, bb.ZMax)][i]
    if sign > 0:
        return hi_b - lo_s + STUD_CLEARANCE
    return hi_s - lo_b + STUD_CLEARANCE


def reset():
    at.restore_homes(_homes())
    for tag in VALVES:
        _set_angle(tag, CLOSED)
    Gui.updateGui()


# --- timeline -------------------------------------------------------------------------
def _timeline():
    """The lockout as anim_tools steps. Directions and travels are solved from the
    movers at their home positions, so call it with the scene reset."""
    g = _homes()
    tl = at.Timeline()

    def open_valve(tag):
        tl.tween(MOVE_SEC, lambda u: _set_angle(tag, CLOSED + (OPEN - CLOSED) * u))

    def remove(tag, direction, distance):
        o = _by_tag(tag)
        tl.move(o, direction * distance, MOVE_SEC, start=at.home(g, o))
        tl.instant(lambda: setattr(o, "Visibility", False))

    b10, f12 = _by_tag("B10"), _by_tag("F12")
    b5, f6 = _by_tag("B5"), _by_tag("F6")
    out12 = _slide_dir(f12, b10)
    out6 = _slide_dir(f6, b5)

    tl.hold(0.8)
    open_valve("V7")                                       # 1. barrel vent
    tl.hold(0.5)
    remove("B10", out12, _stud_travel(b10, f12, out12))    # 2. drain outlet: studs,
    remove("F12", out12, SLIDE["F12"])                     #    blind, then V6
    open_valve("V6")
    tl.hold(0.5)
    remove("B5", out6, _stud_travel(b5, f6, out6))         # 3. barrel closure: studs,
    remove("F6", out6, SLIDE["F6"])                        #    blind
    return tl.steps


def play():
    """Reset, then play on a Qt timer. Returns the Player (p.i, p.done())."""
    at.stop_all()
    reset()
    return at.Player(_timeline(), name="valve lockout").start()


def stop():
    at.stop_all()


def state(v7=CLOSED, v6=CLOSED, v10=CLOSED):
    """Jump to a static valve state, handy for checking or rendering a single frame."""
    _set_angle("V7", v7)
    _set_angle("V6", v6)
    _set_angle("V10", v10)
    _doc().recompute()
    Gui.updateGui()


if __name__ == "__main__":
    play()
