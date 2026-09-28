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

**Size and place the table yourself; the defaults run it off the sheet.**
Measured in FreeCAD 1.1:
- **Position:** `DrawViewSpreadsheet.X/Y` is the table's **centre**, not a
  corner.
- **Size:** row heights and column widths come from the `Spreadsheet::Sheet`,
  in pixels of 0.2646 mm. The default row is 30 px, about 8 mm, so a
  30-row BOM is 240 mm tall: taller than the ANSI B drawing area.
- **Text:** the drawn text size is `TextSize`. Setting it to 3.0 printed
  about 1 mm text; 9.0 prints legibly in a 15 px (4 mm) row.

```python
for col, w in zip("ABCD", (40, 66, 60, 322)):  sheet.setColumnWidth(col, w)
for i in range(1, last_row + 1):             sheet.setRowHeight(str(i), 15)
view.TextSize = 9.0
height = last_row * 15 * 0.2646
view.X, view.Y = right_col_x, top_y - height / 2       # hang it from a top edge
```

Return the table's bottom edge, and stack the notes under it.

### 9.1.1 One row per model mark

When the model already carries typed marks (`[F4]`, `[P8]`, from the
`quetzal-piping` skill §9.6), use **those** as the BOM marks and balloon
text. Don't let the drawing invent its own 1..n numbering. Then the fitter,
the model tree and the drawing all say `[P8]`, one row per mark, and a
spool drawing lists just the marks in its container, plus the assembly
material bolted to it.

- **Pipe quantity is its cut length**, printed in the sheet's format
  (§11.3.1).
- **Small-bore pipe at a stocked pre-cut length** (3, 4, 6 or 12 in, NPS 2 and
  under) is a **nipple**: `NIPPLE 6 IN, PBE`, or `TOE` when one end is
  threaded.
- **Everything else small-bore** is `PIPE, CUT TO LENGTH`.

### 9.1.2 Notes

Put sheet notes in a `DrawViewAnnotation`. Its `X/Y` is the **centre** of the
text block, and it does **not** wrap: a long line runs straight through the
border. Wrap the lines yourself. About 66 characters fit a 130 mm column at
`TextSize = 2.5`, and each line takes about 5.2 mm. Place the block from the
height you computed. Number the notes, and when a note is derived from the
model (a skew angle, a pig space, a flange roll), format it from the model
value, not a typed number.

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

### 10.2 When the push-apart fails: re-space, then clear the caption

The sort-and-push above only pushes forward. With 15 components bunched on
one side of a tall, thin view (a 1" line with a vertical leg), the pushed
angles ran past +π. The bubbles that wrapped round landed on top of ones
already placed: `[P16]` fully hidden behind `[P17]`, and `[E5]` behind
`[V9]`. Two fixes, applied after `add_balloons`:

1. **Measure, then re-space.** If any two bubbles are closer than about
   12 mm on the sheet, re-space all of them evenly round a slightly wider
   ring, in their existing angular order, leaving about ±25° clear at the
   bottom. Leaders stay on their parts. On the launcher drawings this raised
   the closest pair from overlapping to 21 mm apart.
2. **Clear the caption.** The caption prints centred just below the
   outline (§8). The skipped bottom sector does not always cover it, because
   a wide caption reaches past ±20°. Push any bubble inside the caption's
   box (length × about 2.9 mm per character, about 8 mm tall) out sideways.

Report the minimum spacing with the other checks (§14).

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
