# Views (§5–§8)

Part of the `techdraw-drawing` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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
