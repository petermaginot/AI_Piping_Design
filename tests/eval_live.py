# -*- coding: utf-8 -*-
"""Regression evals for the piping skill: compare a fresh build with a known-good one.

The examples in ``examples/`` pair a source (a prompt, a sketch, an iso) with
a model that was checked by hand.  After a change to a skill, have the agent
rebuild one of them from its source alone, in a new document, then score the
result here.  A skill edit that makes the agent read a dimension wrongly or
drop a fitting shows up as a failed eval instead of an anecdote.

Needs the live FreeCAD GUI session (Quetzal builds nothing headless), so it is
not part of ``python -m unittest`` or CI.  Run it over MCP::

    import sys, importlib
    sys.path[:0] = [REPO, REPO + "/tests"]
    import eval_live as ev; importlib.reload(ev)
    ev.compare(FreeCAD.ActiveDocument, "spool_8in_600_elbow")

The metrics do not change when the model is moved or rotated, so a rebuild
need not use the reference's origin or axes:
- counts of parts by type, size and rating;
- total pipe length per size;
- the number of closed joints and open ends;
- the sorted distances between every pair of open ends.  For a spool, these
  are its face-to-face dimensions.

To record a new case, open the reference model (a scratch copy, so the bridge
cannot re-save it) and run ``ev.capture(doc, "<example folder>")``.  That
writes ``examples/<folder>/expected.json``.
"""

import json
import os

import piping_checks as pc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LENGTH_TOL = 1.0       # mm: a drawing dimension can sit ±1 mm off the tables
                       # (Golden Rule 7), and that lands in derived lengths


def _val(x):
    try:
        return float(x.Value)
    except AttributeError:
        return float(x)


def _key(o):
    """Type, size, rating and, for flanged parts, the class: a 300# flange
    built where a 600# was drawn must not count as the same part."""
    bits = [getattr(o, a, "") for a in ("PType", "PSize", "PRating", "FClass")]
    return " ".join(str(b) for b in bits if b)


def metrics(doc):
    """The rigid-motion-invariant summary of a built model."""
    objs = [o for o in doc.Objects if getattr(o, "PType", "")]
    parts, pipe = {}, {}
    for o in objs:
        parts[_key(o)] = parts.get(_key(o), 0) + 1
        if o.PType == "Pipe":
            pipe[o.PSize] = round(pipe.get(o.PSize, 0.0) + _val(o.Height), 3)
    joints, open_ports = pc.auto_joints(doc.Objects)
    ends = [pc.wpos(o, i) for o, i in open_ports]
    spans = sorted(round((a - b).Length, 3)
                   for k, a in enumerate(ends) for b in ends[k + 1:])
    bad = [r for r in pc.joint_report(joints, quiet=True) if r["status"] != "pass"]
    return {"parts": dict(sorted(parts.items())), "pipe_length": dict(sorted(pipe.items())),
            "joints": len(joints), "joints_failing": len(bad),
            "open_ends": len(ends), "end_spans": spans}


def _path(case):
    return os.path.join(REPO, "examples", case, "expected.json")


def capture(doc, case, source=None):
    """Record *doc* as the expected result for ``examples/<case>``."""
    m = metrics(doc)
    m = {"case": case, "source": source or "", "reference": os.path.basename(doc.FileName), **m}
    with open(_path(case), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(m, fh, indent=2)
        fh.write("\n")
    print("wrote", _path(case))
    return m


def compare(doc, case, tol=LENGTH_TOL):
    """Score *doc* against ``examples/<case>/expected.json``.  Prints one line
    per metric and returns True only when every one passes."""
    with open(_path(case), encoding="utf-8") as fh:
        exp = json.load(fh)
    got = metrics(doc)
    results = []

    def check(name, ok, detail):
        results.append(ok)
        print("%-4s %-14s %s" % ("PASS" if ok else "FAIL", name, detail))

    missing = {k: v - got["parts"].get(k, 0) for k, v in exp["parts"].items()
               if got["parts"].get(k, 0) != v}
    extra = {k: v for k, v in got["parts"].items() if k not in exp["parts"]}
    check("parts", not missing and not extra,
          "ok" if not (missing or extra) else "short %s, extra %s" % (missing, extra))
    for size, length in exp["pipe_length"].items():
        g = got["pipe_length"].get(size, 0.0)
        check("pipe " + size, abs(g - length) <= tol, "%.1f mm, expected %.1f" % (g, length))
    check("joints", got["joints"] == exp["joints"] and got["joints_failing"] == 0,
          "%d closed (%d failing), expected %d" % (got["joints"], got["joints_failing"], exp["joints"]))
    check("open ends", got["open_ends"] == exp["open_ends"],
          "%d, expected %d" % (got["open_ends"], exp["open_ends"]))
    if len(got["end_spans"]) == len(exp["end_spans"]):
        worst = max([abs(a - b) for a, b in zip(got["end_spans"], exp["end_spans"])] or [0.0])
        check("end spans", worst <= tol, "worst %.3f mm over %d spans" % (worst, len(exp["end_spans"])))
    else:
        check("end spans", False, "different number of open ends")
    ok = all(results)
    print("%s: %s (%d/%d)" % (case, "PASS" if ok else "FAIL", sum(results), len(results)))
    return ok
