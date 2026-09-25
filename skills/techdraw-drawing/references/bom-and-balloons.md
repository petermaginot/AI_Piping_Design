# Bill of material and balloons (§9–§10)

Part of the `techdraw-drawing` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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
