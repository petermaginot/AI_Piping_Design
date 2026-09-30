# Construction isometrics (§17–§19)

Part of the `techdraw-drawing` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 17. Construction isometrics

A **construction isometric** is the drawing a fabricator builds a spool from.
It is not to scale, and it shows one line or spool per sheet. It has:
- isometric symbols;
- dimensions to work points;
- balloons keyed to a bill of material;
- slope, roll and skew marks;
- a north arrow;
- notes;
- a title block.

Quetzal generates the whole sheet. **Do not build one by hand from TechDraw
views.** A scaled TechDraw iso view cannot carry dimensions (§11.4), and a
hand-built NTS iso is weeks of work that Quetzal has already done.

Every generated page holds:

| Object | What it is |
|---|---|
| `TechDraw::DrawViewSymbol` (`Isometric…`) | The whole iso as one sheet-sized SVG: lines, symbols, dimensions, balloons, north arrow. The inputs needed to regenerate it are stored on it as `Iso*` properties |
| `Spreadsheet::Sheet` (`IsoBOM…`) + `DrawViewSpreadsheet` | The BOM, editable. Hidden columns F–G hold each row's key and its generated text |
| `TechDraw::DrawViewAnnotation` (`IsoNotes…`) | The notes, editable |
| `DrawSVGTemplate` | ANSI B (431.8 × 279.4) or ISO A3 (420 × 297), with the title block filled |

The code is Quetzal's `iso/` and `pcf/` packages. The model is exported to PCF
data in memory and drawn from that, so a `.pcf` file from any other program
(Isogen, CAESAR II, a plant-design package) can be drawn the same way (§17.4).

### 17.0 Which drawing the user wants

| The user asks for | Build |
|---|---|
| "an iso", "isometric", "construction iso", "fabrication iso", "spool iso", "NTS iso", "iso from this PCF" | **Construction iso** (this file) |
| plan, elevation, top, front, "assembly drawing", "to scale", an iso *view* beside orthographic views | **Scaled TechDraw drawing** (§1–§16) |
| both | Both, on separate pages. They share nothing |

When the request is only "an isometric", the construction iso is the default.
Say which one you built at handover, so the user can ask for the other.

**What does not apply from §1–§16:** the generated page has no projected
views, cosmetic vertices, TechDraw dimensions or TechDraw balloons. So none
of the following is needed:
- the projection wait (§5.2);
- the cosmetic-vertex and `AutoCorrectRefs` rules (§6, §11);
- the container-as-performance-control rule (§3, §13).

The SVG is regenerated wholesale, so you cannot add a TechDraw dimension or
balloon to it that stays right. Everything is changed by regenerating (§17.3).

**What still applies:**
- the session preamble, target document and autosave check (§2);
- the user's files are reference, not a work surface (§2.3);
- open exactly one window per page (§11.6);
- where output goes (§15).

**Preconditions.** In the session:

```python
import iso.iso_page, pcf.pcf_export     # ImportError -> Quetzal predates the iso generator
```

If the import fails, say so. Offer the scaled drawing, or ask the user to
update Quetzal. Do not try to reimplement the generator.

### 17.1 What goes on each sheet

**One page is one pipeline**, and Quetzal decides what a pipeline is. The rule
is in `pcf_export.collect_pipelines`, and the following was observed in a live
session:

- **Nothing passed (whole document):** one page per pipeline. An object
  belongs to the pipeline named after:
  1. its `PypeLine`, if it has one; otherwise
  2. its **top-most** group or `App::Part`; otherwise
  3. the **document label**.

  So every loose object in the document, including loose gaskets, stud sets
  and valves, lands on one extra page named after the document. On the
  launcher model that page held the whole header, and its symbols were shrunk
  to 60%.
- **Objects passed:** exactly **one** page, holding everything passed. It is
  named after the first container found among them, in the order given.
  Pass the spool container first. Passing `[gasket, spool]` titles the page
  "Assembly material".
- **Nested containers name the page after the outermost container.** Passing
  the spool `Spool A-01` inside the header `Header A` gives a page titled
  `Header A`. With no selection, every spool under a header lands on one
  `Header A` page. There is no option to change this. If the user wants a
  sheet per spool, the spool containers must be top-level. The flat form of
  `quetzal-piping` §14 is. If they are nested, tell the user rather than
  regrouping their model.
- **An "Assembly material" container becomes its own page** of disconnected
  gaskets, bolts and valves when nothing is passed. Pass the spool containers
  explicitly instead.
- **Supports** (`Clamp`) move to the pipeline of the pipe they carry.
- **Unsupported objects are skipped with a console warning.** These are
  objects whose `PType` is not in `pcf_map.KEYWORDS`, such as structural
  beams or anything without `PType`.

So, for spools grouped per `quetzal-piping` §14:

- **Welded spool only** (the usual shop iso): pass `[spool_part]`.
- **Spool plus its field material:** pass `[spool_part, gasket, studs,
  valve, …]` for the joints at its ends. A shared joint's material belongs on
  one sheet, not both. Ask, or follow the boundary the user stated (§14.5 of
  that skill).

**The container label becomes the pipeline reference.** It is the page title,
the drawing number and note 4. Name containers for a person before you
generate (`Spool 01`, `PL-003 EQUALIZATION LINE`). A label that is too long
for the title block is wrapped and then cut with "…".

**FreeCAD keeps labels unique, and does it silently.** Relabelling a container
to a name that a scaled drawing's page already uses (`PL-001 MAJOR BARREL
SPOOL`) gives `PL-001 MAJOR BARREL SPOOL001`. That suffix is then printed as
the title, drawing number and pipeline note. After setting a label, assert
`part.Label == wanted`.

**One spool per sheet.** If the warning `symbols shrunk to N%: the line is
long for one sheet` appears, the sheet is crowded. Split the line into
several containers and generate again. Do not hand over a shrunk sheet
without saying so.

### 17.2 Building it over MCP

Drive `iso_page` directly rather than `FreeCADGui.runCommand("Quetzal_CreateIso")`.
The command takes its input from the GUI selection and its units from a
machine preference, so what it draws depends on state you cannot see.

```python
import FreeCAD, FreeCADGui
from iso import iso_page, iso_build, iso_sheet, iso_layout
from pcf import pcf_export

doc = find_doc("Header_with_pig_launcher")          # §2.1
FreeCAD.setActiveDocument(doc.Name)                  # §2.2

# Units, size names and sheet come from the prompt, never from the machine:
# default_options() follows Quetzal's DN/NPS preference.
opt = iso_build.Options(units="ftin",                # "ftin" | "mm"
                        size_system="NPS",           # "NPS" | "DN"
                        sheet=iso_sheet.ANSI_B,      # ANSI_B | ISO_A3
                        rotation=None,               # None = automatic, fewest clashes; 0-3 fixed
                        compression=None)            # None = fit pipe lengths to the sheet

# Console warnings are the only report of skipped parts and crowding: capture them.
warnings = []
_iw, _pw = iso_page._warn, pcf_export._log_warning
iso_page._warn = lambda m: warnings.append(m)
pcf_export._log_warning = lambda m: warnings.append(m)
try:
    doc.openTransaction("Create isometric")          # one undo
    pages = iso_page.pages_from_objects(doc, [spool_part], opt)   # or None: whole document
    doc.commitTransaction()
finally:
    iso_page._warn, pcf_export._log_warning = _iw, _pw
print(warnings)
pages[0].ViewObject.doubleClicked()                  # ONE window, on one page (§11.6)
```

**Rotation.** `rotation` is quarter turns about Z. 0 is FreeCAD's standard
isometric view. `None` tries all four and keeps the one with fewest clashes,
then the largest drawing. It is stored as `IsoRotation = -1`. To match the
user's 3D view, as the toolbar command does:

```python
cam = FreeCADGui.getDocument(doc.Name).ActiveView.getCameraOrientation()
opt.rotation = iso_layout.rotation_for_camera(
    tuple(cam.multVec(FreeCAD.Vector(0, 0, -1))), tuple(cam.multVec(FreeCAD.Vector(0, 1, 0))))
```

Take the camera from a 3D view, not from a TechDraw page window.

**Title block.** The generator writes its own title fields. They are the
pipeline, "PIPING ISOMETRIC", the spec, NTS and the sheet number. It
**blanks** CompanyName, DrawnBy, CheckedBy, Approved1 and 2, Code, Weight and
revision_index. Set any of these afterwards, as a new dict (§4):

```python
t = page.Template
t.EditableTexts = dict(t.EditableTexts, DrawnBy="PM", revision_index="A")
```

### 17.3 Adjusting and regenerating

All the inputs live on the view as properties. To change the drawing, change
the property and regenerate:

| Property | Meaning |
|---|---|
| `IsoRotation` | -1 automatic, 0–3 quarter turns about Z |
| `IsoCompression` | Pipe length factor on paper. 0 = fit to the sheet |
| `IsoUnits` | `ftin` or `mm` |
| `IsoSizeSystem` | `NPS` or `DN` |
| `IsoSheetFormat` | `ANSI B` or `ISO A3` |
| `IsoSource` | Objects drawn. Empty = whole document |
| `IsoPcfPath` | PCF file drawn, instead of model objects |
| `IsoPipeline` | Pipeline reference this page draws. `update()` finds its data by this name |

```python
# iso_views(doc.Objects) returns every view TWICE (once itself, once through
# its page), so de-duplicate, or each page is regenerated twice.
views = {v.Name: v for v in iso_page.iso_views(doc.Objects)}.values()
for view in views:
    view.IsoRotation = 2
    sheet = iso_page.update(view)                    # None = nothing was redrawn
```

To find the page an earlier run made of a container, match
`list(view.IsoSource) == [part]` rather than the page label.

**`update()`, never delete and recreate.** A regenerate merges into the
user's edits, which was confirmed live:

- PT, QTY and SIZE always follow the model. They must agree with the
  balloons.
- A **DESCRIPTION** the user edited is kept.
- Rows the user **added** below the table are kept, under an ADDITIONAL
  heading.
- **Notes** the user appended below the generated block are kept.
- If the user edited the generated notes themselves, the notes are left
  alone and a warning says so.
- An edited row whose item has left the model is dropped, with a warning
  that quotes its text.

A new page throws all of that away. Deleting one is risky too. Removing an
iso page whose window was open left that window behind, orphaned. In one
teardown the next call ended in an `OSError: Access violation`. A macro
that runs again should find its earlier page and `update()` it, not tear it
down. If a page really must go, close its window first.

**But `update()` blanks the title block again.** The user's
CompanyName, DrawnBy and even revision_index were wiped by one regenerate.
Read the fields before `update()` and put them back after:

```python
keep = ("CompanyName", "CompanyAddress", "DrawnBy", "CheckedBy",
        "Approved1", "Approved2", "revision_index", "Code", "Weight")
t = view.findParentPage().Template
saved = {k: v for k, v in t.EditableTexts.items() if k in keep and v}
iso_page.update(view)
t.EditableTexts = dict(t.EditableTexts, **saved)
```

**`update()` returns `None` when the pipeline name no longer matches.**
The only other sign is a console warning, `pipeline '…' no longer found; page
left unchanged`, and the page keeps its old, now wrong, content.

This happens whenever the container that named the page is renamed, or is
moved inside another container (§17.1). If you rename a container on
purpose, set `view.IsoPipeline` to the new label before updating. **Treat
`None` as a failure**, and never report a page as updated without checking
the return value.

**Edit the BOM and notes, never the SVG.** The `Symbol` property is
regenerated in full on every `update()`. BOM text goes in column D of the
`IsoBOM` sheet, with a leading apostrophe (§9.2). Added rows go below the last
row.

**After the model changes,** update every iso page in the document, not only
the one the user mentioned. Then re-run §18. Balloons and dimensions follow
the model only when regenerated.

### 17.4 PCF in and out

- **Export for another program** (Isogen, CAESAR II):
  `pcf_export.export(objects, path)`. With several pipelines this writes
  `<path>_<pipeline>.pcf` files, and it returns the list written. The same
  grouping rules as §17.1 apply. `File > Export` uses the same code.
- **Draw a PCF from elsewhere:** `iso_page.pages_from_pcf(doc, path, opt)`
  gives one page per `PIPELINE-REFERENCE` in the file. The view keeps
  `IsoPcfPath`, and `update()` re-reads the file, so edits to the file flow
  through.

Write PCF files into `examples/<name>/`, or into `private/` when they come
from a client (§15). Never write them into the Quetzal installation.

---

## 18. Verify a construction iso numerically

The generator is well tested, but it draws exactly what it is given. The
checks below catch the wrong input:
- a part left out of the selection;
- a support that attached to the wrong line;
- a page drawn from a pipeline that has gone away.

`iso_page.update(view)` returns an `IsoSheet` holding what was drawn. Take
it, check it is not `None`, and print:

- **Warnings.** Every entry in `sheet.warnings`, plus those captured at
  creation (§17.2). Each needs an explanation at handover:
  - `symbols shrunk`, `drawing shrunk to N%`: crowded. Split the line
    (§17.1).
  - `line clashes could not be removed`: try another `IsoRotation`.
  - `closed loop(s) drawn out of true direction`: tell the user which loop.
  - `component N (KEYWORD): …`, or `… is not on any line of this pipeline`:
    a part was not drawn.
- **Every component drawn or explained.**
  `sheet.layout.graph.skipped` lists what was not drawn and why. It should be
  empty for a spool you built.
- **BOM against the model.** Count the drawn objects by `PType` and compare
  them with the BOM quantities. Total pipe is `sum(Pipe.Height)` against
  `BomItem.length` for the `PIPE` rows. A shortfall means an object never
  reached the pipeline.
- **Every BOM number ballooned.** `{n for n, _c, _a in sheet.balloons}`
  equals `{it.number for it in sheet.bom}`. A stud set shares its gasket's
  balloon, and still appears in that set.
- **Every dimension on a model work point, with the right value.** Each
  `Dimension` has node ids `a`, `b`, a true `value` in mm and its printed
  `text`. The nodes are in world mm (`sheet.layout.graph.nodes[i].pos`).
  Check three things:
  1. both nodes lie within 1 mm of a work point you compute from the model
     yourself;
  2. `value` equals the distance **along the run**, meaning the projection
     on the run direction. It is not the straight-line distance: across an
     eccentric reducer the two differ;
  3. `text` equals `iso_format.length_text(value, units)`.

```python
import math, pCmd
from iso import iso_format

def work_points(objs):
    """Ports, elbow/tee centres, and olet centres on the header centreline."""
    wps = []
    for o in objs:
        if not hasattr(o, "PType"):
            continue
        gp = o.getGlobalPlacement()
        to_world = gp.multiply(o.Placement.inverse())
        wps += [to_world.multVec(p) for p in (pCmd.portsPos(o) or [])]
        if o.PType in ("Elbow", "Tee", "SocketEll", "SocketTee"):
            wps.append(gp.Base)
        if o.PType == "Outlet":   # an olet's work point is on the run's centreline, not its port
            wps.append(gp.multVec(FreeCAD.Vector(0, 0, -float(getattr(o, "CarrierOD", 0)) / 2)))
    return wps

g = sheet.layout.graph
wps = work_points(spool_part.Group)
near = lambda p: min((FreeCAD.Vector(*p) - w).Length for w in wps)
for d in sheet.dimensions:
    a, b = FreeCAD.Vector(*g.nodes[d.a].pos), FreeCAD.Vector(*g.nodes[d.b].pos)
    dirs = [FreeCAD.Vector(*e.direction) for e in g.edges if d.a in (e.a, e.b)]
    along = max(abs((b - a).dot(u)) for u in dirs)
    ok = (abs(along - d.value) < 0.5 and near(a) < 1 and near(b) < 1
          and d.text == iso_format.length_text(d.value, view.IsoUnits))
    print("OK " if ok else "BAD", "%-12s %8.1f mm  model %8.1f mm" % (d.text, d.value, along))
```

On the launcher's barrel spool, all seven dimensions passed:
```
OK  3'-9 1/2"      1155.8 mm  model   1155.8 mm
OK  6"              152.0 mm  model    152.0 mm      (straight line 154.1: eccentric reducer)
```
Before olet centres were added to `work_points`, two anchors missed by 104
and 129 mm. That was the check's fault, not the drawing's. When a check
fails, find out which side is wrong before changing anything.

- **Title block.** Every field you were given is set **after** the last
  `update()`.
- **Say it is NTS.** There is no scale to check, and the reader should not
  scale the drawing.

Then **look at it.** Render the whole sheet with the snippet in §14 and read
the PNG. Look for:
- balloons or dimension text on top of one another;
- the notes running into the BOM (also a warning);
- a title cut short with "…".

The generator avoids collisions, but it is not a drafter. If the sheet reads
badly, try a different `IsoRotation` before anything else.

---

## 19. The loop, end to end

1. Confirm the session. Check the bridge's autosave preference, and set the
   active document (§2). Check that `import iso.iso_page` works (§17.0).
2. Decide what goes on each sheet (§17.1):
   - spool containers, top-level and named for people;
   - field material in or out;
   - one spool per sheet.
3. Set the options from the prompt: units, size names, sheet, rotation
   (§17.2).
4. Create the pages in one transaction, capturing warnings. Open **one**
   window.
5. Set the title-block fields you were given.
6. Verify (§18), then render and look.
7. Adjust by property and `update()` (§17.3). Restore the title block and
   re-verify after every regenerate.
8. Save, only if the document is yours (§2.3, §15).

When the model changes after handover, the loop starts again from step 6
for every iso page: `update()` each one, restore its title block, and
verify. Do not start from step 4, because recreating throws away the user's
edits.

Worked example: [`examples/construction_iso/make_construction_isos.py`](../../../examples/construction_iso/make_construction_isos.py).
It draws one construction iso per spool of the pig launcher, runs the §18
checks, and saves the result beside itself.
