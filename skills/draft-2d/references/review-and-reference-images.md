# Looking at it (§9)

Part of the `draft-2d` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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
