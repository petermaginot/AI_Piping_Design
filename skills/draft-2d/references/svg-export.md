# Exporting SVG (§10)

Part of the `draft-2d` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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
