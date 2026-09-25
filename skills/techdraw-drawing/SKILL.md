---
name: techdraw-drawing
description: Turn a finished FreeCAD piping model into a fabrication drawing with the TechDraw workbench, over MCP. Covers the page and template, views, bill of material, balloons and dimensions to work points, then verifies the page numerically. Use when the user asks for a drawing, sheet, iso/front/top views, BOM or balloons of a model, or to update an existing TechDraw page.
---

# Drawing a spool with TechDraw

Directions for an AI agent that turns a finished piping model into a **drawing**:
views, a bill of material, balloons and dimensions on a TechDraw page, built in
the user's live FreeCAD session over the MCP server.

This is the sibling of the `quetzal-piping` and `draft-2d` skills. The first is
for building piping: `pCmd` makers, `tablez/` lookups, port chains. The second is
for 2D Draft geometry. **Neither applies here.** By the time you use this skill
the geometry already exists and is correct; nothing you do should change it.

The rules below are the non-obvious ones: the places where the page builds
without an exception, looks plausible on screen, and is still wrong — a
dimension that reads 0.00, a BOM whose size column has silently become
millimetres, a balloon pointing at nothing — or is so slow it cannot be used.

Everything here was measured against a live FreeCAD 1.1 session. The worked
example is [`examples/TechDraw_example/make_techdraw_page.py`](../../examples/TechDraw_example/make_techdraw_page.py).

## Read before you build

Section numbers (§) are the same in every file of this skill; a cross-reference
such as "§11.2" means the file listed for §11 below. **Read every file marked
"every drawing" before you send any drawing code.**

| § | Contents | File | Read |
|---|---|---|---|
| 1–4, 14–16 | Golden rules, session preamble, the container, page and template, verification, output, the loop | this file | every drawing |
| 5–8 | Views and projection, the view coordinate frame, transparency, captions | [references/views.md](references/views.md) | every drawing |
| 9–10 | Bill of material, balloons | [references/bom-and-balloons.md](references/bom-and-balloons.md) | the drawing has a BOM or balloons |
| 11 | Dimensions to work points; blank pages; recovering after a crash | [references/dimensions.md](references/dimensions.md) | every drawing |
| 12–13 | Keeping the page off; why the page is slow | [references/performance.md](references/performance.md) | every drawing |

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
wrong one. `FreeCAD.setActiveDocument(doc.Name)` first, every time — on the
document you are building in, and never on the user's own file (§2.3).

### 2.3 The user's own files are reference, not a work surface

A model the user opened from their own drive is not yours to rebuild, recompute
or save. Read it to learn the conventions; build on a document in the repo.
Recomputing someone's page marks their file modified, and a TechDraw teardown
can crash FreeCAD outright — which it did, once, while this guide was written.

**The MCP bridge will save it for you unless told not to.** Before running your
code, every `execute_python` call saves the **active** document, if it has a
file path. The AICopilot preference `AutoSaveBeforeRiskyOp` controls this, and
it defaults to on. So a user's model that you activated just to read from is
written back to their drive on your very next call, including any recompute
you caused. Check the preference before anything else:

```python
FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/AICopilot") \
       .GetBool("AutoSaveBeforeRiskyOp", True)
```

If it is on and one of the user's saved files is open, **stop and tell them**.
Offer to switch it off (`.SetBool("AutoSaveBeforeRiskyOp", False)`), and do it
only if they agree. Either way, read their document through `find_doc` (§2.1)
without activating it. The repo document you are drawing on is saved too, on
every call, so expect it to show in `git status` as you go.

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

Per [`AGENTS.md`](../../AGENTS.md):

- Write a `.py` only if asked, into `examples/<name>/`, and save the `.FCStd`
  beside it.
- Never write into the user's Quetzal installation, and never save a document
  that came from outside the repo.
- Photographs, client drawings and site tags stay out of the repo — `private/`
  is gitignored for that.

---

## 16. The loop, end to end

1. Confirm the session; check the bridge's autosave preference; set the active
   document (§2).
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
this skill is about.
