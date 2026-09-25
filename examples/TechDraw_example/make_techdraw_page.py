# make_techdraw_page.py
#
# Build a TechDraw spool drawing from a finished Quetzal model:
#
#   App::Part container (welded components only)
#     -- isometric view, front view (dimensioned), top view
#     -- bill of material as a Spreadsheet, placed on the page
#     -- one balloon per mark, auto-placed on a ring around the isometric
#
# Runs against Simple_spool.FCStd, which holds a DN150 spool:
#   WN flange -- 6" pipe (w/ DN25 sockolet) -- 90 LR elbow -- WN flange
#
# Units are mm.  The macro is re-runnable: it deletes the drawing objects it
# made last time and rebuilds them, leaving the source geometry alone.
#
# RUN IN THE FreeCAD GUI (Macro -> Execute, or paste in the Python console).
# Quetzal's execute() methods need a GUI ViewObject, so this cannot run under
# freecadcmd.  See the guide (skills/techdraw-drawing/).

import glob
import math
import os
import sys

import FreeCAD
import Part
import TechDraw

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

_val = qenv.val          # Quantity -> float.  Never do arithmetic without it.


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOC_NAME = "Simple_spool"

# PTypes welded into the spool, and therefore drawn.  Everything else is
# assembly material: it belongs in the BOM but NOT in the container, because
# container membership is what drives page redraw time (guide sections 3, 13).
WELDED_PTYPES = ("Pipe", "Elbow", "Flange", "Outlet", "Tee", "Reduct", "Cap",
                 "Coupling", "Union")

ASSEMBLY_PTYPES = ("Gasket", "Bolts_Nuts", "Valve")

# Direction points from the model toward the viewer; XDirection is page-right.
# Page-up is then Direction x XDirection (guide section 6).
VIEWS = [
    # key      caption        Direction                     XDirection
    ("iso",   "Isometric",   (0.57735, 0.57735, 0.57735),  (-0.70711, 0.70711, 0.0)),
    ("front", "Front view",  (0.0, -1.0, 0.0),             (1.0, 0.0, 0.0)),
    ("top",   "Top view",    (0.0, 0.0, 1.0),              (1.0, 0.0, 0.0)),
]

# Spin the VIEWPOINT about a model axis, per view, in degrees.  This is the
# knob to reach for when the user says "turn the isometric round so I can see
# the drain": rotating about Z orbits the camera horizontally, which swaps
# which side of the run a branch appears on.
#
# Sign matters and is easy to get backwards.  Orbiting about Z cannot change
# how broadside a horizontal branch is -- only whether it points toward the
# viewer or away behind the run.  Test it: branch_axis.dot(view.Direction) > 0
# means the branch comes at the viewer and reads clear of the pipe.  For this
# spool the drain runs along -Y, so -90 brings it to the front and +90 does
# nothing useful.  Override per run with build(spin={"iso": -90}).
VIEW_SPIN = {"iso": -90.0}
SPIN_AXIS = (0.0, 0.0, 1.0)

# Never the isometric: it foreshortens, so its numbers are wrong (section 11).
# Ordered -- the first view that can show a given extent is the one that gets it.
DIMENSIONED_VIEWS = ("front", "top")
BALLOONED_VIEW = "iso"

# Page positions (mm from the page's bottom-left) on ANSI B landscape.  The
# title block owns the bottom-right corner, so nothing goes below y=70 there.
VIEW_POS = {"iso": (112.0, 196.0), "front": (100.0, 88.0), "top": (245.0, 88.0)}
SHEET_POS = (330.0, 215.0)
VIEW_BOX = (140.0, 100.0)      # each view must fit this, in page mm

# Scales worth printing on a drawing.  The fitter snaps to the first that fits.
NICE_SCALES = [1.0, 1 / 2.0, 1 / 2.5, 1 / 4.0, 1 / 5.0, 1 / 6.0, 1 / 8.0,
               1 / 10.0, 1 / 12.0, 1 / 15.0, 1 / 20.0, 1 / 25.0, 1 / 40.0,
               1 / 50.0, 1 / 100.0]

BALLOON_GAP = 12.0       # page mm from the projected outline to the bubble ring
BALLOON_MIN_SEP = 0.34   # radians between bubbles on that ring (~20 deg)
DIM_GAP = 14.0           # page mm from the outline to the first dimension line
DIM_STEP = 12.0          # page mm between stacked dimension lines
TRANSPARENCY = 50        # for a run that hides something behind it

# DN -> (NPS label, nominal inches).  Quetzal has no such table.  The inches
# are load-bearing: a long-radius elbow is R = 1.5 x NOMINAL bore, not 1.5 x OD,
# and comparing against OD misclassifies every LR elbow as short-radius.
NPS = {"DN15": ('1/2"', 0.5), "DN20": ('3/4"', 0.75), "DN25": ('1"', 1.0),
       "DN32": ('1-1/4"', 1.25), "DN40": ('1-1/2"', 1.5), "DN50": ('2"', 2.0),
       "DN65": ('2-1/2"', 2.5), "DN80": ('3"', 3.0), "DN90": ('3-1/2"', 3.5),
       "DN100": ('4"', 4.0), "DN125": ('5"', 5.0), "DN150": ('6"', 6.0),
       "DN200": ('8"', 8.0), "DN250": ('10"', 10.0), "DN300": ('12"', 12.0),
       "DN350": ('14"', 14.0), "DN400": ('16"', 16.0), "DN450": ('18"', 18.0),
       "DN500": ('20"', 20.0), "DN600": ('24"', 24.0)}

IN = 25.4


def _nps(psize):
    return NPS.get(psize, (psize, None))[0]


def sheet_is_imperial():
    """Does the user's unit schema print lengths in inches?

    Ask the schema rather than testing its name: it is the same setting that
    decides what a dimension on the page reads, so the BOM follows it and the
    drawing cannot end up half metric and half imperial.
    """
    _, _, unit = FreeCAD.Units.Quantity(25.4, "mm").getUserPreferred()
    return unit in ("in", "ft", "thou", "mil")


def _fmt_length(mm, decimals=2):
    """A length in the sheet's own units, e.g. 609.6 mm -> '24.00 in'."""
    _, factor, unit = FreeCAD.Units.Quantity(float(mm), "mm").getUserPreferred()
    return "%.*f %s" % (decimals, float(mm) / factor, unit)


def _size_label(psize):
    """Nominal size in the sheet's convention: 6" on an imperial sheet, DN150
    on a metric one.  A nominal size is a name, not a measurement, so it is
    never converted -- it is selected."""
    return _nps(psize) if sheet_is_imperial() else psize


def _nominal_mm(psize):
    inches = NPS.get(psize, (None, None))[1]
    return inches * IN if inches else None


# ---------------------------------------------------------------------------
# The view coordinate system  (guide section 6)
# ---------------------------------------------------------------------------

def spun_axes(direction, xdirection, spin_deg=0.0, axis=SPIN_AXIS):
    """Orbit a viewpoint about a model axis.

    Rotate Direction AND XDirection together.  Turning only Direction rolls
    the drawing instead of orbiting it: the model spins on the sheet and the
    page-up vector stops meaning what §6 says it means, which quietly breaks
    every balloon and dimension placed afterwards.
    """
    d = FreeCAD.Vector(*direction)
    x = FreeCAD.Vector(*xdirection)
    if spin_deg:
        rot = FreeCAD.Rotation(FreeCAD.Vector(*axis), spin_deg)
        d, x = rot.multVec(d), rot.multVec(x)
    return d, x


def view_frame(view):
    """Return the (direction, page-right, page-up) unit vectors of a view."""
    d = FreeCAD.Vector(view.Direction)
    d.normalize()
    x = FreeCAD.Vector(view.XDirection)
    x = x - d * x.dot(d)          # XDirection need not be perpendicular already
    x.normalize()
    return d, x, d.cross(x)


def source_shape(view):
    """Compound of the visible solids a view projects.

    View.Source is usually the App::Part container, which has no Shape of its
    own -- walk its Group.
    """
    shapes = []
    for src in view.Source:
        if hasattr(src, "Group"):
            shapes += [o.Shape for o in src.Group
                       if hasattr(o, "Shape") and o.ViewObject.Visibility]
        elif hasattr(src, "Shape"):
            shapes.append(src.Shape)
    return Part.makeCompound(shapes)


def view_centre(view):
    """The 3D point that lands at the view's origin.

    TechDraw's own centroid, NOT the bounding-box centre -- the two differ by
    ~160 mm on a real spool, which offsets every balloon by that much.
    """
    return TechDraw.findCentroid(source_shape(view), view.Direction)


def view_uv(view, point3d, centre=None):
    """Project a 3D model point into unscaled view coordinates.

    Balloon X/Y and OriginX/OriginY live in exactly this frame, Y up.  Multiply
    by view.Scale for page mm relative to the view's own X/Y.

    NOTE the cosmetic-vertex frame is NOT this one -- its Y is flipped.  Use
    makeCosmeticVertex3d and let TechDraw do that conversion (section 11).
    """
    _, x, y = view_frame(view)
    r = FreeCAD.Vector(point3d) - (centre if centre else view_centre(view))
    return r.dot(x), r.dot(y)


def view_extent(view):
    """Half-width and half-height of the projected outline, unscaled."""
    return _extent(source_shape(view), view.Direction, view.XDirection)


def _extent(shape, direction, xdirection):
    d = FreeCAD.Vector(direction)
    d.normalize()
    x = FreeCAD.Vector(xdirection)
    x = x - d * x.dot(d)
    x.normalize()
    y = d.cross(x)
    centre = TechDraw.findCentroid(shape, d)
    us, vs = [], []
    for vert in shape.Vertexes:
        r = vert.Point - centre
        us.append(r.dot(x))
        vs.append(r.dot(y))
    return (max(abs(min(us)), abs(max(us))), max(abs(min(vs)), abs(max(vs))))


# ---------------------------------------------------------------------------
# Tearing down the previous run
# ---------------------------------------------------------------------------

# Delete in this order: annotations reference views, views reference the page.
_DRAWING_TYPES = ("TechDraw::DrawViewBalloon", "TechDraw::DrawViewDimension",
                  "TechDraw::DrawViewAnnotation", "TechDraw::DrawViewSpreadsheet",
                  "TechDraw::DrawProjGroupItem", "TechDraw::DrawProjGroup",
                  "TechDraw::DrawViewPart", "TechDraw::DrawSVGTemplate",
                  "TechDraw::DrawPage", "Spreadsheet::Sheet")


def clear_drawing(doc):
    """Remove the drawing, the BOM and the container -- never the geometry.

    Cosmetic vertices are deleted along with their view; do NOT call
    clearCosmeticVertices() on a view that dimensions still reference.
    """
    # Our own window is about to point at a deleted page -- close it first, or
    # it lingers as a blank sheet that looks exactly like a failed build.
    _close_our_page_window(doc)
    for page in [o for o in doc.Objects if o.TypeId == "TechDraw::DrawPage"]:
        page.KeepUpdated = False          # no redraws while we dismantle it
    for type_id in _DRAWING_TYPES:
        for o in [o for o in doc.Objects if o.TypeId == type_id]:
            doc.removeObject(o.Name)
    # A container would take its children with it, so empty it first.
    for part in [o for o in doc.Objects if o.TypeId == "App::Part"]:
        part.Group = []
        doc.removeObject(part.Name)
    for type_id in ("App::Origin", "App::Line", "App::Plane", "App::Point"):
        for o in [o for o in doc.Objects if o.TypeId == type_id]:
            doc.removeObject(o.Name)
    doc.recompute()


# ---------------------------------------------------------------------------
# Container, page, views
# ---------------------------------------------------------------------------

def find_doc(name=DOC_NAME):
    """A document's internal Name is not its Label -- match either.

    Saving a new document does not rename it, so Simple_spool.FCStd may well
    still be open as "Unnamed".
    """
    for d in FreeCAD.listDocuments().values():
        if name in (d.Name, d.Label):
            return d
    raise RuntimeError("No open document named or labelled %r -- open %s.FCStd "
                       "in the GUI first." % (name, name))


def collect_welded(doc):
    """The objects that belong in the drawn container, in document order."""
    return [o for o in doc.Objects
            if o.TypeId == "Part::FeaturePython"
            and getattr(o, "PType", None) in WELDED_PTYPES]


def collect_assembly(doc):
    """Bolted-on material: in the BOM, out of the container."""
    return [o for o in doc.Objects
            if o.TypeId == "Part::FeaturePython"
            and getattr(o, "PType", None) in ASSEMBLY_PTYPES]


def make_container(doc, objs, name="Spool"):
    part = doc.addObject("App::Part", "Part")
    part.Label = name
    part.Group = objs
    doc.recompute()
    return part


def make_page(doc):
    page = doc.addObject("TechDraw::DrawPage", "Page")
    tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    tmpl.Template = os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                                 "Templates", "ASME", "ANSIB_Landscape.svg")
    page.Template = tmpl
    return page, tmpl


def fit_scale(part, box_w, box_h, spin=None):
    """Largest nice scale at which EVERY view fits box_w x box_h page mm.

    One scale for the whole drawing, so the title block can state it once.
    Spun views are measured spun -- an orbited isometric has a different
    outline, and fitting the unspun one picks the wrong scale.
    """
    spin = VIEW_SPIN if spin is None else spin
    shape = Part.makeCompound([o.Shape for o in part.Group])
    halves = [_extent(shape, *spun_axes(d, x, spin.get(k, 0.0)))
              for k, _, d, x in VIEWS]
    for s in NICE_SCALES:
        if all(hw * 2 * s <= box_w and hh * 2 * s <= box_h for hw, hh in halves):
            return s
    return NICE_SCALES[-1]


def add_view(doc, page, part, caption, direction, xdirection, scale, pos,
             hidden=False):
    """One standalone projection.

    DrawProjGroupItem with Type='Front' and a hand-set Direction, NOT a
    DrawProjGroup -- that way each view keeps its own scale, hidden-line
    setting and caption instead of inheriting the group's (section 5).
    """
    view = doc.addObject("TechDraw::DrawProjGroupItem", "View")
    view.Source = [part]
    view.Type = "Front"
    view.Direction = FreeCAD.Vector(*direction)
    view.XDirection = FreeCAD.Vector(*xdirection)
    view.ScaleType = "Custom"
    view.Scale = scale
    view.Caption = caption
    view.HardHidden = hidden
    page.addView(view)
    # addView drops the view at the centre of the page, discarding any X/Y set
    # beforehand.  Position AFTER adding, never before (section 5).
    view.X, view.Y = pos
    return view


# MDI windows this macro opened, keyed by document name.  A page window carries
# no reference to the document it belongs to -- every one of them is a bare
# QMainWindow titled "Page" -- so the only safe way to avoid closing somebody
# else's window is to remember the ones we opened ourselves.
_OUR_PAGE_WINDOWS = {}


def _close_our_page_window(doc):
    """Close the page window this macro opened for `doc`, if it still exists."""
    sub = _OUR_PAGE_WINDOWS.pop(doc.Name, None)
    if sub is None:
        return False
    try:
        sub.close()
        return True
    except RuntimeError:
        return False            # already destroyed by the user


def show_page(doc, page):
    """Open one window on the page and paint it.

    Opening a second window onto the same page does not give two views of it:
    the scene items belong to one window and every other renders as an empty
    template.  A macro that calls doubleClicked() every run accumulates blank
    page windows, and the user ends up staring at one of them wondering where
    the drawing went.

    Painting here also matters because the page is about to be set
    KeepUpdated=False -- whatever has not been drawn by then stays undrawn.
    """
    if not _HAS_GUI:
        return
    from PySide import QtGui
    mdi = FreeCADGui.getMainWindow().findChild(QtGui.QMdiArea)
    before = set(mdi.subWindowList())
    page.ViewObject.doubleClicked()
    FreeCADGui.updateGui()
    new = [s for s in mdi.subWindowList() if s not in before]
    if new:
        _OUR_PAGE_WINDOWS[doc.Name] = new[-1]
    page.requestPaint()
    FreeCADGui.updateGui()


def project_views(doc, page, views, tries=10):
    """Force each view to run HLR at least once, and WAIT for the result.

    Two separate traps here.  A view added to a page does not project by
    itself: it has to be touched and recomputed.  And a freshly created view
    does not finish projecting inside the call that made it -- its view
    provider attaches on the next turn of the GUI event loop, so the vertex
    and edge lists read as empty until updateGui() has run.

    A view with no projected geometry cannot be dimensioned, and referencing
    one takes FreeCAD down with an access violation rather than raising
    (section 11).  So block here until the geometry is really there.
    """
    page.KeepUpdated = True
    for view in views:
        view.touch()
    doc.recompute()
    for _ in range(tries):
        if all(len(v.getVisibleEdges()) for v in views):
            break
        if _HAS_GUI:
            FreeCADGui.updateGui()
        doc.recompute()
    empty = [v.Name for v in views if not len(v.getVisibleEdges())]
    if empty:
        raise RuntimeError(
            "Views %s never projected -- refusing to dimension or balloon "
            "them. Is the page's Source empty, or is this running headless?"
            % ", ".join(empty))
    return {v.Name: len(v.getVisibleEdges()) for v in views}


# ---------------------------------------------------------------------------
# Bill of material  (guide section 9)
# ---------------------------------------------------------------------------

def _schedules_matching(psize, od, thk):
    """Every pipe schedule whose table row matches this OD and thickness.

    Usually more than one -- at DN150, SCH-40, SCH-40S and SCH-STD are the
    same pipe.  Reporting all of them is honest; picking one silently is not.
    """
    hits = []
    for path in sorted(glob.glob(os.path.join(qenv.tablez_dir(), "Pipe_*.csv"))):
        name = os.path.basename(path)
        try:
            row = qenv.read_row(name, psize)
        except Exception:
            continue
        if not row:
            continue
        r_od, r_thk = qenv.f(row, "OD"), qenv.f(row, "thk")
        if r_od and r_thk and abs(r_od - od) < 0.01 and abs(r_thk - thk) < 0.01:
            hits.append(name[5:-4])          # strip "Pipe_" and ".csv"
    return [h for h in hits if h.startswith("SCH-")] or hits


def _describe(obj):
    """A DRAFT description.  Material grades are not in the model.

    PRating is a maker leftover, not a spec field -- a 10" A106 pipe can carry
    PRating='ConduitEMT-LIGHT'.  Anything not derivable from geometry is
    emitted as a <...> placeholder for the user to overwrite (section 9).
    """
    ptype = obj.PType
    if ptype == "Pipe":
        sched = "/".join(_schedules_matching(
            obj.PSize, _val(obj.OD), _val(obj.thk))) or "<SCH?>"
        return "PIPE, %s, <A106 GR B SMLS>" % sched
    if ptype == "Elbow":
        sched = "/".join(_schedules_matching(
            obj.PSize, _val(obj.OD), _val(obj.thk))) or "<SCH?>"
        nominal = _nominal_mm(obj.PSize)
        ratio = _val(obj.BendRadius) / nominal if nominal else 0.0
        arm = "LR" if ratio > 1.25 else "SR"      # 1.5 x nominal vs 1.0 x nominal
        return "ELBOW, %s %d, %s, <A234 WPB>" % (
            arm, int(round(_val(obj.BendAngle))), sched)
    if ptype == "Flange":
        return "FLANGE, RF %s %s, <BORE>, <A105>" % (obj.FlangeType, obj.FClass)
    if ptype == "Outlet":
        return "OUTLET, %s %s, on %s run, <A105>" % (
            obj.EndType, obj.PRating, _size_label(_carrier_dn(obj)))
    if ptype == "Gasket":
        return "GASKET, %s RF, <SPIRAL WOUND>" % obj.PRating
    if ptype == "Bolts_Nuts":
        return "BOLTS AND NUTS FOR %s %s FLG, <A193 B7 / A194 2H>" % (
            _size_label(obj.PSize), obj.PRating)
    if ptype == "Valve":
        return "VALVE, %s, <describe>" % obj.PRating
    return "%s, <describe>" % ptype.upper()


def _carrier_dn(outlet):
    """Best-effort run size for a branch outlet, from its carrier OD."""
    carrier = _val(outlet.CarrierOD)
    for psize in NPS:
        for sched in ("SCH-40", "SCH-STD", "SCH-80"):
            try:
                row = qenv.read_row("Pipe_%s.csv" % sched, psize)
            except Exception:
                continue
            if row and abs(qenv.f(row, "OD") - carrier) < 0.01:
                return psize
    return "?"


def _bom_key(obj):
    """Two objects share a mark when every spec-bearing field matches.

    Keyed on geometry, not on PRating alone.  Length is deliberately absent:
    two pipes of different length are still the same pipe on a cut list.
    """
    key = [obj.PType, obj.PSize]
    for prop in ("OD", "thk", "BendAngle", "BendRadius", "FClass",
                 "FlangeType", "EndType", "PRating", "CarrierOD"):
        if prop in obj.PropertiesList:
            v = getattr(obj, prop)
            key.append(round(_val(v), 3) if hasattr(v, "Value") else v)
    return tuple(key)


def build_bom(welded, assembly):
    """Group the model into marks.  Returns (rows, {obj.Name: mark}).

    Pipe is quantified as a summed length, everything else as a count.
    """
    groups = []
    for obj in list(welded) + list(assembly):
        key = _bom_key(obj)
        for g in groups:
            if g["key"] == key:
                g["objs"].append(obj)
                break
        else:
            groups.append({"key": key, "objs": [obj], "welded": obj in welded})

    rows, marks = [], {}
    for i, g in enumerate(groups, start=1):
        first = g["objs"][0]
        if first.PType == "Pipe":
            qty = _fmt_length(sum(_val(o.Height) for o in g["objs"]))
        else:
            qty = str(len(g["objs"]))
        rows.append((str(i), qty, _size_label(first.PSize), _describe(first),
                     g["welded"]))
        for o in g["objs"]:
            marks[o.Name] = str(i)
    return rows, marks


def _text(sheet, cell, value):
    """Write a cell as literal text.

    Spreadsheet.set() parses what it is given: '6"' becomes the quantity
    6 inches and displays as 152.4 mm, which quietly turns the Size column of
    a BOM into millimetres.  A leading apostrophe forces text (section 9).
    """
    sheet.set(cell, "'" + str(value))


def write_bom(doc, page, rows):
    sheet = doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
    for col, head in zip("ABCD", ("Mark", "Qty", "Size", "Description")):
        _text(sheet, "%s1" % col, head)

    row_no = 2
    for mark, qty, size, desc, _ in [r for r in rows if r[4]]:
        for col, val in zip("ABCD", (mark, qty, size, desc)):
            _text(sheet, "%s%d" % (col, row_no), val)
        row_no += 1
    loose = [r for r in rows if not r[4]]
    if loose:
        row_no += 1
        _text(sheet, "D%d" % row_no, "Assembly materials")
        row_no += 1
        for mark, qty, size, desc, _ in loose:
            for col, val in zip("ABCD", (mark, qty, size, desc)):
                _text(sheet, "%s%d" % (col, row_no), val)
            row_no += 1
    doc.recompute()

    view = doc.addObject("TechDraw::DrawViewSpreadsheet", "Sheet")
    view.Source = sheet
    view.CellStart = "A1"
    view.CellEnd = "D%d" % (row_no - 1)
    page.addView(view)
    view.X, view.Y = SHEET_POS          # after addView, which recentres it
    return sheet, view


# ---------------------------------------------------------------------------
# Balloons  (guide section 10)
# ---------------------------------------------------------------------------

def _radius_at(shape, station, axis):
    """Outer radius of a solid where a plane at `station` cuts it."""
    try:
        wires = shape.slice(axis, station.dot(axis))
    except Exception:
        return 0.0
    best = 0.0
    for w in wires:
        for v in w.Vertexes:
            best = max(best, (v.Point
                              - _project_onto_axis(v.Point, station, axis)).Length)
    return best


def _flange_hub_anchor(flange, view, centre):
    """Land a flange's leader on the HUB silhouette, behind the disc.

    A leader that ends on the centreline -- which is what the bounding-box
    centre gives -- points at every component on that axis at once, so a
    flange balloon reads equally well as a call-out for the pipe welded to it.
    Worse, a weld-neck hub runs out to exactly the pipe OD at the weld end
    (84.20 mm against the pipe's 84.14 here), so even the silhouette is shared
    there.

    The one place the flange is unmistakably itself is the hub, just behind the
    disc, where the neck is still far wider than the pipe.  Walk out from the
    raised face until the section drops below the disc OD -- that station is
    the back of the disc -- and take the silhouette radius there.
    """
    ports = _gports(flange)
    if len(ports) < 2:
        return flange.Shape.BoundBox.Center
    face, weld = ports[0][0], ports[1][0]
    axis = weld - face
    length = axis.Length
    if length < 1e-6:
        return flange.Shape.BoundBox.Center
    axis.normalize()

    disc_r = _val(flange.D) / 2.0 if "D" in flange.PropertiesList else None
    station, radius = None, 0.0
    steps = 40
    for i in range(1, steps + 1):
        pt = face + axis * (length * i / float(steps))
        r = _radius_at(flange.Shape, pt, axis)
        if r <= 0.0:
            continue
        if disc_r is None or r < disc_r * 0.95:
            station, radius = pt, r          # first station past the disc
            break
    if station is None:                      # no hub (SO, blind, LJ): use the rim
        station = face + axis * (length * 0.5)
        radius = _radius_at(flange.Shape, station, axis)

    # Offset to the silhouette: perpendicular to both the flange axis and the
    # line of sight, so the point sits on the outline rather than inside it.
    radial = axis.cross(FreeCAD.Vector(view.Direction))
    if radial.Length < 1e-6:                 # flange seen end-on: no silhouette
        return station
    radial.normalize()
    a, b = station + radial * radius, station - radial * radius
    # Whichever side reads further from the middle of the view is the side the
    # leader can reach without crossing the spool.
    ua, va = view_uv(view, a, centre)
    ub, vb = view_uv(view, b, centre)
    return a if (ua * ua + va * va) >= (ub * ub + vb * vb) else b


def balloon_anchor(obj, view, centre):
    """Where a component's leader should land.

    Flanges get the hub treatment above; everything else is unambiguous enough
    from its centre, because a leader into the middle of a pipe run or an
    elbow has only one thing it could mean.
    """
    if getattr(obj, "PType", None) == "Flange":
        return _flange_hub_anchor(obj, view, centre)
    return obj.Shape.BoundBox.Center


def add_balloons(doc, page, view, objs, marks):
    """One balloon per component: arrow on the part, bubble on a ring.

    The bubble sits outside the projected outline at the angle of its own
    component, so nothing lands on top of the geometry.  Bubbles that still
    collide are for the user to drag apart.
    """
    centre = view_centre(view)
    half_w, half_h = view_extent(view)
    gap = BALLOON_GAP / view.Scale
    ring_u, ring_v = half_w + gap, half_h + gap

    # Work out every bubble's angle first, then space them, then create them.
    placed = []
    for obj in objs:
        u, v = view_uv(view, balloon_anchor(obj, view, centre), centre)
        # The arrow tip stays on the part; only the bubble's angle is adjusted.
        angle = math.atan2(v, u) if math.hypot(u, v) > 1e-6 else 0.0
        # Skip the bottom sector: the view's Caption is printed there and a
        # bubble would land on top of it.
        if -1.92 < angle < -1.22:         # within ~20 deg of straight down
            angle = -1.92 if angle < -1.57 else -1.22
        placed.append([angle, u, v, obj])

    # Two components at the same bearing -- or two clamped to the same edge of
    # the skipped sector -- otherwise stack in exactly the same spot.  This is
    # spacing, not collision avoidance: bubbles that merely crowd are left for
    # the user to drag.
    placed.sort(key=lambda p: p[0])
    for i in range(1, len(placed)):
        if placed[i][0] - placed[i - 1][0] < BALLOON_MIN_SEP:
            placed[i][0] = placed[i - 1][0] + BALLOON_MIN_SEP

    balloons = []
    for angle, u, v, obj in placed:
        b = doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
        b.SourceView = view
        b.Text = marks[obj.Name]
        b.BubbleShape = "Circular"
        b.EndType = "Filled arrow"
        page.addView(b)
        b.OriginX, b.OriginY = u, v                  # arrow tip, on the part
        b.X = math.cos(angle) * ring_u               # bubble, on the ring
        b.Y = math.sin(angle) * ring_v
        balloons.append(b)
    page.NextBalloonIndex = len(balloons) + 1
    return balloons


# ---------------------------------------------------------------------------
# Dimensions  (guide section 11)
# ---------------------------------------------------------------------------

def _cosmetic_indices(view, count):
    """Vertex indices of the last `count` cosmetic vertices on a view.

    Cosmetics are appended after the projected vertices, in creation order.
    The names in References2D are 0-BASED and line up with getVertexByIndex.
    """
    total = len(view.getVisibleVertexes()) + len(view.getHiddenVertexes())
    if total < count:
        raise RuntimeError(
            "%s reports %d vertices but %d cosmetics were just added -- the "
            "view has not projected.  Call project_views() first."
            % (view.Name, total, count))
    return list(range(total - count, total))


# --- work points -----------------------------------------------------------
#
# A pipe drawing is set out from WORK POINTS: flange faces, and the centreline
# intersections of fittings.  Everything below exists to find those in the
# model rather than measuring the outside of the steel.

def _gports(obj):
    """This object's ports as (position, direction) in global coordinates."""
    return [(obj.Placement.multVec(p), obj.Placement.Rotation.multVec(d))
            for p, d in zip(obj.Ports, obj.PortDirections)]


def _attached(obj, port_pos, objs, tol=0.5):
    """The component welded to `obj` at `port_pos`, if any."""
    for other in objs:
        if other is obj:
            continue
        for pos, _ in _gports(other):
            if pos.distanceToPoint(port_pos) < tol:
                return other
    return None


def _line_intersection(p0, d0, p1, d1):
    """Where two port axes cross -- an elbow's work point."""
    if d0.cross(d1).Length < 1e-9:
        return None                                  # parallel: no work point
    w = p1 - p0
    denom = d0.dot(d0) * d1.dot(d1) - d0.dot(d1) ** 2
    if abs(denom) < 1e-9:
        return None
    t = (w.dot(d0) * d1.dot(d1) - w.dot(d1) * d0.dot(d1)) / denom
    return p0 + d0 * t


def _project_onto_axis(point, line_pt, line_dir):
    """Drop `point` onto a centreline -- where a branch meets its run."""
    return line_pt + line_dir * (point - line_pt).dot(line_dir)


def _carrier_pipe(outlet, objs):
    """The run a branch outlet sits on: (pipe, axis point, axis direction).

    A branch outlet is not port-connected to its run -- it sits on the OD,
    while the run's ports are at its ends -- so match it by carrier OD and
    proximity to the axis instead.
    """
    want = _val(getattr(outlet, "CarrierOD", 0.0))
    opos = _gports(outlet)[0][0]
    for o in objs:
        if o.PType != "Pipe" or abs(_val(o.OD) - want) > 0.01:
            continue
        ports = _gports(o)
        if len(ports) < 2:
            continue
        a, b = ports[0][0], ports[1][0]
        axis = b - a
        if axis.Length < 1e-9:
            continue
        axis.normalize()
        if opos.distanceToPoint(_project_onto_axis(opos, a, axis)) < _val(o.OD):
            return o, a, axis
    return None, None, None


def _resolve_work_point(obj, port_pos, welded):
    """The work point a pipe end runs to -> (point, kind, anchor component).

    A flange resolves to its raised FACE -- the datum a fitter measures from,
    not the weld.  An elbow resolves to the intersection of its port axes, so
    a pipe into an elbow is dimensioned to the corner rather than the tangent
    point.  A free end is its own work point.

    The third value is the component the dimension should visually attach to,
    which is not always the one that defines the point: an elbow's work point
    lies on the centreline of whatever the elbow turns INTO, so the extension
    line belongs on that far component (§11.5.4).
    """
    neighbour = _attached(obj, port_pos, welded)
    if neighbour is None:
        return port_pos, "end", obj
    if neighbour.PType == "Flange":
        faces = [p for p, _ in _gports(neighbour)
                 if p.distanceToPoint(port_pos) > 0.5]
        return (faces[0] if faces else port_pos), "face", neighbour
    if neighbour.PType == "Elbow":
        ports = _gports(neighbour)
        if len(ports) >= 2:
            wp = _line_intersection(ports[0][0], ports[0][1],
                                    ports[1][0], ports[1][1])
            if wp is not None:
                far = None
                for pos, _ in ports:
                    if pos.distanceToPoint(port_pos) > 0.5:
                        far = _attached(neighbour, pos, welded) or far
                return wp, "CL", (far or neighbour)
    if neighbour.PType == "Outlet":
        run, a, axis = _carrier_pipe(neighbour, welded)
        if a is not None:
            return _project_onto_axis(port_pos, a, axis), "run CL", run
    return port_pos, "weld", neighbour


def _anchor_to(point, comp, axis, side):
    """Slide `point` along `axis` to the edge of `comp` facing the dimension.

    The measured coordinate is untouched -- for a DistanceY dimension this
    only moves the point sideways -- so the value cannot change.  What it
    fixes is the extension line: anchored on the pipe centreline it runs right
    across the view and touches nothing, which is how a correct number ends up
    attached to the wrong feature (§11.5.4).
    """
    if comp is None or not hasattr(comp, "Shape"):
        return point
    # Project the BOUNDING BOX corners, not Shape.Vertexes.  A turned part like
    # a flange has vertices only where its surfaces seam, so the widest point
    # of the disc is not a vertex at all and the anchor lands short of the rim.
    bb = comp.Shape.BoundBox
    corners = [FreeCAD.Vector(x, y, z)
               for x in (bb.XMin, bb.XMax)
               for y in (bb.YMin, bb.YMax)
               for z in (bb.ZMin, bb.ZMax)]
    vals = [c.dot(axis) for c in corners]
    target = min(vals) if side < 0 else max(vals)
    return point + axis * (target - point.dot(axis))


def plan_dimensions(view, part, welded, already=()):
    """Dimension each PIPE between the work points at its two ends.

    Two rules drive this, and both come from how a spool is actually built:

    * **Dimension to work points, not to the metal.**  A bounding-box
      dimension is the right number measured between the wrong two things: it
      says where the steel ends, when what a fitter sets out is where the
      centrelines cross and where a flange face lands.
    * **A leg with no pipe in it needs no dimension.**  Where two fittings are
      welded straight together, the distance between their work points is
      fixed by the catalogue take-outs.  The fitter cannot change it and has
      no use for it.  So iterate over pipes, not over legs.

    A view only gets a dimension whose span it can actually show: a branch
    running parallel to a view's Direction projects onto the run behind it and
    is invisible there, however obvious it is in 3D.
    """
    _, x_axis, y_axis = view_frame(view)
    half_w, half_h = view_extent(view)

    # Offsets are page mm from the view origin (a dimension's ScaleType is
    # 'Page').  Extra room below: the view's Caption prints there too.
    below = -(half_h * view.Scale + DIM_GAP + DIM_STEP)
    left = -(half_w * view.Scale + DIM_GAP)
    right = half_w * view.Scale + DIM_GAP

    def placement(span):
        """DistanceX or DistanceY, and where to park it, for a 3D span."""
        unit = FreeCAD.Vector(span)
        if unit.Length < 1e-9:
            return None
        unit.normalize()
        if abs(unit.dot(x_axis)) > 0.9:
            return "DistanceX", (0.0, below)
        if abs(unit.dot(y_axis)) > 0.9:
            return "DistanceY", (left, 0.0)
        return None                  # skew or edge-on: this view cannot show it

    def anchored(kind, offset, pairs):
        """Slide both anchors sideways onto the features they measure."""
        axis = x_axis if kind == "DistanceY" else y_axis
        side = -1 if (offset[0] if kind == "DistanceY" else offset[1]) < 0 else 1
        return [_anchor_to(pt, comp, axis, side) for pt, comp in pairs]

    wanted = []
    for pipe in [o for o in welded if o.PType == "Pipe"]:
        ports = _gports(pipe)
        if len(ports) < 2:
            continue
        p_a, kind_a, comp_a = _resolve_work_point(pipe, ports[0][0], welded)
        p_b, kind_b, comp_b = _resolve_work_point(pipe, ports[1][0], welded)
        spec = placement(p_b - p_a)
        if not spec:
            continue
        kind, offset = spec
        span = (p_b - p_a).Length
        a, b = anchored(kind, offset, [(p_a, comp_a), (p_b, comp_b)])
        wanted.append((kind, a, b, offset,
                       "%s %s to %s" % (_size_label(pipe.PSize), kind_a, kind_b),
                       span))

    # Locate each branch along its run: datum face -> where the branch
    # centreline crosses the run centreline.  Stacking a second parallel
    # dimension on the same side overlaps its text however far apart the lines
    # are, so this one goes on the opposite side.
    for outlet in [o for o in welded if o.PType == "Outlet"]:
        run, a, axis = _carrier_pipe(outlet, welded)
        if run is None:
            continue
        cross = _project_onto_axis(_gports(outlet)[0][0], a, axis)
        datum, _, datum_comp = _resolve_work_point(run, _gports(run)[0][0], welded)
        spec = placement(cross - datum)
        if not spec:
            continue
        kind, _ = spec
        offset = (right, 0.0) if kind == "DistanceY" else (0.0, below - DIM_STEP)
        span = (cross - datum).Length
        p, q = anchored(kind, offset, [(datum, datum_comp), (cross, run)])
        wanted.append((kind, p, q, offset, "Face to branch CL", span))

    # Two views usually share a model axis, so dimension a given span once, on
    # the first view asked for it.
    return [w for w in wanted if w[4] not in already]


def attach_dimensions(doc, page, view, wanted):
    """Dimension between points we place ourselves, not found geometry.

    A projected Vertex index re-numbers whenever the model or the view
    direction changes, so a dimension attached to one silently moves.  Instead
    drop a cosmetic vertex at a known 3D point and dimension between those --
    which is what the hand-built Jumper_spool drawing does.
    """
    if not wanted:
        return []

    # Place every cosmetic vertex first, then recompute once: each recompute
    # renumbers, so interleaving creation and lookup gets the wrong indices.
    #
    # Use makeCosmeticVertex with our OWN Y-up projection, not the convenient
    # makeCosmeticVertex3d.  That helper stores Point.y in the Y-DOWN scene
    # frame, but the dimension renderer reads it as Y-UP, so every anchor comes
    # out mirrored about the view centre.  The separation is unchanged, so the
    # dimension still reads the correct value while pointing at the wrong two
    # places -- see guide section 11.5.4.
    centre = view_centre(view)
    for _, p1, p2, _, _, _ in wanted:
        for pt in (p1, p2):
            u, w = view_uv(view, pt, centre)
            view.makeCosmeticVertex(FreeCAD.Vector(u, w, 0.0))
    view.touch()
    doc.recompute()
    idx = _cosmetic_indices(view, 2 * len(wanted))

    # AutoCorrectRefs rewrites References2D behind your back -- it turned a
    # valid pair into a vertex that did not exist, and the dimension then read
    # 0.00 mm on the page without erroring.  Off while we attach.
    prm = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
    autocorrect = prm.GetBool("AutoCorrectRefs")
    prm.SetBool("AutoCorrectRefs", False)
    try:
        dims = []
        for i, (kind, _, _, (dx, dy), label, expected) in enumerate(wanted):
            d = doc.addObject("TechDraw::DrawViewDimension", "Dimension")
            d.Type = kind
            d.References2D = [(view, ("Vertex%d" % idx[2 * i],
                                      "Vertex%d" % idx[2 * i + 1]))]
            d.FormatSpec = "%.1w"
            d.Label = label
            page.addView(d)
            d.X, d.Y = dx, dy           # after addView, which recentres it
            dims.append((d, expected))
        doc.recompute()
    finally:
        prm.SetBool("AutoCorrectRefs", autocorrect)
    return dims


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def set_transparency(welded):
    """Make a run see-through where a branch assembly sits behind it.

    This is a 3D ViewObject property.  It changes what the user sees in the 3D
    window; it does NOT change the projected edges, so the drawing is
    unaffected either way (section 8).
    """
    for tube in [o for o in welded if o.PType == "Pipe"]:
        axis_len = _val(tube.Height)
        if any(o.PType == "Outlet"
               and o.Shape.BoundBox.Center.distanceToPoint(
                   tube.Shape.BoundBox.Center) < axis_len
               for o in welded):
            tube.ViewObject.Transparency = TRANSPARENCY
            return tube
    return None


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(doc=None, spin=None):
    """Build the page.  `spin` re-orbits named views, e.g. {"iso": -90}."""
    spin = VIEW_SPIN if spin is None else spin
    doc = doc or find_doc()
    # TechDraw's helpers act on the active document, not on the one you pass.
    FreeCAD.setActiveDocument(doc.Name)
    clear_drawing(doc)

    welded = collect_welded(doc)
    assembly = collect_assembly(doc)
    if not welded:
        raise RuntimeError("No welded Quetzal components found in %s" % doc.Name)

    part = make_container(doc, welded)
    page, tmpl = make_page(doc)
    scale = fit_scale(part, *VIEW_BOX, spin=spin)

    views = {}
    for key, caption, direction, xdirection in VIEWS:
        d_axis, x_axis = spun_axes(direction, xdirection, spin.get(key, 0.0))
        views[key] = add_view(doc, page, part, caption, d_axis, x_axis,
                              scale, VIEW_POS[key], hidden=(key == "top"))
    edge_counts = project_views(doc, page, list(views.values()))

    # Everything that reads projected geometry goes first, while the views are
    # freshly computed and nothing else has touched the page.  Each view is
    # asked what it alone can show, so a branch that is edge-on in the front
    # view still gets dimensioned on the top view.
    dims, labelled = [], set()
    for key in DIMENSIONED_VIEWS:
        wanted = plan_dimensions(views[key], part, welded, labelled)
        dims += attach_dimensions(doc, page, views[key], wanted)
        labelled.update(w[4] for w in wanted)

    rows, marks = build_bom(welded, assembly)
    sheet, sheet_view = write_bom(doc, page, rows)
    balloons = add_balloons(doc, page, views[BALLOONED_VIEW], welded, marks)
    clear_run = set_transparency(welded)

    tmpl.EditableTexts = dict(
        tmpl.EditableTexts,
        **{"DrawingTitle1": doc.Label.replace("_", " ").upper(),
           "DrawingTitle2": "WELD SPOOL",
           "Scale": "1:%g" % round(1.0 / scale, 4)})

    doc.recompute()
    # Paint the page BEFORE switching updates off, or it stays blank on screen
    # however complete the object tree is.
    show_page(doc, page)
    page.KeepUpdated = False       # leave it off: the user re-enables to print
    report(doc, page, part, views, scale, rows, balloons, dims, clear_run,
           edge_counts)
    return doc


# ---------------------------------------------------------------------------
# Report / numeric verification  (guide section 14)
# ---------------------------------------------------------------------------

def report(doc, page, part, views, scale, rows, balloons, dims, clear_run,
           edge_counts):
    lines = ["\n=== TechDraw page built on %s ===" % doc.Label]
    lines.append("  Container : %s -> %s"
                 % (part.Label, ", ".join(o.Name for o in part.Group)))
    excluded = [o.Name for o in doc.Objects
                if o.TypeId == "Part::FeaturePython" and o not in part.Group]
    lines.append("  Excluded  : %s" % (", ".join(excluded) or "(none)"))

    shape = Part.makeCompound([o.Shape for o in part.Group])
    lines.append("  Geometry  : %d solids, %d faces, %d edges  (drives redraw time)"
                 % (len(shape.Solids), len(shape.Faces), len(shape.Edges)))
    lines.append("  Page      : %s, KeepUpdated=%s, scale 1:%g, template %s"
                 % (page.Label, page.KeepUpdated, round(1.0 / scale, 4),
                    os.path.basename(page.Template.Template)))

    for key, view in views.items():
        hw, hh = view_extent(view)
        lines.append("  View %-6s: %-10s %6.1f x %5.1f mm on page, "
                     "HardHidden=%-5s %d projected edges"
                     % (key, view.Caption, hw * 2 * scale, hh * 2 * scale,
                        view.HardHidden, edge_counts.get(view.Name, 0)))

    lines.append("  BOM       : %d marks  (<...> = fill in by hand)" % len(rows))
    for mark, qty, size, desc, welded_flag in rows:
        lines.append("     %-3s %-10s %-7s %s%s"
                     % (mark, qty, size, desc,
                        "" if welded_flag else "   [assembly]"))

    tmpl = page.Template
    iso = views[BALLOONED_VIEW]
    off = []
    for b in balloons:
        px = _val(iso.X) + _val(b.X) * iso.Scale
        py = _val(iso.Y) + _val(b.Y) * iso.Scale
        if not (0 <= px <= _val(tmpl.Width) and 0 <= py <= _val(tmpl.Height)):
            off.append("%s(mark %s) at (%.1f, %.1f)" % (b.Name, b.Text, px, py))
    lines.append("  Balloons  : %d on %s, %d off-sheet%s"
                 % (len(balloons), iso.Caption, len(off),
                    (" -> " + "; ".join(off)) if off else ""))

    # Assembly material is in the BOM but not in the container, so it is not
    # drawn and cannot carry a balloon.  Say which marks those are rather than
    # leaving the reader to notice a gap in the numbering.
    ballooned = set(b.Text for b in balloons)
    unballooned = [(r[0], r[3], r[4]) for r in rows if r[0] not in ballooned]
    for mark, desc, welded_flag in unballooned:
        why = ("NOT DRAWN - welded part missing from the container!"
               if welded_flag else "assembly material, not drawn")
        lines.append("     mark %-3s no balloon (%s)" % (mark, why))

    # A "%w" FormatSpec renders in the USER's unit schema, so the same file
    # prints millimetres on one machine and inches on the next.  Name it.
    schema = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Units").GetInt("UserSchema")
    schema_name = FreeCAD.Units.listSchemas()[schema] \
        if hasattr(FreeCAD.Units, "listSchemas") else str(schema)
    lines.append("  Dimensions: %d, printed in the '%s' unit schema"
                 % (len(dims), schema_name))
    on_view = {}
    for key in DIMENSIONED_VIEWS:
        on_view[views[key].Name] = views[key].Caption
    for d, expected in dims:
        got = d.getRawValue()
        flag = "OK " if abs(got - expected) < 0.05 else "BAD"
        parent = on_view.get(d.References2D[0][0].Name, "?")
        lines.append("     %s %-18s %-9s reads %9.2f mm  model %9.2f mm  [%s]"
                     % (flag, d.Label, d.Type, got, expected, parent))

    lines.append("  Clear run : %s"
                 % (("%s at %d%% transparency" % (clear_run.Name, TRANSPARENCY))
                    if clear_run else "(none needed)"))
    lines.append("")
    FreeCAD.Console.PrintMessage("\n".join(lines))
    return "\n".join(lines)


if __name__ == "__main__":
    build()
