# Driving the Draft workbench over MCP

Directions for an AI agent that builds **flat 2D artwork** — seals, stamps,
logos, title-block furniture, plate profiles — with FreeCAD's **Draft**
workbench, by driving the user's live session over the MCP server
([blwfish/freecad-mcp](https://github.com/blwfish/freecad-mcp)).

This is the sibling of [`freecad-quetzal-guide.md`](freecad-quetzal-guide.md).
That one is for piping: `pCmd` makers, `tablez/` lookups, port chains. **None of
that applies here.** Draft work is plain geometry — circles, rectangles, arrays
and outlined text — and its traps are entirely different ones. Read this before
you build 2D artwork; read the Quetzal guide before you build pipe.

The rules below are the non-obvious ones: the places where a build runs clean,
looks right in the GUI, and still ships a broken deliverable.

---

## 1. Golden rules (read first)

1. **You build in the user's live GUI session, over MCP.** Confirm it first with
   `check_freecad_connection`. Draft itself works headless, but you need the GUI
   for the view captures in §9, and the user needs to see the result.
2. **Build in a new, dedicated document.** Never add objects to whatever the
   user already has open. Create it by name, and close and recreate it on each
   iteration (§3).
3. **Drive a file, not the console.** Write a `.py`, then `import` +
   `importlib.reload` it over MCP. Never paste a growing build script into
   `execute_python` — see §3 for why this is the single highest-leverage rule
   in this document.
4. **Every Draft maker that can make a face, does.** `make_circle` and
   `make_rectangle` default to `MakeFace = True`. A circle you meant as an
   outline renders as a filled black disc that hides everything inside it
   (§4.1).
5. **A ShapeString is one object per glyph, and a space is not a glyph.**
   `Draft.make_shapestring(String=" ")` returns an object with no faces and a
   meaningless `BoundBox`. Guard for it, delete it, and advance by a nominal
   width (§5).
6. **`doc.recompute()` before you read any `Shape`.** A freshly made ShapeString
   has no usable `Shape.BoundBox` until the document recomputes. Glyph metrics
   drive all text layout, so this is not optional.
7. **Bake Draft arrays to `Part::Feature` before exporting.** A Draft array's
   view provider makes the SVG exporter emit `fill:url(#shape color)` — a
   gradient it never defines — so every element of the array exports unfilled
   (§7).
8. **Upright text grows outward from its baseline; inverted text grows inward.**
   Two arcs are only on the same ring if their baseline radii differ by the cap
   height. Get this wrong and the bottom legend silently sits a cap-height too
   far in — it looks *almost* right, which is why it survives review (§6.2).
9. **A clean build proves nothing.** Verify numerically out of the built
   document — overall size, radial clearances, element counts, angular spans
   (§8). Then look at it (§9). Then, if you are exporting, verify the
   *exported file* by rendering it (§10) — not by re-screenshotting FreeCAD,
   which tests the wrong thing. A reconciling element count is not proof
   either: it says nothing about what is *inside* each path (§10.5).
10. **Geometry you only used to think with should not be in the output.**
    Construction radii belong in constants. An unfilled circle left in the
    document exports as a visible stroked ring in every SVG reader, even
    though it looks like a harmless guideline in the GUI (§10.4).
11. **A hole is not a hole until the exporter agrees.** `importSVG` writes
    only the outer boundary of a Draft object's face, so an annulus or an
    outlined star exports as a solid blob while the viewport looks perfect
    throughout. Build holed shapes as polygon faces joined by a real boolean
    and wrapped in a `Part::Feature` (§10.3).
12. **Measure the reference, do not read it.** Fit a circle for the centre,
    then ask which *angles* carry ink rather than which radii. Twenty lines of
    measurement replace a dozen rounds of nudging (§9.3).

---

## 2. Session preamble

```python
import FreeCAD, FreeCADGui, Draft
print(FreeCAD.Version()[:3], "GUI:", FreeCAD.GuiUp)
print("workbench:", FreeCADGui.activeWorkbench().name())
print("open documents:", {n: d.FileName for n, d in FreeCAD.listDocuments().items()})
print("bridge autosave:", FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/AICopilot"
).GetBool("AutoSaveBeforeRiskyOp", True))
```

**The MCP bridge saves the active document before every `execute_python`
call**, if the document has a file path. The AICopilot preference
`AutoSaveBeforeRiskyOp` controls this, and it defaults to on. Your own freshly
created build document has no path, so it is safe until `save()` (§11). A user's
file that happens to be active is not. If autosave is on and any of the user's
saved files is open, **stop and tell them**. Offer to switch it off
(`.SetBool("AutoSaveBeforeRiskyOp", False)`), do it only if they agree, and
never activate their document yourself.

`FreeCAD.listDocuments()` returns a `dict` keyed by document name. Iterating it
yields **strings**, not documents — `[d.Name for d in FreeCAD.listDocuments()]`
raises `'str' object has no attribute 'Name'`. Use `.keys()` and mean it.

Print the open documents every time. You are about to create and destroy a
document repeatedly, and you need to know which names are the user's.

Draft does not need to be the active workbench for `Draft.make_*` to work, but
activating it gives the user the toolbars they expect:

```python
FreeCADGui.activateWorkbench("DraftWorkbench")
```

### 2.1 Fonts

`Draft.make_shapestring` needs an explicit path to a `.ttf`. There is no
sensible default — discover what is installed rather than guessing:

```python
import os
print([f for f in os.listdir(r"C:\Windows\Fonts")
       if f.lower().startswith(("arial", "times", "cour"))])
```

Condensed bold faces (`ARIALNB.TTF`) suit ring lettering, where you are fitting
a long legend into a fixed arc. Verify the specific glyphs you need actually
render before you design around them — a missing glyph comes back as an object
with zero faces, exactly like a space:

```python
for ch in ["N", "\u00ba", "&"]:
    o = Draft.make_shapestring(String=ch, FontFile=FONT, Size=2.0)
    doc.recompute()
    print(repr(ch), len(o.Shape.Faces))       # 0 means the font has no glyph
```

---

## 3. The build-script loop

**This is the core workflow.** Write the whole build to a `.py` file on disk,
then have the live session import and re-run it. Do not accumulate a build
script inside `execute_python` calls.

```python
import sys, importlib, FreeCAD
p = r"C:\...\<project dir>"
if p not in sys.path:
    sys.path.insert(0, p)

if "MyDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("MyDoc")

import build_thing
importlib.reload(build_thing)          # picks up every edit you just made
doc, grp = build_thing.build()
```

Why this and not the console:

- **2D artwork is iterative.** You will adjust a radius, look, adjust it again.
  A dozen rounds is normal. Each round is one `Edit` to the file plus this
  seven-line call — the build code itself is never retransmitted.
- **Every iteration starts from nothing.** Closing and recreating the document
  means iteration *n* cannot inherit a stray object from iteration *n−1*. A
  half-updated document that still contains the thing you thought you deleted
  is the classic way to spend an hour chasing a bug that does not exist.
- **The file is the deliverable.** When the user asks for a macro, it already
  exists and has been run in its final form. Nothing needs transcribing.
- **`importlib.reload` is what makes it cheap.** Without it Python serves the
  cached module and your edits appear to do nothing — which reads exactly like
  a geometry bug.

Structure the file as constants → helpers → `build()` → `style()` → `save()`,
with `build()` returning `(doc, group)`. Put every dimension in the constants
block, so tuning is an `Edit` to one number rather than a hunt through logic.

Group everything the build makes:

```python
grp = doc.addObject("App::DocumentObjectGroup", "Seal")
for p in parts:
    grp.addObject(p)
```

The group is what you measure in §8 and what you hand to the exporter in §10.
Collect objects into a `parts` list as you create them rather than scraping
`doc.Objects` afterwards — scraping picks up construction leftovers.

---

## 4. Draft makers and their traps

### 4.1 `MakeFace` is on by default

```python
c = Draft.make_circle(R)
c.MakeFace = False          # otherwise it is a filled black disc
```

This applies to `make_circle`, `make_rectangle` and `make_wire`. The symptom is
unmistakable once you have seen it — your first render is a black blob with
everything hidden underneath — but only if you actually look. Decide per object
whether it is an outline or a filled shape, and set it explicitly both ways
rather than relying on the default.

Filled shapes are usually what you want for artwork that will be printed or
exported: a filled thin rectangle carries a plotted line weight that survives
scaling, whereas a stroked wire depends on a `LineWidth` the exporter may
mistranslate (§10.2).

### 4.2 Rectangles are corner-anchored

`Draft.make_rectangle(w, h)` builds from the origin into +X/+Y. To centre one
on a point you place its corner:

```python
r = Draft.make_rectangle(2 * half, THICK)
r.Placement = FreeCAD.Placement(FreeCAD.Vector(-half, y - THICK / 2.0, 0),
                                FreeCAD.Rotation())
r.MakeFace = True
```

### 4.3 Circles are centre-anchored

`Draft.make_circle(r)` centres on the origin; move it with `Placement.Base`.
Small filled circles are the cleanest way to build dots and bullets.

---

## 5. Text: ShapeString

`Draft.make_shapestring` is the only way to get text as *geometry* (rather than
an annotation that will not export). One call per string is fine for a straight
line of text you do not need to measure. **One call per glyph** is required as
soon as you need to place characters individually.

```python
def _shapestring(doc, ch, size, font):
    """One glyph at the origin.  Returns (obj, advance_width)."""
    obj = Draft.make_shapestring(String=ch, FontFile=font, Size=size, Tracking=0)
    doc.recompute()                                   # Golden Rule 6
    shape = getattr(obj, "Shape", None)
    if shape is None or not shape.Faces:              # space, or missing glyph
        doc.removeObject(obj.Name)
        return None, 0.34 * size                      # nominal space advance
    return obj, shape.BoundBox.XLength
```

Take the font as a **parameter**, not a module global. A seal typically wants
three faces at once — a heavier one for the outer legend, a lighter one for a
smaller legend, and a condensed one for a centre block with a long line in it.
Discovering that after you have baked `FONT` into every helper is a refactor
you can skip by writing the argument now.

Three things are load-bearing here:

- **The recompute.** Without it `BoundBox` is garbage and every downstream
  layout number is wrong.
- **The empty-shape guard.** A space has no faces. Reading `BoundBox.XLength`
  off it does not raise — it returns nonsense, which is worse. Delete the empty
  object so it does not end up in the group.
- **Measuring the real advance.** Use the glyph's own `XLength`, not a nominal
  per-character width. Proportional fonts vary enough that estimated widths
  visibly drift over a long string.

Centring a straight line of text is then arithmetic:

```python
def centred_text(doc, string, y, size, font, tracking):
    glyphs = [_shapestring(doc, ch, size, font) for ch in string]
    total = sum(w for _, w in glyphs) + tracking * (len(glyphs) - 1)
    x, placed = -total / 2.0, []
    for obj, w in glyphs:
        if obj is not None:
            obj.Placement = FreeCAD.Placement(FreeCAD.Vector(x, y, 0),
                                              FreeCAD.Rotation())
            placed.append(obj)
        x += w + tracking
    doc.recompute()
    return placed
```

`Size` is the **cap height** in mm, and a ShapeString sits on its baseline at
the origin — so a line of text with `Size = 2.0` and baseline `y` occupies
`y` to `y + 2.0`. Lay blocks out by baseline and keep the cap height in a
constant.

---

## 6. Text on an arc

This is where 2D seal-and-badge work actually lives, and it has two traps that
both produce output that looks nearly right.

### 6.1 Placement

For a glyph of width `w` on the ray at angle `t`:

```python
rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), t + 90.0 if invert else t - 90.0)
base = (FreeCAD.Vector(math.cos(math.radians(t)),
                       math.sin(math.radians(t)), 0) * radius
        - rot.multVec(FreeCAD.Vector(w / 2.0, 0, 0)))
obj.Placement = FreeCAD.Placement(base, rot)
```

The `- rot.multVec(...)` term is what centres the glyph *on* its ray. Without
it every character hangs off to one side by half its width, and the string
drifts against its intended centre angle by half the last glyph.

`invert=False` (rotate `t − 90`) puts the letters upright with their feet
toward the centre — use it across the top. `invert=True` (rotate `t + 90`)
puts their tops toward the centre so the legend still reads left-to-right along
the bottom. Reading order also flips: step **clockwise** along the top and
**counter-clockwise** along the bottom.

### 6.2 The two radii

**Trap one: upright text grows outward, inverted text grows inward.** Both are
measured from the baseline. So for the two arcs of one ring to share a band:

```python
H_ARC     = 3.4              # cap height
R_ARC_OUT = 19.6             # outer edge of the lettering -- the real design input
R_TXT_TOP = R_ARC_OUT - H_ARC    # upright: baseline is the INNER edge
R_TXT_BOT = R_ARC_OUT            # inverted: baseline is the OUTER edge
```

Pass both arcs the same baseline radius and the bottom legend lands a full cap
height too far inward. It reads as "the bottom text is a bit small" rather than
as a bug, and it will survive any number of visual passes. Design in terms of
the band's **outer edge** and derive the baselines.

**Trap two: angular advance must be measured across the band, not at the
baseline.** A glyph's angular width depends on the radius you measure it at.
Step at the baseline and upright text splays apart while inverted text crowds
together:

```python
if advance_radius is None:
    advance_radius = radius - size / 2.0 if invert else radius + size / 2.0

total = sum(w for _, w in glyphs) + tracking * (len(glyphs) - 1)
span  = math.degrees(total / advance_radius)
step  = 1.0 if invert else -1.0
a     = centre_deg - step * span / 2.0

for obj, w in glyphs:
    half = math.degrees((w / 2.0) / advance_radius)
    t = a + step * half                     # ray through this glyph's centre
    ...                                     # place per §6.1, using `radius`
    a = t + step * (half + math.degrees(tracking / advance_radius))
```

Position at `radius` (the baseline); advance at `advance_radius` (the middle of
the band). Two different radii doing two different jobs.

### 6.3 Tag the glyphs

Label each glyph with the legend it belongs to:

```python
obj.Label = "%s_%s" % (tag, obj.Name)       # e.g. arcName_ShapeString017
```

Sixty anonymous `ShapeString` objects are unmeasurable. Tagged ones let §8
compute each legend's radial band and angular span independently, which is the
only way to check that two arcs do not collide with each other or with anything
between them.

### 6.4 Solve the tracking, do not nudge it

Once you know the arc a legend has to span — because you measured it off a
reference (§9.3) — stop converging on it by trial. Measure the glyphs once in a
throwaway document and solve for the letter spacing directly:

```python
widths = []
for ch in string:
    o, w = _shapestring(doc, ch, size, font)
    if o is not None:
        doc.removeObject(o.Name)          # measuring only; keep nothing
    widths.append(w)

adv = radius - size / 2.0 if invert else radius + size / 2.0   # §6.2 trap two
need = math.radians(target_deg) * adv                          # arc length wanted
tracking = (need - sum(widths)) / (len(widths) - 1)
```

One calculation lands within a couple of tenths of a degree. In this session
targets of 101.5° and 172.0° came out at 101.3° and 172.0° on the first
rebuild, replacing what had been three rounds of guessing per legend.

It also tells you when a target is *impossible*: a negative tracking means the
glyphs alone overflow the arc, and what you need is a narrower face or a
smaller cap height, not more fiddling. Re-solve whenever you change the font,
the cap height or the band radius — all three move the answer.

---

## 7. Arrays, and baking them

`Draft.make_polar_array` is the right tool for milled edges, dashed circles,
bolt circles — anything repeated about a centre. Build one element at angle 0
and array it:

```python
tooth = Draft.make_rectangle(R - R_ROOT, TOOTH_W)
tooth.Placement = FreeCAD.Placement(
    FreeCAD.Vector(R_ROOT, -TOOTH_W / 2.0, 0), FreeCAD.Rotation())
tooth.MakeFace = True
doc.recompute()
arr = Draft.make_polar_array(tooth, number=N, angle=360.0,
                             center=FreeCAD.Vector(0, 0, 0))
```

The array rotates both position and orientation, so an element built
tangentially at angle 0 stays tangential all the way round.

**Then bake it** (Golden Rule 7):

```python
doc.recompute()
baked = doc.addObject("Part::Feature", name)
baked.Shape = arr.Shape
baked.Label = name
doc.removeObject(arr.Name)
doc.removeObject(tooth.Name)      # the source element is not part of the design
doc.recompute()
```

The Draft array's view provider causes the SVG exporter to write
`fill:url(#shape color)`, referencing a gradient that appears nowhere in the
file. Every element of the array then renders unfilled. A `Part::Feature`
exports with a flat fill, exactly like the glyphs do. Baking also removes the
source element, which otherwise sits in the document as a duplicate at angle 0.

You lose parametricity. For finished artwork that is the right trade — the
parameters live in the build script, which is the actual source of truth.

---

## 8. Verify numerically

A build that ran is not a build that is correct. Measure the document.

**Overall size and centring** — the one number a spec usually pins down:

```python
bb = None
for o in grp.Group:
    if hasattr(o, "Shape") and not o.Shape.isNull():
        bb = o.Shape.BoundBox if bb is None else (bb.add(o.Shape.BoundBox) or bb)
print("%.4f x %.4f mm  centre (%.4f, %.4f)"
      % (bb.XLength, bb.YLength, bb.Center.x, bb.Center.y))
```

**Radial clearances**, from actual vertices — never by eye:

```python
def rmax(o):
    return max((math.hypot(v.X, v.Y) for v in o.Shape.Vertexes), default=0.0)
```

For each tagged legend, report `min`/`max` vertex radius and compare against
whatever it must not touch. Two arcs that should share a band must report the
**same** radii — that is the check that catches §6.2 trap one.

**Angular spans**, to catch collisions between things on the same ring:

```python
angs = sorted(math.degrees(math.atan2(v.Y, v.X)) % 360
              for o in objs for v in o.Shape.Vertexes)
print("%.1f .. %.1f deg" % (min(angs), max(angs)))
```

**Element counts and spacing**, to confirm an array did what you asked:

```python
cs = sorted(math.degrees(math.atan2(f.CenterOfMass.y, f.CenterOfMass.x)) % 360
            for f in baked.Shape.Faces)
deltas = [round(cs[i + 1] - cs[i], 4) for i in range(len(cs) - 1)]
print(len(cs), min(deltas), max(deltas))       # want count, and min == max
```

**Count what you expect to exist.** `len(grp.Group)`, the number of rules, the
number of dots, the position of each. When a user says "remove the line above
the number", confirm *which object that is* by its coordinates before deleting
anything — object names and labels drift as a build evolves, and the internal
`Name` may not match the displayed `Label` at all.

---

## 9. Looking at it

### 9.1 Capture

Do not rely on the `view_control` screenshot tool writing the file — it may
return base64 without leaving anything on disk. Save explicitly, then `Read`
the file:

```python
FreeCADGui.Selection.clearSelection()        # selection renders bright green/blue
v = FreeCADGui.activeDocument().activeView()
v.setCameraType("Orthographic")
v.viewTop()
v.fitAll()
v.getCameraNode().height.setValue(48.0)      # zoom: smaller = tighter
v.saveImage(path, 900, 900, "White")
```

Then `Read` the path as an image.

- **`"White"`** as the background. The default gradient makes black artwork
  hard to judge.
- **Clear the selection.** An object left selected renders highlighted, and you
  will read it as a colour bug in your geometry.
- **Zoom by setting the camera `height` only, after `fitAll()`.** Setting
  `position` as well moves the camera through the near clip plane and you get a
  blank white image — which looks exactly like a build that produced nothing.
- **The Draft grid** shows up in captures. `Draft_ToggleGrid` via
  `FreeCADGui.runCommand`, or just zoom in enough that it stops mattering.

### 9.2 Styling for review

```python
for o in doc.Objects:
    vo = getattr(o, "ViewObject", None)
    if vo is None:
        continue
    for attr, value in (("LineColor", (0.0, 0.0, 0.0)),
                        ("ShapeColor", (0.0, 0.0, 0.0)),
                        ("LineWidth", 2.5)):
        try:
            setattr(vo, attr, value)
        except Exception:
            pass
```

Wrap each set in `try` — view providers differ by object type and not all of
them carry every property.

### 9.3 Measuring a reference image

If the user supplies a reference — a scan, a stamp impression, the figure
printed in the regulation — **measure it**. Twenty lines of pixel arithmetic
replace a dozen rounds of adjust-look-adjust, and they give you numbers you can
put in a constants block and defend afterwards.

Load it through Qt, which is already in the process:

```python
from PySide6.QtGui import QImage
im = QImage(path)
def dark(x, y):
    c = im.pixelColor(int(x), int(y))
    return (c.red() + c.green() + c.blue()) / 3.0 < 128
```

**Find the true centre first.** Every number downstream is a fraction of the
outer radius, so a centre a few pixels out corrupts all of them. The ink
bounding box is wrong when the image is cropped or the artwork sits slightly
off in its canvas; the ink centroid is wrong whenever the design is
asymmetric — on one reference here the two disagreed by 4 px. Fit a circle to
the outermost ink and iterate:

```python
def outer_pts(cx, cy, floor):
    pts = []
    for k in range(1440):
        a = math.radians(k * 0.25)
        r = 130.0
        while r > floor:
            if dark(cx + r * math.cos(a), cy - r * math.sin(a)):
                pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
                break
            r -= 0.25
    return pts
# then a Kasa least-squares circle fit over pts, re-seeding cx, cy a few times
```

**The radius floor is load-bearing.** Without it, rays that land in a gap
between teeth run all the way inward to the next feature and drag the fit off
by tens of pixels. The symptom is a fitted radius well below the bounding box
half-width, and a spread of point radii that is a large fraction of R — here,
`R 100.23 (spread 67.12..110.89)` before the floor, `R 106.85 (spread
97.72..109.53)` after.

**Then ask which *angles* carry ink, not which radii.** A ray through the
artwork hits whatever happens to lie on it, so a radial profile through
lettering returns one letter's strokes rather than the band the letters sit in.
Angular occupancy within a radial band is the measurement that answers layout
questions:

```python
def occupancy(lo, hi, step=0.25):
    out = []
    for k in range(int(360 / step)):
        a = math.radians(k * step)
        hit, f = False, lo
        while f <= hi:
            if dark(cx + R * f * math.cos(a), cy - R * f * math.sin(a)):
                hit = True
                break
            f += 0.003
        out.append((k * step, hit))
    return out                      # then group contiguous True runs
```

The contiguous groups come back as the **individual letters**. That hands you,
in one pass: the exact angular span of a legend (first group's start to last
group's end), the letter count as a check that you banded correctly, the
inter-letter gap, and the position of anything sitting between the legends. On
the references here it gave `WISCONSIN` spanning 32.5°–151.0° as nine clean
groups, the bottom legend 185.2°–357.2°, and the two stars centred at 14.6° and
168.8° — all of which went straight into the build as targets.

**Count repeated elements by rising edges, at more than one radius:**

```python
for fr in (0.94, 0.955, 0.97):
    prev, rises = None, 0
    for k in range(7200):
        a = math.radians(k * 0.05)
        v = dark(cx + R * fr * math.cos(a), cy - R * fr * math.sin(a))
        if prev is not None and v and not prev:
            rises += 1
        prev = v
    print(fr, rises)                # 129 / 128 / 129 -> 128 teeth
```

Agreement across radii is what tells you that you are counting teeth and not
noise. Track the duty cycle (ink samples / total) too — it separates "more
teeth" from "fatter teeth" when a user asks for a finer edge.

**Isolate one feature with a bounded flood fill** when you need its size, or
need to know whether it is solid or hollow — seed at the nearest ink pixel and
refuse to leave a box around it. Without the bound it leaks along whatever
touches the feature: a star touching the inner circle came back here as a
13×48 blob, which is obviously wrong only because the numbers were printed.
Counting enclosed background pixels inside the blob's box is enough to tell a
hollow star from a solid one.

**Check whether a result is just your search window.** An early scan here
reported ink "from 20.0 to 160.0 degrees" — which were precisely the bounds it
had been given. A measurement that lands exactly on its own limits is not a
measurement.

**Be careful what you conclude from an impression.** One reading in this
session gave a ring at 0.68R along the top and 0.56R along the bottom — the
stamp had been pressed at an angle. Average across the axis, treat the numbers
as approximate, and do not chase a distorted artifact into your geometry. Where
two references disagree, prefer the one the user pointed at, and say which you
used.

### 9.4 Reading the spec out of a PDF

Regulations that fix a seal's dimensions arrive as PDFs, and the box may have
no `pdftotext`, no `pypdf` and no `PyMuPDF` — FreeCAD's bundled Python had none
of them, and neither did the system one. You do not need them. Parse the file
directly:

- Objects are `N 0 obj ... endobj`; a `/Type /ObjStm` stream holds more objects
  packed inside it and has to be expanded before you can see them.
- Text is usually Identity-H CID-keyed, so bytes in the content stream are
  glyph ids, not characters. Each font carries a `/ToUnicode` CMap — parse its
  `beginbfchar` and `beginbfrange` blocks into a dict per font, track the
  current font through `/F<n> ... Tf` operators, and decode the hex strings in
  `Tj` / `TJ`. Fake the spaces from large negative kerns in `TJ` arrays.
- The CMap streams are often **uncompressed** even when the page content is
  Flate. Do not assume every stream needs inflating; try, and fall back.

Figures matter more than the prose in this work, and an embedded bitmap comes
out with no image library at all — read `/Width`, `/Height` and `/ColorSpace`
off the XObject, inflate the stream and hand the raw bytes to Qt:

```python
img = QImage(bytes(data), W, H, W * 3, QImage.Format_RGB888)
img.save(png_path)
```

Then `Read` that PNG and measure it with §9.3. This is how the approved seal
designs — the part of the rule that actually constrains the artwork — got out
of a 342 KB regulation PDF and into the constants block.

---

## 10. Exporting SVG

```python
import importSVG
importSVG.export(list(grp.Group), path)
```

FreeCAD's SVG output has three defects that matter for artwork. All three
produce a file that is visibly wrong in any viewer while FreeCAD's own display
looks perfect — so **FreeCAD's viewport does not verify the export**.

### 10.1 Glyph counters fill in

Each ShapeString exports as one path whose inner contours are subpaths, but the
exporter cannot reverse their winding. It says so, once per glyph:

```
DraftGeomUtils.invert: unable to invert <BSplineCurve object>
```

Under the default nonzero fill rule the holes in R, E, O, A and S disappear and
the text renders as solid blobs. **Treat that log line as the diagnostic it
is** — it floods the `execute_python` output and is easy to dismiss as noise.

Fix: add `fill-rule:evenodd` to every filled path.

### 10.2 Strokes fatten filled shapes

The exporter writes the view object's `LineWidth` as a **millimetre** stroke,
including on shapes that are already filled. On fine geometry this is
catastrophic: a 0.62 mm wide tooth with a 0.7 mm stroke grows to 1.32 mm and
closes the 0.83 mm gaps, turning a milled edge into a solid ring.

Fix: filled shapes need no stroke at all.

```python
def _fix_svg(path):
    import re
    with open(path, encoding="utf-8") as fh:
        svg = fh.read()

    def element(m):
        el = m.group(0)
        filled = "fill:#" in el
        el = re.sub(r'stroke-width="[^"]*"',
                    'stroke-width="%s"' % (0 if filled else STROKE), el)
        el = re.sub(r'stroke-width:[^;"]*',
                    'stroke-width:%s' % (0 if filled else STROKE), el)
        if filled:
            el = el.replace('stroke="#000000"', 'stroke="none"')
            if "fill-rule" not in el:
                el = el.replace("fill:#", "fill-rule:evenodd;fill:#")
        return el

    svg = re.sub(r"<(?:path|circle)\b[^>]*>", element, svg)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
```

### 10.3 Faces with holes export as solid blobs

`importSVG` writes only the **outer** boundary of a Draft object's face. An
annulus, an outlined star, any ring — each reaches the SVG as a solid shape. On
a seal that means the circle around the centre block exports as a disc that
blacks out the name, the number and the city, while FreeCAD's viewport shows
the ring correctly the entire time.

There are three ways to get this wrong, and each looks right somewhere:

- **`Part::Cut` of two Draft circles.** Collapses to a single `<circle>`
  element with the inner contour simply gone — the exporter special-cases exact
  circular edges.
- **One closed polygon tracing the outer boundary then the inner one, joined by
  a zero-width slit.** OCC heals the slit back into a proper annular face — one
  face, *two* wires — and the exporter drops the inner wire again. The
  give-away is a `Wires` count of 2 on a shape you built as a single loop.
- **`Part.Face([outer_wire, inner_wire])`.** This one *exports correctly* —
  one `<path>`, two subpaths — and is still wrong, because it is not a hole
  geometrically. Its area comes back as the **sum** of the two wires, so the
  `.FCStd` you ship carries a solid shape and any later area, offset or boolean
  is wrong. Correct SVG is not evidence of correct geometry.

What works is a real boolean between **polygon** faces, wrapped in a
`Part::Feature`:

```python
def _holed_face(doc, outer_pts, inner_pts, name):
    outer = Part.Face(Part.makePolygon(outer_pts + [outer_pts[0]]))
    inner = Part.Face(Part.makePolygon(inner_pts + [inner_pts[0]]))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = outer.cut(inner)
    obj.Label = name
    doc.recompute()
    return obj
```

Both halves carry weight. **Polygons**, so there is no exact circular edge for
the exporter to special-case — a 360-gon annulus is within 0.006% of the true
area and 0.0005 mm on radius, which nothing will ever show. **A boolean**, so
OCC records an actual hole. The result is one face with two wires and the right
area, and `importSVG` writes it as one `<path>` with two subpaths, which the
`fill-rule:evenodd` from §10.1 renders as a hole.

Check both the geometry and the file, because either can be right alone:

```python
f = obj.Shape.Faces[0]
print(len(obj.Shape.Faces), len(f.Wires), f.Area)   # want 1, 2, the true area
```

**Nested outlines: the band width is set by the edge, not the point.** When the
hole is a uniform scale `h` of the outer profile, the band between them has
constant width `(1 - h) * d`, where `d` is the perpendicular distance from the
centre to an *edge*. For a circle `d` is the radius and the intuition holds.
For a five-pointed star `d` is about a **third** of the point radius, so
reasoning from the circumradius overstates the band by 3x — halving the outline
weight of a star here moved the real band 0.491 mm → 0.246 mm, not the
1.589 mm → 0.794 mm the point radius suggested. Measure it instead of deriving
it:

```python
outer = max(f.Wires, key=lambda w: w.BoundBox.XLength)
inner = min(f.Wires, key=lambda w: w.BoundBox.XLength)
print(min(outer.distToShape(v)[0] for v in inner.Vertexes))
```

### 10.4 Construction geometry exports as visible strokes

An unfilled circle that reads as a faint guideline in the FreeCAD viewport
exports as a stroked ring that every SVG reader draws at full weight. If a
radius is something you *thought with* rather than something the design
*contains*, keep it as a constant and draw nothing. In finished artwork the
healthy end state is usually that **every** element is filled and nothing is
stroked (see the audit below).

### 10.5 Verify the exported file

Audit the styles:

```bash
grep -o 'fill:[^;"]*' out.svg | sort | uniq -c
grep -c 'stroke="#000000"' out.svg
```

Then reconcile the element count against what you built — teeth + dashes + dots
+ rules + glyphs should equal the number of paths, with spaces excluded from
the glyph count. A count that reconciles exactly is good evidence nothing was
dropped or duplicated.

**But a reconciling count proves only that. It says nothing about what is
*inside* each path.** In this session an export was audited at "168 paths, 0
circles, 168 fills, 0 strokes" — every number exactly as predicted — and the
inner circle was a solid black disc sitting over the middle of the seal. The
count was right *because the ring was there*; what had been truncated was the
ring's contents, from two contours to one. Counting elements cannot catch a
§10.3 failure, and neither can any style audit.

So check the paths that are supposed to carry holes:

```python
els = re.findall(r"<path\b[^>]*>", svg)
holes = [e for e in els
         if re.search(r'\sd="([^"]*)"', e).group(1).count("M") > 1]
print(len(holes))        # ring + hollow shapes + every glyph with a counter
```

One `M` per subpath. A ring, an outlined star, and every O, P, R, A, G and S
belong in that list; if a shape you built with a hole is missing, the hole is
gone. Going further and checking the radial extent of the ring's own path —
that it spans *both* radii rather than only the outer one — is what finally
caught the bug here.

Match the element first and the `d` attribute inside it, as above. A lazy
pattern across the whole element (`<path[^>]*?d="([^"]*)"`) cheerfully matches
some other quoted attribute and hands you an object id instead of a path; the
symptom is a "longest path" of twenty characters.

Then **render it**. Qt is already in the FreeCAD process, so rasterize through
a real SVG renderer in-session:

```python
from PySide6.QtSvg import QSvgRenderer          # PySide2 on older builds
from PySide6.QtGui import QImage, QPainter, QColor

r = QSvgRenderer(svg_path)
print("valid:", r.isValid())
img = QImage(900, 900, QImage.Format_ARGB32)
img.fill(QColor(255, 255, 255))
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing, True)
r.render(p)
p.end()
img.save(png_path)
```

`Read` that PNG. This is the only check that tests the artifact you are
actually delivering.

If the work has a legibility requirement, render it small as well — at the
pixel size it will really be reproduced at — and read it back:

```python
img = QImage(131, 131, QImage.Format_ARGB32)     # then scale up to inspect
```

Scale that small render back up with `Qt.FastTransformation`, not the smooth
one: you want to see the pixels it actually produced, not an interpolation that
flatters them.

**Know the physical floor as well as the pixel one.** A 1-3/4" seal at 300 dpi
is about 520 px, so a 0.25 mm feature is under 3 px — fine digitally, but a
laser-cut rubber stamp or an embosser will not hold a line much below
0.25–0.30 mm, and ink spread closes anything finer. When a requested change
takes a feature under that, say so with the number and offer the constant that
reverses it, rather than either silently refusing or silently shipping
something that will not stamp.

---

## 11. Where the output goes

Per [`AGENTS.md`](../AGENTS.md):

- Write a `.py` only if asked, into `examples/<name>/`, and save the `.FCStd`
  beside it.
- **Anything carrying a real identity — a name, a licence or registration
  number, a client's drawing — goes in `private/`**, which is gitignored, and
  is never committed. A seal or signature block is also a forgeable artifact,
  which is a second reason it does not belong in a public repo.
- Never write into the user's FreeCAD installation.

Have the build script save its own outputs, so one run reproduces every
deliverable:

```python
def save(doc, directory, stem):
    import importSVG
    fcstd = os.path.join(directory, stem + ".FCStd")
    svg = os.path.join(directory, stem + ".svg")
    png = os.path.join(directory, stem + ".png")
    doc.saveAs(fcstd)
    importSVG.export(list(doc.getObject("Seal").Group), svg)
    _fix_svg(svg)
    _render_png(svg, png)          # rasterised FROM THE SVG, per §10.5
    return fcstd, svg, png
```

Render the PNG from the exported SVG rather than screenshotting the viewport.
It costs nothing — Qt is already loaded — it makes the deliverable PNG and the
deliverable SVG the same artwork by construction, and it means every save
exercises the export path that §10 says is the one that breaks.

After `saveAs` the document has a path, so with the bridge's autosave on (§2)
every later `execute_python` call rewrites the `.FCStd` while that document is
active. Close or recreate it (the §3 loop already does) before running more
checks, or expect the extra git diff.

Report the paths you wrote, and say plainly whether anything was staged or
committed.

---

## 12. The loop, end to end

1. `check_freecad_connection`; print version, GUI flag, open documents and the
   bridge's autosave preference (§2).
2. Confirm the font carries the glyphs you need (§2.1).
3. **Measure the reference before writing any constants** — fit the centre,
   take the angular spans and element counts, and if the spec is a PDF, get
   the figure out of it (§9.3, §9.4). These become your targets.
4. Write the build script: constants, helpers, `build()`, `style()`, `save()`
   (§3). Solve the legend tracking against the measured spans (§6.4).
5. Close the document, `importlib.reload`, rebuild (§3).
6. Measure it: size, clearances, spans, counts — and the wire count and area
   of anything with a hole (§8, §10.3).
7. Screenshot it and look (§9).
8. Adjust a constant, go to 5. Expect several rounds.
9. Export, audit the styles, reconcile the element count, **check that the
   holes survived**, and **render the exported file and read it back** (§10).
10. Save into the right directory (§11), report the paths, and state what you
    verified rather than that it built.

Before an existing build is handed back after edits, re-run 6 and 9 in full.
Most of the traps in this document are silent, and a change that only touched
one constant can still take a feature under a clearance or a reproduction
limit.
