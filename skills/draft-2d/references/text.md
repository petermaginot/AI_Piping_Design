# Text (§5–§6)

Part of the `draft-2d` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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
