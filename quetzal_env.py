# -*- coding: utf-8 -*-
"""Locate the installed Quetzal workbench and read its dimension tables.

The macros in ``examples/`` live in *this* repo but build geometry with the
`Quetzal <https://github.com/oddtopus/quetzal>`_ FreeCAD workbench: they
``import pCmd`` from it and read its ``tablez/*.csv`` dimension tables.  This
module is the one place that knows how to find that installation.

Resolution order (first hit that contains ``pCmd.py`` wins):

1. the ``QUETZAL_DIR`` environment variable;
2. a ``.quetzal_path`` file at the root of this repo, holding one path.
   FreeCAD launched from the Start menu does not inherit a shell-set
   environment variable, so on Windows this is usually the easier option;
3. ``FreeCAD.getUserAppDataDir()/Mod/{quetzal,Quetzal}``;
4. ``FreeCAD.getResourceDir()/Mod/{quetzal,Quetzal}``.

Typical use from a macro::

    import os, sys
    _here = os.path.dirname(os.path.abspath(__file__))
    while _here and not os.path.isfile(os.path.join(_here, "quetzal_env.py")):
        _here = os.path.dirname(_here) if os.path.dirname(_here) != _here else ""
    if _here and _here not in sys.path:
        sys.path.insert(0, _here)
    import quetzal_env as qenv

    pCmd = qenv.import_pcmd()
    row  = qenv.read_row("Pipe_SCH-STD.csv", "DN200")
    OD   = qenv.f(row, "OD")

Everything here is plain stdlib except :func:`find_quetzal_dir`, which consults
FreeCAD's own directories when they are available.  Importing this module
outside FreeCAD is fine; only the FreeCAD-dependent candidates are skipped.
"""

import csv
import os
import sys

__all__ = [
    "QuetzalNotFound",
    "find_quetzal_dir",
    "import_pcmd",
    "tablez_dir",
    "table_path",
    "read_row",
    "f",
    "val",
    "IN",
]

IN = 25.4  # mm per inch -- units are millimetres throughout (guide §1.2)

_ENV_VAR = "QUETZAL_DIR"
_PATH_FILE = ".quetzal_path"

_cached_dir = None


class QuetzalNotFound(RuntimeError):
    """Raised when the Quetzal workbench directory cannot be located."""


def _is_quetzal_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, "pCmd.py"))


def _path_file_candidate():
    """The path recorded in ``.quetzal_path`` beside this module, if any."""
    here = os.path.dirname(os.path.abspath(__file__))
    fpath = os.path.join(here, _PATH_FILE)
    if not os.path.isfile(fpath):
        return None
    with open(fpath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                return os.path.expanduser(os.path.expandvars(line))
    return None


def _freecad_candidates():
    """Mod/ directories under FreeCAD's user and resource dirs."""
    try:
        import FreeCAD
    except ImportError:
        return []
    roots = []
    for getter in ("getUserAppDataDir", "getResourceDir"):
        try:
            roots.append(getattr(FreeCAD, getter)())
        except Exception:
            pass
    cands = []
    for root in roots:
        for name in ("quetzal", "Quetzal"):
            cands.append(os.path.join(root, "Mod", name))
    return cands


def _already_imported_candidate():
    """If pCmd is already in the session, believe it.

    Quetzal puts a ``/./`` in ``sys.path``, so normalise that out (guide §2.3).
    """
    mod = sys.modules.get("pCmd")
    fpath = getattr(mod, "__file__", None)
    if not fpath:
        return None
    return os.path.dirname(fpath.replace(os.sep + "." + os.sep, os.sep))


def find_quetzal_dir(refresh=False):
    """Return the Quetzal workbench directory, or raise :class:`QuetzalNotFound`."""
    global _cached_dir
    if _cached_dir and not refresh:
        return _cached_dir

    candidates = [
        os.environ.get(_ENV_VAR),
        _path_file_candidate(),
        _already_imported_candidate(),
    ]
    candidates.extend(_freecad_candidates())

    for cand in candidates:
        if _is_quetzal_dir(cand):
            _cached_dir = os.path.abspath(cand)
            return _cached_dir

    raise QuetzalNotFound(
        "Cannot locate the Quetzal workbench (no directory containing pCmd.py).\n"
        "Tried: %s=%r, %s, an already-imported pCmd, and FreeCAD's Mod/ dirs.\n"
        "Fix it by setting %s, or by writing the path into %s at the root of "
        "this repo (see README.md)."
        % (_ENV_VAR, os.environ.get(_ENV_VAR), _PATH_FILE, _ENV_VAR, _PATH_FILE)
    )


def import_pcmd():
    """Put Quetzal on ``sys.path`` and return its ``pCmd`` module."""
    qdir = find_quetzal_dir()
    if qdir not in sys.path:
        sys.path.insert(0, qdir)
    import pCmd  # noqa: E402  (deliberately deferred until the path is set)
    return pCmd


def tablez_dir():
    """The ``tablez/`` directory inside the Quetzal installation."""
    return os.path.join(find_quetzal_dir(), "tablez")


def table_path(csv_name):
    """Full path to ``tablez/<csv_name>``."""
    return os.path.join(tablez_dir(), csv_name)


def read_row(csv_name, psize, fieldnames=None, **match):
    """Return the row for ``PSize == psize`` from ``tablez/<csv_name>``.

    The tables are ``;``-delimited and carry a UTF-8 BOM (guide §6).

    ``fieldnames`` supplies a header for the header-less tables (e.g.
    ``Union_3000lb_SW.csv``).  Extra keyword arguments are additional exact
    string matches on other columns -- ``PSizeBranch="DN50"`` for a reducing
    fitting, ``Ang="45"`` for an elbow table that holds several angles.  A
    keyword whose value is ``None`` is ignored, so callers can pass an optional
    filter straight through.
    """
    filters = {k: v for k, v in match.items() if v is not None}
    with open(table_path(csv_name), "r", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";", fieldnames=fieldnames):
            if str(row.get("PSize", "")).strip() != psize:
                continue
            if all(str(row.get(k, "")).strip() == str(v)
                   for k, v in filters.items()):
                return row
    raise RuntimeError(
        "No row for PSize=%s%s in %s"
        % (psize, " %s" % filters if filters else "", csv_name))


def f(row, key, default=None):
    """Float from a CSV row by column NAME, tolerating a blank/missing column.

    Column sets differ between tables (guide §6), so a caller that wants a
    column which may not exist passes a ``default``.
    """
    v = row.get(key, "")
    if v is None or str(v).strip() == "":
        if default is not None:
            return default
        raise KeyError(key)
    return float(v)


def val(x):
    """FreeCAD ``Quantity`` (or plain number) -> ``float``.

    Object properties are ``Quantity``, not ``float``; doing arithmetic on one
    directly is the single most common runtime error in these macros
    (guide §1.9).  Never skip this.
    """
    try:
        return float(x.Value)
    except AttributeError:
        return float(x)
