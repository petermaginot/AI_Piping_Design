---
name: draft-2d
description: Build flat 2D artwork (engineering seals and stamps, logos, title-block furniture, plate profiles, text on an arc) with FreeCAD's Draft workbench, over MCP, and export clean SVG and PNG. Use when the user asks for 2D Draft geometry or artwork in FreeCAD, including reproducing one from a reference image or PDF. Not for piping (quetzal-piping) or drawing sheets (techdraw-drawing).
---

# Driving the Draft workbench over MCP

Directions for an AI agent that builds **flat 2D artwork** — seals, stamps,
logos, title-block furniture, plate profiles — with FreeCAD's **Draft**
workbench, by driving the user's live session over the MCP server
([blwfish/freecad-mcp](https://github.com/blwfish/freecad-mcp)).

This is the sibling of the `quetzal-piping` skill, which is for piping: `pCmd`
makers, `tablez/` lookups, port chains. **None of that applies here.** Draft work
is plain geometry — circles, rectangles, arrays and outlined text — and its traps
are entirely different ones.

The rules below are the non-obvious ones: the places where a build runs clean,
looks right in the GUI, and still ships a broken deliverable.

## Read before you build

Section numbers (§) are the same in every file of this skill; a cross-reference
such as "§10.3" means the file listed for §10 below.

| § | Contents | File | Read |
|---|---|---|---|
| 1–4, 7, 8, 11, 12 | Golden rules, preamble and fonts, the build-script loop, maker traps, arrays, verification, output, the loop | this file | every build |
| 5–6 | ShapeString text; text on an arc | [references/text.md](references/text.md) | the artwork has any text |
| 9 | Capturing and looking; styling for review; measuring a reference image; reading a spec out of a PDF | [references/review-and-reference-images.md](references/review-and-reference-images.md) | every build |
| 10 | Exporting SVG, and verifying the exported file | [references/svg-export.md](references/svg-export.md) | before any export |

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

## 11. Where the output goes

Per [`AGENTS.md`](../../AGENTS.md):

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
Most of the traps in this skill are silent, and a change that only touched
one constant can still take a feature under a clearance or a reproduction
limit.
