# -*- coding: utf-8 -*-
"""Numerical checks for a built Quetzal model, run in the live FreeCAD session.

The ``quetzal-piping`` skill (§8, §10.2) requires every build to be verified
numerically before handover.  This module is that verification, so the agent
calls it rather than retyping it on every build.  Nothing here creates or
changes objects.

Load it over MCP once per session (re-run after a FreeCAD restart)::

    import sys, importlib
    sys.path.insert(0, r"<repo root>")
    import piping_checks as pc; importlib.reload(pc)

    doc = FreeCAD.ActiveDocument
    joints, open_ports = pc.auto_joints(doc.Objects)
    rows  = pc.joint_report(joints)               # gap ~0, dot ~-1 per joint
    rows += pc.open_port_report(open_ports)       # ends that should be open?
    rows += pc.interference_report(doc.Objects, joints)
    pc.summary(rows)

Every check returns rows ``{"check", "measured", "target", "status", "note"}``
with ``status`` one of ``pass``, ``fail``, ``review`` (a judgement for the
agent or the user) or ``unverified`` (data missing).  Put them in the handover
report (skill §8.1); never round a ``fail`` into a ``pass``.
"""

import itertools

__all__ = [
    "wpos", "wdir", "port_objects", "auto_joints",
    "joint_report", "open_port_report", "interference_report", "summary",
]

GAP_TOL = 1e-4        # mm: a mated pair closes to rounding (2e-5 seen on a
                      # long chain of rotations); anything real is far larger
DOT_TOL = 1e-6        # a mated pair points face to face: dot == -1
MATCH_TOL = 0.01      # mm: ports this close are treated as one joint
NEAR_MISS = 100.0     # mm: two open ports this close are a joint that missed
MIN_VOLUME = 1e-3     # mm^3: overlap below this is sub-tolerance contact
SW_FIT_VOLUME = 5.0   # mm^3: pipe-table OD vs fitting-table socket (§10.2)

# Objects whose ports are not connection points (skill references/components.md:
# a Clamp's single port is meaningless).
_IGNORE_PORTS = ("Clamp",)


def _label(o):
    return getattr(o, "Label", o.Name)


def _ptype(o):
    return getattr(o, "PType", "") or ""


def wpos(o, i):
    """World position of port *i*.  Uses the global placement, so it is right
    inside App::Part spool containers as well as at the top level."""
    return o.getGlobalPlacement().multVec(o.Ports[i])


def wdir(o, i):
    """World direction of port *i*, normalised."""
    return o.getGlobalPlacement().Rotation.multVec(o.PortDirections[i]).normalize()


def port_objects(objs):
    """The objects in *objs* that carry connection ports."""
    out = []
    for o in objs:
        ports = getattr(o, "Ports", None)
        if ports and getattr(o, "PortDirections", None) and _ptype(o) not in _IGNORE_PORTS:
            out.append(o)
    return out


def auto_joints(objs, tol=MATCH_TOL):
    """Pair every port with the ports of other objects that sit on it.

    Returns ``(joints, open_ports)``.  A joint is ``(a, ia, b, ib)``.  Where
    more than two ports share a point (a flange face with a gasket and a stud
    set on it), every pair of distinct objects there is a joint.  An open port
    is ``(o, i)`` with nothing on it: a free end, a blind face, a vent.  A
    gap larger than *tol* cannot be found this way; it shows up as two open
    ports instead, which is why :func:`open_port_report` exists.
    """
    ports = [(o, i, wpos(o, i)) for o in port_objects(objs) for i in range(len(o.Ports))]
    clusters = []
    for o, i, p in ports:
        for c in clusters:
            if (c[0][2] - p).Length <= tol:
                c.append((o, i, p))
                break
        else:
            clusters.append([(o, i, p)])
    joints, open_ports = [], []
    for c in clusters:
        if len(c) == 1:
            open_ports.append(c[0][:2])
            continue
        for (a, ia, _), (b, ib, _) in itertools.combinations(c, 2):
            if a is not b:
                joints.append((a, ia, b, ib))
    return joints, open_ports


def joint_report(joints, gap_tol=GAP_TOL, dot_tol=DOT_TOL, quiet=False):
    """Gap and facing of every joint.  A joint passes at gap 0 and dot -1.

    A stud set or a gasket shares the flange face but not its direction, so
    for those only the gap is judged.
    """
    rows = []
    for a, ia, b, ib in joints:
        gap = (wpos(a, ia) - wpos(b, ib)).Length
        dot = wdir(a, ia).dot(wdir(b, ib))
        name = "%s[%d] - %s[%d]" % (_label(a), ia, _label(b), ib)
        loose = {"Bolts_Nuts", "Gasket"} & {_ptype(a), _ptype(b)}
        ok = gap <= gap_tol and (loose or abs(dot + 1.0) <= dot_tol)
        rows.append({
            "check": "joint " + name,
            "measured": "gap=%.6f mm dot=%+.6f" % (gap, dot),
            "target": "gap=0 dot=-1" if not loose else "gap=0",
            "status": "pass" if ok else "fail",
            "note": "" if ok else ("ports point the same way" if dot > 0 else "not closed"),
        })
    if not quiet:
        _print(rows)
    return rows


def open_port_report(open_ports, near=NEAR_MISS, quiet=False):
    """Ports with nothing on them.

    Two open ports of different objects within *near* mm of each other are a
    joint that missed: ``fail``, with the gap.  Every other open port is a
    ``review``: the agent says whether it is an intended free end (a bevel
    end, a blind face, a vent) or something left unconnected.
    """
    rows, missed = [], set()
    for (a, ia), (b, ib) in itertools.combinations(open_ports, 2):
        if a is b:
            continue
        d = wpos(b, ib) - wpos(a, ia)
        gap = d.Length
        # A missed joint: the ports face each other (anti-parallel) and each
        # lies in front of, or beside, the other -- not behind it.  A blind's
        # back face beside its neighbour's weld end points away and is not one.
        facing = (wdir(a, ia).dot(wdir(b, ib)) < -0.9
                  and d.dot(wdir(a, ia)) > -0.5 and (-d).dot(wdir(b, ib)) > -0.5)
        if gap <= near and facing:
            missed.update({(a.Name, ia), (b.Name, ib)})
            rows.append({
                "check": "joint %s[%d] - %s[%d]" % (_label(a), ia, _label(b), ib),
                "measured": "gap=%.3f mm dot=%+.6f" % (gap, wdir(a, ia).dot(wdir(b, ib))),
                "target": "gap=0 dot=-1",
                "status": "fail",
                "note": "near miss: ports did not meet",
            })
    for o, i in open_ports:
        if (o.Name, i) in missed:
            continue
        p = wpos(o, i)
        rows.append({
            "check": "open port %s[%d]" % (_label(o), i),
            "measured": "(%.3f, %.3f, %.3f)" % (p.x, p.y, p.z),
            "target": "intended free end",
            "status": "review",
            "note": _ptype(o),
        })
    if not quiet:
        _print(rows)
    return rows


def _classify(a, b, vol, adjacent):
    """Status and note for one overlapping pair (skill §10.2 artefact table)."""
    types = {_ptype(a), _ptype(b)}
    if "Bolts_Nuts" in types and types & {"Flange", "Valve"}:
        return "pass", "table artefact: stud set short of the flange backs (compare both sides)"
    if types == {"Bolts_Nuts", "Gasket"} and vol < 50.0:
        return "pass", "table artefact: centring ring past the studs"
    if adjacent and "Pipe" in types and vol < SW_FIT_VOLUME:
        return "pass", "table artefact: SW pipe OD vs fitting socket"
    if "Clamp" in types and any(getattr(o, "FType", "") == "Beam" for o in (a, b)):
        return "review", "U-bolt legs through the beam flange: expect 2*pi*(d/2)^2*tf"
    return "fail", "clash" if not adjacent else "overlap at a joint"


def interference_report(objs, joints=(), min_volume=MIN_VOLUME, quiet=False):
    """Every pair of solids that overlaps, classified.

    Bounding boxes prefilter the pairs; ``common().Volume`` measures the
    rest.  Touching neighbours (zero volume) are not reported.  Pairs that
    share a joint in *joints* count as adjacent.
    """
    solids = [o for o in objs
              if hasattr(o, "Shape") and o.TypeId != "App::Part"
              and not o.TypeId.startswith(("TechDraw::", "Spreadsheet::", "App::"))
              and o.Shape.Solids]
    adjacent = {frozenset((a.Name, b.Name)) for a, _, b, _ in joints}
    shapes = {}
    for o in solids:                      # world position, inside a spool Part too
        s = o.Shape.copy()
        s.Placement = o.getGlobalPlacement()
        shapes[o.Name] = s
    rows = []
    for a, b in itertools.combinations(solids, 2):
        sa, sb = shapes[a.Name], shapes[b.Name]
        if not sa.BoundBox.intersect(sb.BoundBox):
            continue
        try:
            vol = sa.common(sb).Volume
        except Exception as exc:          # OCCT failure is itself a finding
            rows.append({"check": "overlap %s / %s" % (_label(a), _label(b)),
                         "measured": "common() failed", "target": "0 mm^3",
                         "status": "unverified", "note": str(exc)})
            continue
        if vol <= min_volume:
            continue
        status, note = _classify(a, b, vol, frozenset((a.Name, b.Name)) in adjacent)
        rows.append({"check": "overlap %s / %s" % (_label(a), _label(b)),
                     "measured": "%.1f mm^3" % vol, "target": "0 mm^3",
                     "status": status, "note": note, "_vol": vol,
                     "_studs": next((o.Name for o in (a, b) if _ptype(o) == "Bolts_Nuts"), None)
                     if note.startswith("table artefact: stud set") else None})
    # A centred stud set overlaps the flanges on its two sides equally.
    by_set = {}
    for r in rows:
        if r.get("_studs"):
            by_set.setdefault(r["_studs"], []).append(r)
    for group in by_set.values():
        vols = [r["_vol"] for r in group]
        if len(group) != 2 or abs(vols[0] - vols[1]) > 0.01 * max(vols):
            for r in group:
                r["status"] = "review"
                r["note"] = "stud-set overlap not equal on both sides: %s" % (
                    ", ".join("%.1f" % v for v in vols))
        else:
            for r in group:
                r["note"] = "table artefact: stud set short of the flange backs, equal both sides"
    for r in rows:
        r.pop("_vol", None); r.pop("_studs", None)
    if not quiet:
        _print(rows)
    return rows


def summary(rows):
    """Count by status and print the failures and reviews.  Returns the
    counts, so a caller can assert ``counts["fail"] == 0``."""
    counts = {s: 0 for s in ("pass", "fail", "review", "unverified")}
    for r in rows:
        counts[r["status"]] += 1
    print("checks: %d  pass %d  fail %d  review %d  unverified %d"
          % ((len(rows),) + tuple(counts[s] for s in ("pass", "fail", "review", "unverified"))))
    _print([r for r in rows if r["status"] != "pass"])
    return counts


def _print(rows):
    for r in rows:
        print("%-10s %-60s %-32s %s" % (r["status"].upper(), r["check"], r["measured"], r["note"]))
