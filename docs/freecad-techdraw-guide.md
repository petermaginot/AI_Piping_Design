# Drawing a spool with TechDraw over MCP

Directions for an AI agent that turns a finished piping model into a **drawing**:
views, a bill of material, balloons and dimensions on a TechDraw page, built in
the user's live FreeCAD session over the MCP server.

This is the sibling of [`freecad-quetzal-guide.md`](freecad-quetzal-guide.md) and
[`freecad-draft-guide.md`](freecad-draft-guide.md). The first is for building
piping: `pCmd` makers, `tablez/` lookups, port chains. The second is for 2D
Draft geometry. **Neither applies here.** By the time you reach this guide the
geometry already exists and is correct; nothing you do should change it.

The rules below are the non-obvious ones: the places where the page builds
without an exception, looks plausible on screen, and is still wrong — a
dimension that reads 0.00, a BOM whose size column has silently become
millimetres, a balloon pointing at nothing — or is so slow it cannot be used.

Everything here was measured against a live FreeCAD 1.1 session. The worked
example is [`examples/TechDraw_example/make_techdraw_page.py`](../examples/TechDraw_example/make_techdraw_page.py).

---

## 1. Golden rules (read first)

1. **The `App::Part` container is the drawing, and it is the performance
   control.** Welded components go in; gaskets, bolting and valves stay out.
   This one decision is worth 12x on redraw time (§3, §13).
2. **A view will not project itself.** Create it, `touch()` it, recompute, then
   *wait* for the GUI event loop. Until then it has no geometry, and anything
   that references it fails — sometimes by taking FreeCAD down (§5.2).
3. **`page.addView()` recentres the view.** Set `X`/`Y` *after* adding, never
   before. The same applies to balloons, dimensions and the spreadsheet (§5.3).
4. **Balloon coordinates are unscaled view coordinates, Y up, origin at
   `TechDraw.findCentroid`** — not the bounding-box centre. Get this wrong and
   every balloon is off by a constant (§6).
5. **Do not use `makeCosmeticVertex3d` to anchor a dimension.** It stores the
   point Y-down while the dimension renderer reads it Y-up, so every anchor is
   mirrored about the view centre — and because the *separation* survives, the
   dimension still reads the right number against the wrong two features. Place
   the vertex with `makeCosmeticVertex` and your own Y-up projection (§6.2).
6. **Never dimension to a projected `VertexN`.** Those indices re-number when
   the model or the view direction changes. Place your own cosmetic vertex and
   dimension between those (§11).
7. **Turn off `AutoCorrectRefs` while attaching a dimension.** It silently
   rewrites your references into ones that do not exist, and the dimension then
   reads 0.00 mm without erroring (§11.2).
8. **`Spreadsheet.set()` parses what you give it.** `6"` becomes the quantity
   six inches and prints as `152.4 mm`. Force text with a leading apostrophe
   (§9.2).
9. **`PRating` is not a spec field.** It is whatever table the maker happened to
   use. Derive the BOM from geometry and emit the rest as a placeholder (§9.3).
10. **A `%w` format spec prints in the *user's* unit schema**, so the same file
    reads millimetres on one machine and inches on the next. State which one
    you got (§11.3).
11. **Do not dimension the isometric view.** TechDraw foreshortens it and the
    numbers are wrong (§11.4).
12. **Dimension to work points — flange faces and fitting centreline
    intersections — never to the bounding box.** And skip any leg with no pipe
    in it: the take-outs already fix it. Then ask each view what it can
    actually show, because a branch parallel to a view's `Direction` is
    invisible in it (§11.5).
13. **The BOM prints in the sheet's unit schema**, the same one the dimensions
    use. Nominal size is a name, not a measurement — select it, never convert
    it (§11.5.3, §9).
14. **Derive container membership from `PType`, not from the existing
    container.** A component the user added since the last run will not be in
    it (§3).
15. **Open exactly one window on the page, and paint it before switching
    updates off.** A second window onto the same page renders blank, and a
    blank sheet is nearly always a window problem, not a build problem (§11.6).
16. **Verify numerically before handing over.** Every dimension read back
    against the model, every balloon proved on-sheet, every mark accounted for
    (§14).

---

## 2. Session preamble

Confirm the live session with `check_freecad_connection` before anything else.
This is GUI work: TechDraw's view providers only exist in a real GUI, so none of
it runs under `freecadcmd`.

### 2.1 Choose the target document deliberately

`FreeCAD.listDocuments()` is keyed by internal **Name**, which is not the
**Label**. A document saved as `Simple_spool.FCStd` is very often still open as
`Unnamed`, because saving does not rename it. Match either:

```python
def find_doc(name):
    for d in FreeCAD.listDocuments().values():
        if name in (d.Name, d.Label):
            return d
    raise RuntimeError("No open document named or labelled %r" % name)
```

### 2.2 Set the active document

Several TechDraw helpers act on `FreeCAD.ActiveDocument`, not on the object you
hand them. If the user has two models open, you will silently build into the
wrong one. `FreeCAD.setActiveDocument(doc.Name)` first, every time.

### 2.3 The user's own files are reference, not a work surface

A model the user opened from their own drive is not yours to rebuild, recompute
or save. Read it to learn the conventions; build on a document in the repo.
Recomputing someone's page marks their file modified, and a TechDraw teardown
can crash FreeCAD outright — which it did, once, while this guide was written.

---

## 3. The container is the drawing

Build one `App::Part` and put the **welded** components in it — pipe, elbows,
flanges, outlets, tees, reducers, caps. That is the weld spool: the thing the
fabricator makes. Gaskets, bolt sets and valves are assembly material. They
belong in the BOM (§9) and nowhere near the container.

```python
WELDED_PTYPES = ("Pipe", "Elbow", "Flange", "Outlet", "Tee", "Reduct", "Cap",
                 "Coupling", "Union")
part = doc.addObject("App::Part", "Part")
part.Group = [o for o in doc.Objects
              if getattr(o, "PType", None) in WELDED_PTYPES]
```

This is correct drafting practice, and it is also the single biggest lever on
whether the page is usable at all. §13 has the numbers.

**Rebuild the membership from `PType` every run; never trust the container that
is already there.** When the user adds a drain branch between runs, the new pipe
is not in the old container, and a macro that reuses it draws a spool missing a
component — with the BOM and the balloons agreeing with each other and with the
drawing, so nothing looks wrong. Deriving membership afresh picked up an added
`Tube001` automatically.

A consequence worth stating on the page: **assembly material is in the BOM but
cannot be ballooned**, because it is not drawn. That is correct, not a bug — but
a mark with no balloon is also exactly what a welded part wrongly left out of
the container looks like. Report the two cases differently (§14).

Note the container has **no `Shape` of its own**. Anything that needs the
geometry has to walk `part.Group`:

```python
shape = Part.makeCompound([o.Shape for o in part.Group])
```

---

## 4. Page and template

```python
page = doc.addObject("TechDraw::DrawPage", "Page")
tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
tmpl.Template = os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                             "Templates", "ASME", "ANSIB_Landscape.svg")
page.Template = tmpl
```

Derive the template path from `getResourceDir()`. Hard-coding
`C:/Program Files/FreeCAD 1.1/...` works on exactly one machine.

`Template.Width` and `Template.Height` are the sheet size in mm — ANSI B
Landscape is 431.8 x 279.4. Use them to prove your annotations land on the
sheet (§14), not a remembered constant.

The title block is `tmpl.EditableTexts`, a plain dict. Assign a **new** dict;
mutating the existing one in place does not stick:

```python
tmpl.EditableTexts = dict(tmpl.EditableTexts,
                          **{"DrawingTitle1": "SIMPLE SPOOL", "Scale": "1:12"})
```

The ASME template has both a `Scale` key (the value) and a `scale` key (the
literal word "Scale" printed as a label). Set `Scale`.

---

## 5. Views

### 5.1 Standalone items, not a projection group

Use `TechDraw::DrawProjGroupItem` with `Type = 'Front'` and a hand-set
`Direction`, one object per view. Do **not** wrap them in a `DrawProjGroup`: a
group forces its members to share a scale and a projection convention, and a
spool drawing usually wants an isometric alongside two orthographic views with
their own hidden-line settings.

`Direction` points **from the model toward the viewer**. `XDirection` is
page-right. Page-up is then `Direction x XDirection`.

| View | `Direction` | `XDirection` | shows |
|---|---|---|---|
| Isometric | `(0.57735, 0.57735, 0.57735)` | `(-0.70711, 0.70711, 0)` | everything, foreshortened |
| Front | `(0, -1, 0)` | `(1, 0, 0)` | the X-Z plane |
| Top | `(0, 0, 1)` | `(1, 0, 0)` | the X-Y footprint |

Pick the orthographic directions to suit the spool, not by habit. A spool that
runs vertically projects to a *line* in the top view — dimension the view that
actually shows the shape.

### 5.2 A view does not project itself

This is the trap that costs the most time. A newly created view has no
geometry: `getVisibleEdges()` returns 0. Touching it and recomputing is not
enough either — the view provider attaches on the **next turn of the GUI event
loop**, so inside the call that created it the view still reads as empty.

Referencing an unprojected view does not raise. `makeDistanceDim3d` on one
throws `RuntimeError: FreeCAD exception thrown (Access violation)`, and a
teardown at the wrong moment takes the whole application down.

So block until the geometry is real:

```python
page.KeepUpdated = True
for v in views:
    v.touch()
doc.recompute()
for _ in range(10):
    if all(len(v.getVisibleEdges()) for v in views):
        break
    FreeCADGui.updateGui()          # let the view providers attach
    doc.recompute()
if any(not len(v.getVisibleEdges()) for v in views):
    raise RuntimeError("views never projected -- refusing to annotate them")
```

Do every piece of work that reads projected geometry immediately after this,
while the views are fresh.

### 5.3 `addView` moves what you just positioned

`page.addView(view)` drops the view at the centre of the sheet, discarding any
`X`/`Y` set beforehand. Position afterwards:

```python
page.addView(view)
view.X, view.Y = 112.0, 196.0       # AFTER, always
```

The same is true of `DrawViewBalloon`, `DrawViewDimension` and
`DrawViewSpreadsheet`. If your whole page ends up stacked at
`(215.9, 139.7)` on ANSI B, this is why.

### 5.4 Scale

`ScaleType = 'Custom'`, then `Scale` as a fraction. Prefer one scale for the
whole drawing so the title block can state it once, and snap to a ratio a
drafter would recognise rather than whatever exactly fits:

```python
NICE_SCALES = [1, 1/2, 1/2.5, 1/4, 1/5, 1/6, 1/8, 1/10, 1/12, 1/15, 1/20, ...]
```

Fit against the *projected* extent in each direction, not the bounding box
diagonal, or a long flat spool comes out needlessly small.

---

### 5.5 Re-orbiting a view when the user asks

"Turn the isometric round so I can see the drain" is a routine request, and it
is a *parameter*, not an edit. Keep a per-view spin in one place and let the
build honour it, so the user can say a number instead of asking you to rewrite
the view table:

```python
VIEW_SPIN = {"iso": -90.0}            # degrees about model Z
SPIN_AXIS = (0.0, 0.0, 1.0)
```

**Rotate `Direction` and `XDirection` together.** Turning only `Direction`
rolls the drawing rather than orbiting it — the model spins on the sheet, and
page-up stops meaning what §6 says it means, which silently breaks every
balloon and dimension placed afterwards.

```python
rot = FreeCAD.Rotation(FreeCAD.Vector(*axis), spin_deg)
d, x = rot.multVec(d), rot.multVec(x)
```

**The sign is the part that gets guessed wrong.** Orbiting about Z cannot
change how broadside a horizontal branch is — all four quarter turns leave it
equally foreshortened. What changes is which side of the run the branch lands
on. Test it rather than trying it:

```python
branch_axis.dot(view.Direction) > 0      # branch comes toward the viewer
```

Positive means the branch reads clear in front of the run; negative means it
is hidden behind it. On this spool the drain runs along -Y, so `-90` brings it
to the front and `+90` achieves nothing:

```
spin   +0  Direction=( 0.577, 0.577, 0.577)  dot=-0.577  hidden behind the run
spin  +90  Direction=(-0.577, 0.577, 0.577)  dot=-0.577  hidden behind the run
spin  -90  Direction=( 0.577,-0.577, 0.577)  dot=+0.577  in front
```

Two things must follow the spin or the page comes out wrong. **Fit the scale
against the spun axes** — an orbited view has a different outline, and fitting
the unspun one picks the wrong scale. And everything positioned in the view
frame — balloons, dimension anchors, cosmetic vertices — has to be *recomputed*
rather than carried over, since the frame itself has moved. Deriving them from
the view frame at build time, as §6 and §10 do, gets that for free: change the
spin, rebuild, and the balloons redistribute around the new outline by
themselves.

---

## 6. The view coordinate system

Everything placed on a view — balloons, dimension points, cosmetic vertices —
is positioned in the view's own 2D frame. Get this frame right and the rest of
the drawing follows.

```python
def view_frame(view):
    d = FreeCAD.Vector(view.Direction); d.normalize()
    x = FreeCAD.Vector(view.XDirection)
    x = x - d * x.dot(d)            # XDirection need not be perpendicular
    x.normalize()
    return d, x, d.cross(x)         # page-up = Direction x XDirection
```

The origin is **TechDraw's own centroid of the projected shape**, which is not
the bounding-box centre:

```python
centre = TechDraw.findCentroid(shape, view.Direction)
```

On a real 10" spool those two points are 160 mm apart. Using the bounding-box
centre offsets every balloon on the sheet by that distance — consistently, so
it looks like a placement bug rather than a frame bug.

```python
def view_uv(view, p3, centre):
    _, x, y = view_frame(view)
    r = FreeCAD.Vector(p3) - centre
    return r.dot(x), r.dot(y)       # unscaled view units; x view.Scale for page mm
```

### 6.1 Which coordinates are scaled

| Property | Frame | Scaled? |
|---|---|---|
| `DrawView.X` / `.Y` | page, from bottom-left | page mm |
| `Balloon.X/.Y`, `.OriginX/.OriginY` | view, Y **up** | unscaled — multiply by `view.Scale` |
| `CosmeticVertex.Point` | view, Y **down** | unscaled |
| `Dimension.X/.Y` | page, relative to its view | page mm (`ScaleType` is `Page`) |

So a balloon's position on the sheet is
`view.X + balloon.X * view.Scale`. That expression is what §14 checks.

### 6.2 Cosmetic vertices have the opposite Y sign — and TechDraw disagrees with itself about it

`view_uv` and `Balloon.OriginY` agree: page-up is positive. `CosmeticVertex.Point`
does **not** — it is stored in Qt scene coordinates, where Y runs down. The same
3D point comes back as `v = -534.20` from `view_uv` and `+534.20` as a cosmetic
vertex.

`makeCosmeticVertex3d(p3)` looks like the answer: hand it a model-space point
and let TechDraw do the conversion. **Do not use it to anchor a dimension.** It
writes `Point.y` in the Y-down frame, but the dimension renderer reads that same
value as Y-up, so each anchor is reflected about the view centre:

```
intended anchor  z = -88.90   ->  drawn at z = 979.50
intended anchor  z = 839.80   ->  drawn at z =  50.80     (mirror about z = 445.30)
```

The reflection preserves the *separation*, so the dimension still reads
928.70 mm. It is the right number, measured between the wrong two features,
with nothing anywhere reporting an error — `getRawValue()`, `References2D` and
`getArrowPositions()` all look correct, because they are all expressed in the
frame that is itself mirrored. Only the drawn geometry is wrong, so **this one
is invisible to every numeric check in §14 and can only be caught by looking**
(§11.5.4).

Project the point yourself and place the vertex in view coordinates:

```python
centre = view_centre(view)
u, w = view_uv(view, p3, centre)            # Y up, as balloons use
view.makeCosmeticVertex(FreeCAD.Vector(u, w, 0.0))
```

---

## 7. Transparency

To let a branch assembly read through the run in front of it:

```python
tube.ViewObject.Transparency = 50
```

Be clear about what this does. It is a **3D** view property. It changes what the
user sees in the 3D window, which is where they judge the model — and it does
**not** change the projection. TechDraw's hidden-line removal is unaffected, so
the drawing is identical whether the run is transparent or not. If you need the
hidden geometry to show on the *page*, that is `view.HardHidden = True`, which
is a different setting with a real cost (§13).

---

## 8. Captions

A view carries a `Caption` property, and there is also a separate
`TechDraw::DrawViewAnnotation` object. The hand-built reference drawing uses
both, inconsistently. Pick `Caption` — it moves with its view and needs no
second object — and use `DrawViewAnnotation` only for text that belongs to the
sheet rather than to a view.

Captions print **below the view centre**. Anything else you place there will
collide with them: the bottom dimension needs extra clearance, and a balloon
ring should skip the bottom sector (§10).

---

## 9. The bill of material

### 9.1 Structure

A `Spreadsheet::Sheet` holds the data; a `TechDraw::DrawViewSpreadsheet` puts a
cell range on the page.

```python
view = doc.addObject("TechDraw::DrawViewSpreadsheet", "Sheet")
view.Source = sheet
view.CellStart, view.CellEnd = "A1", "D12"
page.addView(view)
view.X, view.Y = 330.0, 215.0       # after addView (§5.3)
```

Group welded marks first, then a break row reading `Assembly materials`, then
the bolting and valves. Quantify pipe as a **summed length**, everything else as
a count — two pipes of different length are still one mark on a cut list.

### 9.2 `set()` parses what you give it

This is the quiet one. `Spreadsheet.set()` evaluates its argument:

| You write | It stores | It displays |
|---|---|---|
| `6"` | `=6 "` | `152.4 mm` |
| `609.6 mm` | `=609.6 mm` | `609.6 mm` |
| `'6"` | `'6"` | `6"` |

So a BOM whose Size column should read `6"`, `1"`, `10"` comes out in
millimetres, and nothing warns you. A leading apostrophe forces text:

```python
def _text(sheet, cell, value):
    sheet.set(cell, "'" + str(value))
```

Use it for every BOM cell, including the headers.

### 9.3 Derive from geometry; `PRating` is a hint

`PRating` is whatever table the maker was pointed at, not a spec field. In the
reference model a 10" A106 pipe carries `PRating = 'ConduitEMT-LIGHT'` and a
300# flange carries `'SCH-STD'`. Key the BOM on `PType`, `PSize` and real
dimensions (`OD`, `thk`, `BendRadius`, `FClass`, `FlangeType`, `EndType`).

Some things are genuinely not in the model — material grades, gasket type, bolt
lengths. Do not invent them. Emit a placeholder the user can see and overwrite:

```
PIPE, SCH-40/SCH-40S/SCH-STD, <A106 GR B SMLS>
FLANGE, RF WN 150lb, <BORE>, <A105>
```

Two further traps worth knowing:

- **A schedule is not uniquely determined by OD and thickness.** At DN150,
  `SCH-40`, `SCH-40S` and `SCH-STD` are the same pipe. Scan `tablez/Pipe_*.csv`
  and report every match rather than silently picking the first.
- **Long-radius means `R = 1.5 x nominal bore`, not `1.5 x OD`.** A DN150 LR
  elbow has `BendRadius = 228.6 = 1.5 x 6"`, but `228.6 / OD 168.275 = 1.36`,
  so an OD-based test calls every LR elbow short-radius. Quetzal has no DN-to-NPS
  table; carry your own.

---

## 10. Balloons

```python
b = doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
b.SourceView = view
b.Text = mark                     # the BOM mark number, as a string
b.BubbleShape = "Circular"
b.EndType = "Filled arrow"
page.addView(b)
b.OriginX, b.OriginY = u, v       # arrow tip, on the part (§6)
b.X, b.Y = bubble_u, bubble_v     # bubble, clear of the geometry
```

Set `page.NextBalloonIndex` past the last one you made, or the GUI's own balloon
tool will reuse numbers.

For auto-placement: put the arrow at the component's projected centroid, and the
bubble out on a ring at the same bearing. Make the ring **elliptical**
(`half_width + gap`, `half_height + gap`) — a circular ring flings the bubbles of
a tall thin spool far out to the sides.

Two refinements earn their place. Skip the bottom sector, where the caption
prints (§8). And enforce a minimum angular separation, or two components at the
same bearing stack in exactly the same spot:

```python
placed.sort(key=lambda p: p[0])
for i in range(1, len(placed)):
    if placed[i][0] - placed[i-1][0] < MIN_SEP:
        placed[i][0] = placed[i-1][0] + MIN_SEP
```

That is spacing, not collision avoidance. Bubbles that merely crowd are for the
user to drag; bubbles drawn on top of each other are a defect.

### 10.1 A leader that ends on the centreline points at everything

The centroid is the obvious arrow target and it is wrong for anything welded
into a run. A component's centroid sits **on the axis**, and so does every
other component on that axis — so a flange's leader reads just as well as a
call-out for the pipe welded to it. The balloon is not wrong, it is
*ambiguous*, which on a fabrication drawing is the same thing.

Land the leader on the **silhouette** instead: offset from the axis by the
component's radius there, along `axis × view.Direction`. That vector is
perpendicular to both the part's axis and the line of sight, so the point lands
on the outline rather than somewhere inside it. Of the two signs, take the one
further from the view centre, so the leader reaches in from outside instead of
crossing the spool.

For a weld-neck flange, *where* on the silhouette matters too. Its hub runs out
to exactly the pipe OD at the weld end — 84.20 mm against the pipe's 84.14 mm
on this spool — so a leader landing there is no less ambiguous than one on the
centreline. The flange is only unmistakably itself just behind the disc, where
the hub is still far wider than the pipe. Find that station by walking out from
the raised face until the section drops below the disc OD:

```python
for i in range(1, steps + 1):
    pt = face + axis * (length * i / steps)
    r = _radius_at(flange.Shape, pt, axis)         # Shape.slice() at that station
    if r < disc_radius * 0.95:
        break                                       # first station past the disc
```

On the DN150 150# flange here that lands 27 mm from the raised face at a radius
of 104 mm, against a pipe radius of 84 mm — comfortably clear of both the disc
and the pipe, and on the side away from the face as a fitter would expect.

Measure the radius from the solid rather than the flange table. `Shape.slice()`
reports what is actually there, including the hub fillet, and it works the same
way for a component whose properties you have not special-cased.

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

---

## 12. Keeping the page off

`page.KeepUpdated = False` stops the page redrawing on every change. Turn it on
while you build (you need the views to project, §5.2) and leave it **off** when
you hand over, so the user's next edit to the model does not stall the GUI.

It is a page property, independent of the global
`Mod/TechDraw/General/KeepPagesUpToDate`.

---

## 13. Why the page is slow

The usual guess is that hidden-line removal cannot cope with the geometry. It
is not that. For an 11-component spool, the whole geometry pipeline is
sub-second:

```
TechDraw.projectEx(compound, direction)   0.18 s     # HLR
TechDraw.edgeWalker(visible_edges)        0.14 s     # face finding
```

What actually costs is **how many objects are in the container**, because the
scene layer builds a graphics item per edge, per vertex and per found face, for
every view. Measured end to end on the same spool — time from `touch()` until
every view has really projected:

| Container holds | Views | Solids | Faces | Time to drawn |
|---|---|---|---|---|
| Welded only | 1 | 11 | 124 | **1.65 s** |
| + gaskets, bolting, valves | 1 | 87 | 1786 | **36.48 s** |
| Welded only | 3 | 11 | 124 | **4.79 s** |
| + gaskets, bolting, valves | 3 | 87 | 1786 | **59.40 s** |

Bolting is what does it. A single `Bolts_Nuts` object is **16 solids, 336 faces,
720 edges** — 2.7x the entire welded spool. Two bolt sets and a pair of valves
turn a five-second page into a minute.

The geometry pipeline only grew from 0.32 s to 2.84 s across those two cases. The
other 56 seconds are scene construction. That is why raising the HLR settings
does little and why trimming the container does a lot.

Levers, in the order worth trying:

1. **Take bolting, gaskets and valves out of the container.** This is the whole
   game, and it is also what a weld spool drawing should show.
2. **`page.KeepUpdated = False`** while working (§12).
3. **`view.HardHidden = False`** unless the view genuinely needs hidden lines —
   it roughly doubles the items in the scene.
4. **`view.SmoothVisible = False`** drops tangent edges, which are numerous on
   pipe and elbows.
5. **`view.CoarseView = True`** switches to polygonal HLR. Fast and ugly; useful
   while laying a page out.

If a page is still slow after that, count the solids before blaming TechDraw.

---

## 14. Verify numerically

A page that built without an exception has proved nothing. Query the finished
document and print numbers you can quote.

- **Container membership.** Print what is in it and what was excluded. No
  `Gasket`, `Bolts_Nuts` or `Valve` in the container.
- **Every view projected.** `len(view.getVisibleEdges()) > 0` for each. Zero
  means the page is blank however good the object tree looks.
- **Every dimension against the model.** `dim.getRawValue()` is millimetres;
  compare it to the same distance computed from the geometry. This is the check
  that catches the 0.00 mm failure, and it is not optional:

```
OK  Overall length     DistanceX reads    458.80 mm  model    458.80 mm
OK  Overall height     DistanceY reads   1068.40 mm  model   1068.40 mm
OK  Face to branch CL  DistanceY reads    395.30 mm  model    395.30 mm
```

- **Every balloon on the sheet.** `view.X + b.X * view.Scale` inside
  `(0, Template.Width)`, likewise for Y. A balloon at page coordinate 572 on a
  431.8 mm sheet is off the paper.
- **Every mark accounted for**, and every mark *without* a balloon explained.
  Assembly material legitimately has none; a welded component with none was left
  out of the container, which is a real defect that otherwise looks identical:

```
mark 6   no balloon (assembly material, not drawn)
mark 6   no balloon (NOT DRAWN - welded part missing from the container!)
```
- **The unit schema**, named explicitly (§11.3).

Then look at it. Export the page or grab the view:

```python
TechDrawGui.exportPageAsSvg(page, path)
# or, to see what the user sees:
mdi = FreeCADGui.getMainWindow().findChild(QtGui.QMdiArea)
mdi.activeSubWindow().widget().grab().save(png_path)
```

Clear the selection first, or you will be looking at highlight colours and
vertex dots and think something is wrong. Looking at the page is how you catch
overlapping text, which no numeric check will tell you about.

---

## 15. Where the output goes

Per [`AGENTS.md`](../AGENTS.md):

- Write a `.py` only if asked, into `examples/<name>/`, and save the `.FCStd`
  beside it.
- Never write into the user's Quetzal installation, and never save a document
  that came from outside the repo.
- Photographs, client drawings and site tags stay out of the repo — `private/`
  is gitignored for that.

---

## 16. The loop, end to end

1. Confirm the session; set the active document (§2).
2. Tear down the previous drawing — annotations, then views, then template, then
   page, then the spreadsheet, then the container. Empty the container before
   removing it, or it takes the geometry with it.
3. Collect the welded components; build the `App::Part` (§3).
4. Create the page and template; fit one scale to all views (§4, §5.4).
5. Add the views, positioning each **after** `addView` (§5.3).
6. Project them, and block until they really are projected (§5.2).
7. Dimensions first, while the views are fresh. For each dimensioned view in
   turn, plan what that view can actually show and skip what an earlier one
   already measured (§11.5); then cosmetic vertices, one recompute, indices,
   `AutoCorrectRefs` off, attach (§11).
8. Build the BOM, force every cell to text, place the sheet (§9).
9. Balloons on the ring (§10).
10. Transparency and title block (§7, §4).
11. Open one window on the page and paint it, **then** `KeepUpdated = False`
    (§11.6, §12).
12. Run the numeric checks in §14 and print the report.
13. Look at the page. Save.

Before an existing drawing is handed back after edits, re-run 6, 11 and 12 in
full. A dimension that was correct before the model moved is exactly the failure
this guide is about.
