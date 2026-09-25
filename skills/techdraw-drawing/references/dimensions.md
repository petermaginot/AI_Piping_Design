# Dimensions (§11)

Part of the `techdraw-drawing` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 11. Dimensions

### 11.1 Dimension to points you placed yourself

`References2D` points at projected geometry by index — `('View002', ('Vertex12',
'Vertex219'))`. Those indices are positions in the edge soup that hidden-line
removal produced. Change the model, the view direction, or the hidden-line
setting, and they renumber. The dimension does not error; it silently measures
something else.

Place your own points instead:

```python
view.makeCosmeticVertex3d(p1)     # model-space points
view.makeCosmeticVertex3d(p2)
view.touch(); doc.recompute()
```

Cosmetic vertices are appended **after** the projected ones, in creation order,
so create all of them, recompute **once**, and then take the indices — each
recompute renumbers, and interleaving creation with lookup gets it wrong:

```python
total = len(view.getVisibleVertexes()) + len(view.getHiddenVertexes())
indices = range(total - n_cosmetic, total)    # 0-BASED, matches getVertexByIndex
```

The names in `References2D` are **0-based**: `"Vertex51"` is
`getVertexByIndex(51)`. Using 1-based names produces a dimension that reads
0.00 mm.

`TechDraw.makeDistanceDim3d(view, kind, p1, p2)` exists and looks like the
obvious answer. On FreeCAD 1.1 it returns `None` or raises
`DDH::makeDistDim - dim not found`, and on an unprojected view it access-violates.
Build the object directly.

### 11.2 `AutoCorrectRefs` rewrites your references

The preference `Mod/TechDraw/Dimensions/AutoCorrectRefs` defaults to **on**, and
it re-resolves `References2D` after you set them. Given a valid
`('Vertex51', 'Vertex52')` it stored `('Vertex52', 'Vertex54')` — an index past
the end of the list — and the dimension read 0.00 mm on the page with no error
anywhere.

Turn it off while attaching, and put it back:

```python
prm = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
was = prm.GetBool("AutoCorrectRefs")
prm.SetBool("AutoCorrectRefs", False)
try:
    ...                                  # create dimensions here
finally:
    prm.SetBool("AutoCorrectRefs", was)
```

### 11.3 Units are the reader's, not yours

`FormatSpec = "%.1w"` prints the value in the **user's** unit schema. The
session this guide was written in is set to `ImperialDecimal`, so a 1068.4 mm
spool dimensions as `42.1 in`. That is often what a drafter wants, and it is
never what you assumed. `getRawValue()` always returns millimetres — verify
against that, and name the active schema in your report:

```python
schema = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt("UserSchema")
FreeCAD.Units.listSchemas()[schema]      # -> 'ImperialDecimal'
```

### 11.4 Where dimensions go

Not on the isometric. TechDraw foreshortens it, so the numbers are wrong — which
is why the reference drawing dimensions the top view instead, despite the
isometric being the view a fabricator reads.

Stacking two parallel dimensions on the same side overlaps their text however
far apart you put the lines. Put the second one on the opposite side. Leave
extra clearance below a view for the caption (§8).

### 11.5 Dimension to work points, not to the metal

This is the rule that decides whether a spool drawing is any use, and an
automated drawing gets it wrong by default, because a bounding box is the
easiest thing in the model to reach for.

**A pipe drawing is set out from work points:** flange faces, and the
centreline intersections of fittings. A bounding-box dimension is the right
number measured between the wrong two things — it says where the steel ends,
when what a fitter sets out is where the centrelines cross. The overall height
of this spool is 1068.40 mm; the dimension a fitter needs, from the bottom
flange **face** to the **centreline** of the top flange, is 928.70 mm. Both are
correct measurements. Only one belongs on the drawing.

Quetzal gives you everything needed, because every component carries `Ports`
and `PortDirections`. Resolve each pipe end to the work point of whatever is
welded there:

| Welded on | Work point |
|---|---|
| Flange | its raised **face** — the datum, not the weld |
| Elbow | the **intersection of its two port axes** — the corner, not the tangent |
| Outlet | where the branch centreline meets the **run** centreline |
| nothing | the free end is its own work point |

```python
def _gports(obj):                       # ports in global coordinates
    return [(obj.Placement.multVec(p), obj.Placement.Rotation.multVec(d))
            for p, d in zip(obj.Ports, obj.PortDirections)]
```

A branch outlet is the awkward one: it is **not** port-connected to its run. It
sits on the outside diameter, while the run's own ports are at its ends. Match
it by `CarrierOD` and proximity to the axis, then project onto that axis.

### 11.5.1 A leg with no pipe in it needs no dimension

The corollary, and the reason to **iterate over pipes rather than over legs**.
Where two fittings are welded straight together, the distance between their
work points is fixed by the catalogue take-outs. The fitter cannot change it
and has no use for it; dimensioning it adds a number that can only confirm what
the fittings already decide. On this spool the elbow and the top flange are
welded directly, so the whole X direction is determined — and gets no dimension
at all.

Iterating over pipes gives that for free: no pipe in the leg, no dimension.

### 11.5.2 Let the view decide what it can show

A branch pointing along -Y is plainly visible in 3D, prominent in the
isometric, and **completely invisible in a front view looking along -Y** — it
projects onto the run behind it. So check each span against the view frame and
place it only where it reads:

```python
if abs(unit.dot(x_axis)) > 0.9:   return "DistanceX", (0.0, below)
if abs(unit.dot(y_axis)) > 0.9:   return "DistanceY", (left, 0.0)
return None                        # skew or edge-on: this view cannot show it
```

Then walk the views in a fixed order and skip what an earlier one already
measured. Together the rules produce three dimensions on this spool, and no
others:

```
OK  6" face to CL      DistanceY reads    928.70 mm  [Front view]   face -> CL of far flange
OK  Face to branch CL  DistanceY reads    395.30 mm  [Front view]   datum -> branch centreline
OK  1" run CL to end   DistanceY reads    332.58 mm  [Top view]     run CL -> end of branch
```

### 11.5.3 Give the BOM the sheet's units

A drawing that reads `24.00 in` against a BOM that says `609.6 mm` is a drawing
somebody will misread. Quantities follow the same unit schema the dimensions
do — ask it rather than hard-coding millimetres:

```python
_, factor, unit = FreeCAD.Units.Quantity(mm, "mm").getUserPreferred()
"%.2f %s" % (mm / factor, unit)          # 609.6 mm -> '24.00 in'
```

Nominal size is the exception, because it is a **name, not a measurement**. A
6" pipe is not 6 inches of anything. Do not convert it — select the convention:
`6"` on an imperial sheet, `DN150` on a metric one, never `152.4 mm`.

---

### 11.5.4 Anchor on the feature, and check by looking

Getting the work point right is only half of it. The work point fixes the
coordinate being *measured*; the anchor also decides where the extension line
starts, and an anchor left on the pipe centreline throws a line clear across
the view that touches nothing. Slide each anchor sideways — along the axis the
dimension does **not** measure — to the edge of the component it belongs to,
on the side the dimension line sits:

```python
def _anchor_to(point, comp, axis, side):
    bb = comp.Shape.BoundBox
    corners = [FreeCAD.Vector(x, y, z) for x in (bb.XMin, bb.XMax)
               for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)]
    vals = [c.dot(axis) for c in corners]
    target = min(vals) if side < 0 else max(vals)
    return point + axis * (target - point.dot(axis))
```

Project the **bounding box corners**, not `Shape.Vertexes`. A turned part like
a flange only has vertices where its surfaces seam, so the widest point of the
disc is not a vertex at all and the anchor lands short of the rim.

Note which component to attach to is not always the one that defines the point.
An elbow's work point lies on the centreline of whatever the elbow turns
**into**, so the extension line belongs on that far flange, not on the elbow.

Finally: this is the part of the drawing that numeric verification cannot
police. A dimension can report the right value, reference the right vertices,
and still be drawn between the wrong two features (§6.2). Render the view and
look at where the extension lines land:

```python
sc = sub.widget().findChild(QtGui.QGraphicsView).scene()   # scene = page mm x 10, Y down
img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32); img.fill(QtGui.QColor("white"))
pnt = QtGui.QPainter(img)
sc.render(pnt, QtCore.QRectF(0, 0, w, h),
          QtCore.QRectF(x0*10, -(y0+h_mm)*10, w_mm*10, h_mm*10))
```

Rendering the scene to a chosen page-mm rectangle beats screenshotting the
window: the mapping from page millimetres to pixels is exact, so you can
predict where a feature should appear and check that it does. Comparing a
dimension's `sceneBoundingRect()` against the page position you computed for
its intended anchors turns "does it look right" into arithmetic.

### 11.6 A blank page is usually a window, not a build

When the user says nothing is visible, check the *window* before you doubt the
build. A page can be complete and correct in the document — views positioned,
`getVisibleEdges()` in the hundreds, balloons and dimensions all present — and
still render as an empty template on screen.

**Opening a second window onto one page does not give you two views of it.**
The scene items belong to one window; every other window shows the template and
nothing else. So a macro that calls `page.ViewObject.doubleClicked()` on every
run quietly accumulates blank page windows, and the user is looking at one of
them. Deleting a page closes its own window, so this only bites when
`doubleClicked()` is called repeatedly on a page that is already open.

Diagnose it by comparing the document against the screen:

```python
[len(v.getVisibleEdges()) for v in views]    # hundreds -> the build is fine
```

If those numbers are healthy and the sheet is blank, close the page windows and
open exactly one.

**Never close page windows by title.** Every one of them is a bare `QMainWindow`
titled `Page`, with no reference back to its document, so a title match closes
the user's other drawings too — which is a much worse failure than the one you
were fixing. Remember the window you opened and close only that:

```python
before = set(mdi.subWindowList())
page.ViewObject.doubleClicked()
new = [s for s in mdi.subWindowList() if s not in before]
if new:
    _OUR_PAGE_WINDOWS[doc.Name] = new[-1]     # close this one, and only this one
page.requestPaint()
```

**Paint the page before setting `KeepUpdated = False`.** Whatever has not been
drawn by then stays undrawn, so a macro that switches updates off at the end
and never opened a window leaves a blank sheet behind.

### 11.7 Projected geometry does not survive a crash

Projections are cached, not stored as part of the model. After FreeCAD crashes
and the user recovers their file, the views can come back with **zero** edges,
and `KeepUpdated = False` means nothing ever rebuilds them. The page opens blank
and stays blank.

The repair is the same as the initial projection (§5.2) — `KeepUpdated = True`,
touch every view, recompute, wait, then set it back. It took 4.1 s on an
eleven-component spool. It changes no geometry, but it does mark the document
modified, so on somebody else's file say so and let them decide whether to save.
They only get that choice if the bridge's autosave is off (§2.3). Check it
before you touch the file, not after.
