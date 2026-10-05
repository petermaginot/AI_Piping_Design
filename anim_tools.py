# -*- coding: utf-8 -*-
"""Small toolkit for animating a FreeCAD model in the live GUI session.

Used by the ``skills/animation`` skill.  An animation is a *timeline*: a list
of ``(seconds, fn(u))`` steps, where ``u`` runs 0 -> 1 over the step and a
step of 0 s is an instant action.  A :class:`Player` plays it on a Qt timer,
so the GUI (and the MCP bridge) stay responsive; :func:`step_to` runs the same
steps synchronously to grab a single frame.

Typical use::

    import anim_tools as at
    tl = at.Timeline()
    tl.hold(1.0)
    tl.move(studs, out * 150, 2.0, start=at.home(holder, studs))
    tl.instant(lambda: setattr(studs, "Visibility", False))
    at.Player(tl.steps).start()

Rules (see the skill): update placements only, never ``recompute()`` the
document per frame; take every point from Quetzal ports, never from a typed
coordinate; keep home placements in the document so ``reset()`` survives a
save and reopen.
"""

import json
import time

import FreeCAD
from FreeCAD import Vector

__all__ = [
    "OPEN_RGB", "CLOSED_RGB",
    "ease", "frame", "val", "mark", "label", "wpos", "wdir",
    "Timeline", "Player", "stop_all", "step_to", "pump", "play_blocking",
    "save_homes", "home", "restore_homes", "set_transparency", "set_valve",
]

OPEN_RGB = (0.10, 0.70, 0.20)     # valve open: green
CLOSED_RGB = (0.85, 0.10, 0.10)   # valve closed: red


# ---------------------------------------------------------------------------
# Geometry and lookup
# ---------------------------------------------------------------------------

def ease(u):
    """Smoothstep: 0 -> 1 with zero speed at both ends."""
    return u * u * (3 - 2 * u)


def frame(X, Y):
    """Rotation taking local X, Y to the world directions X, Y (Z = X x Y).
    X and Y must be perpendicular; they are normalised here."""
    X = Vector(X).normalize()
    Y = Vector(Y).normalize()
    Z = X.cross(Y)
    m = FreeCAD.Matrix(X.x, Y.x, Z.x, 0, X.y, Y.y, Z.y, 0,
                       X.z, Y.z, Z.z, 0, 0, 0, 0, 1)
    return FreeCAD.Rotation(m)


def val(x):
    """float from a Quantity or a number."""
    try:
        return float(x.Value)
    except AttributeError:
        return float(x)


def mark(doc, tag):
    """The one object whose label starts with '[tag] '."""
    hits = [o for o in doc.Objects if o.Label.startswith("[%s] " % tag)]
    if len(hits) != 1:
        raise RuntimeError("expected one [%s], found %d" % (tag, len(hits)))
    return hits[0]


def label(doc, text):
    """The one object labelled exactly ``text`` (e.g. a spool App::Part)."""
    hits = [o for o in doc.Objects if o.Label == text]
    if len(hits) != 1:
        raise RuntimeError("expected one %r, found %d" % (text, len(hits)))
    return hits[0]


def wpos(o, i):
    """World position of port i."""
    return o.getGlobalPlacement().multVec(o.Ports[i])


def wdir(o, i):
    """World direction of port i (outward, unit)."""
    return o.getGlobalPlacement().Rotation.multVec(o.PortDirections[i]).normalize()


# ---------------------------------------------------------------------------
# Timeline and playback
# ---------------------------------------------------------------------------

class Timeline(object):
    """Builds ``steps``, a list of (seconds, fn(u)).  Every fn must be a pure
    function of u and of state fixed before the timeline was built, so that
    any step can be replayed out of order by :func:`step_to`."""

    def __init__(self):
        self.steps = []

    def hold(self, sec):
        self.steps.append((sec, lambda u: None))

    def instant(self, fn):
        """fn() once, in a 0 s step."""
        self.steps.append((0.0, lambda u: fn()))

    def tween(self, sec, fn):
        """fn(ease(u)) over sec seconds."""
        self.steps.append((sec, lambda u: fn(ease(u))))

    def move(self, obj, delta, sec, start):
        """Translate obj by delta from the Placement ``start``, eased."""
        start = FreeCAD.Placement(start)

        def fn(u):
            obj.Placement = FreeCAD.Placement(start.Base + delta * u,
                                              start.Rotation)
        self.tween(sec, fn)

    def duration(self):
        return sum(s for s, _ in self.steps)


class Player(object):
    """Plays steps on a QTimer.  Keeps a reference to itself on the FreeCAD
    module while running, or it would be garbage-collected and stop."""

    def __init__(self, steps, fps=30, name="animation"):
        from PySide import QtCore
        self.steps = steps
        self.fps = fps
        self.name = name
        self.i = 0
        self.t_step = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)

    def start(self):
        stop_all()
        FreeCAD.__anim_player__ = self
        self.i = 0
        self.t_step = time.monotonic()
        self.timer.start(int(1000 / self.fps))
        return self

    def stop(self):
        self.timer.stop()

    def done(self):
        return self.i >= len(self.steps)

    def tick(self):
        now = time.monotonic()
        while self.i < len(self.steps):
            sec, fn = self.steps[self.i]
            u = 1.0 if sec <= 0 else min(1.0, (now - self.t_step) / sec)
            fn(u)
            if u < 1.0:
                return
            self.i += 1
            self.t_step = now
        self.timer.stop()
        FreeCAD.Console.PrintMessage("%s: done\n" % self.name)


def stop_all():
    """Stop the player started last, if any."""
    p = getattr(FreeCAD, "__anim_player__", None)
    if p is not None:
        p.stop()


def step_to(steps, i, u=1.0):
    """Pose the scene at step i, fraction u, by running every earlier step to
    its end.  Deterministic, and the same code the player runs: use it to grab
    frames (then ``saveImage``) instead of playing in real time."""
    for _, fn in steps[:i]:
        fn(1.0)
    if i < len(steps):
        steps[i][1](u)
    try:
        import FreeCADGui
        FreeCADGui.updateGui()
    except ImportError:
        pass


def pump(ms):
    """Run the Qt event loop for ms milliseconds (the timer and
    execute_python share the GUI thread)."""
    from PySide import QtCore
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(int(ms), loop.quit)
    loop.exec_()


def play_blocking(player, budget_s=50.0):
    """Pump until the player finishes or budget_s passes; returns player.i.
    Keep each MCP call under about 50 s and call again until
    ``player.done()``."""
    t_end = time.monotonic() + budget_s
    while player.timer.isActive() and time.monotonic() < t_end:
        pump(40)
    return player.i


# ---------------------------------------------------------------------------
# Home state, kept in the document
# ---------------------------------------------------------------------------

def _home_map(holder, prop):
    if not hasattr(holder, prop):
        holder.addProperty("App::PropertyMap", prop, "Animation",
                           "Start state of every animated object (JSON)")
    return dict(getattr(holder, prop))


def save_homes(holder, objs, prop="AnimHome"):
    """Record placement, visibility and transparency of each obj on
    ``holder`` (any document object).  Only objects not yet recorded are
    written, so call it with the model in its start state; a later call after
    a save mid-animation does not overwrite the true homes."""
    m = _home_map(holder, prop)
    changed = False
    for o in objs:
        if o.Name in m:
            continue
        vo = getattr(o, "ViewObject", None)
        m[o.Name] = json.dumps({
            "base": list(o.Placement.Base),
            "q": list(o.Placement.Rotation.Q),
            "vis": bool(o.Visibility),
            "tr": int(getattr(vo, "Transparency", 0)) if vo else 0,
        })
        changed = True
    if changed:
        setattr(holder, prop, m)


def home(holder, obj, prop="AnimHome"):
    """The recorded start Placement of obj."""
    d = json.loads(getattr(holder, prop)[obj.Name])
    return FreeCAD.Placement(Vector(*d["base"]), FreeCAD.Rotation(*d["q"]))


def restore_homes(holder, prop="AnimHome"):
    """Put every recorded object back: placement, visibility, transparency."""
    doc = holder.Document
    for name, s in getattr(holder, prop).items():
        o = doc.getObject(name)
        if o is None:
            continue
        d = json.loads(s)
        o.Placement = FreeCAD.Placement(Vector(*d["base"]),
                                        FreeCAD.Rotation(*d["q"]))
        o.Visibility = d["vis"]
        vo = getattr(o, "ViewObject", None)
        if vo is not None and hasattr(vo, "Transparency"):
            vo.Transparency = d["tr"]


def set_transparency(objs, value):
    """Transparency on each object that has one.  An App::Part container has
    none: pass its members (``part.Group``)."""
    for o in objs:
        vo = getattr(o, "ViewObject", None)
        if vo is not None and hasattr(vo, "Transparency"):
            vo.Transparency = value


# ---------------------------------------------------------------------------
# Valves
# ---------------------------------------------------------------------------

def set_valve(v, is_open, open_rgb=OPEN_RGB, closed_rgb=CLOSED_RGB):
    """Colour a Quetzal valve and put its actuator open or closed
    ('Handle' / 'Handle-closed', 'Handwheel' / 'Handwheel-closed').  Only the
    valve rebuilds, and only when the value changes (a gate valve takes about
    0.8 s, so do this in an instant step).  Its ports and placement do not
    change.  Quetzal has no closed gearbox for a ball valve, so a geared ball
    valve only changes colour."""
    v.ViewObject.ShapeColor = open_rgb if is_open else closed_rgb
    if not hasattr(v, "Actuator"):
        return
    base = v.Actuator.replace("-closed", "")
    if base == "Gearbox" and not any(t in str(getattr(v, "PRating", ""))
                                     for t in ("Gate", "Globe")):
        return
    want = base if is_open else base + "-closed"
    if v.Actuator != want:
        v.Actuator = want
        v.recompute()
