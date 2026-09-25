---
name: quetzal-piping
description: Build, modify or correct piping (spools, runs, branch connections, pig launchers and receivers) in the user's live FreeCAD session with the Quetzal workbench, over MCP. Works from a text prompt, a hand-drawn isometric or pencil sketch, an existing drawing, or annotated field photographs. Use whenever the user asks to model piping in FreeCAD or Quetzal, or to write a Quetzal macro.
---

# AI-assisted piping design with Quetzal

Directions for an AI agent that builds piping designs (spools, runs, assemblies)
with the **Quetzal** workbench by driving the user's **live FreeCAD session over
the MCP server** ([blwfish/freecad-mcp](https://github.com/blwfish/freecad-mcp)).
You build directly in their running FreeCAD via `execute_python` and verify the
result numerically in the same session before saying you are done. A `.py` macro
is a deliverable only when the user asks for one (§7.1).

These rules separate a model that is right from one that silently produces
wrong geometry or crashes.

## Read before you build

This skill is split across several files. Section numbers (§) are the same in
every file, so a cross-reference such as "§9.2.2" means the file listed for §9
below. **Read every file marked "every build" before you send any build code**,
and read the file for your source before you interpret that source. §9.2–§9.7
(work points, the short-pipe rule, orientation and roll, solving constraints
through the chain) apply to every source, not only to isometrics.

| § | Contents | File | Read |
|---|---|---|---|
| 1, 2, 7, 8, 10 | Golden rules, session preamble, workflow, sanity checks, build-and-verify loop | this file | every build |
| 3–6 | `pCmd` maker catalog, branch outlets, valves, socket-weld, reducers, pipe supports (beam, post, U-bolt, or plain Part solids), flanges, ports and `alignTwoPorts`, `tablez/` | [references/components.md](references/components.md) | every build |
| 9 | Reading an isometric; dimensions to work points; orientation and roll; structuring the build; constraints through the chain | [references/layout.md](references/layout.md) | every build |
| 11 | Building from a text prompt | [references/text-prompt.md](references/text-prompt.md) | source is prose |
| 12 | Building from a field photograph | [references/photograph.md](references/photograph.md) | source is a photo |
| 13 | Worked assembly: a pig launcher | [references/pig-launcher.md](references/pig-launcher.md), with [pig_trap_guidelines.md](references/pig_trap_guidelines.md) and [Trap_diagram.svg](references/Trap_diagram.svg) | pig trap, launcher or receiver |
| — | Fill-in spec template to offer when a prompt is under-specified | [references/spool_prompt_template.md](references/spool_prompt_template.md) | as needed |

Outside this folder, at the repository root: `quetzal_env.py` (Quetzal path
resolution and `tablez/` reads for macro files, §7.1) and `examples/`.
`examples/spool_8in_600_elbow/` is the reference for the shape a macro should take.

---

## 1. Golden rules (read first)

1. **You build in the user's live GUI session, over MCP.** Quetzal's `execute()`
   methods set `fp.ViewObject.Deviation`, so `Pipe`/`Flange`/etc. only build
   geometry when a GUI ViewObject exists — headless `freecadcmd` fails with
   `'NoneType' object has no attribute 'Deviation'`. The MCP target *is* a GUI
   session, so this requirement is satisfied for free and needs no workaround.
   Build with `execute_python`, verify in the same session (§10), and show the
   user the finished model rather than instructions for producing it.
   **Confirm the session before you build** — `check_freecad_connection`,
   check that the Quetzal workbench is loaded, and check whether the bridge
   will autosave the user's files (§2, §2.1).
2. **Units are millimetres.** Convert imperial input: `inches * 25.4`.
   E.g. a 24" length → `609.6`.
3. **Nominal sizes are DN (metric bore) labels**, even for imperial NPS.
   6" = `DN150`, 2" = `DN50`, 1" = `DN25`, etc. The CSV `PSize` column is the key.
4. **Be data-driven, not hardcoded.** Read dimensions live from the `tablez/`
   CSV files rather than embedding numbers. This survives table edits and avoids
   transcription errors.
5. **Reuse the maker functions in `pCmd.py`.** Never reimplement geometry.
   Build objects with `pCmd.makePipe`, `pCmd.makeFlange`, `pCmd.makeElbow`, …
   and position them with `pCmd.alignTwoPorts`.
6. **Set `PRating` after creating pipes/elbows/caps/tees/reducts** — the maker
   docstrings note "property PRating must be defined afterwards" (the maker's
   `rating` arg drives geometry lookup but the property isn't always persisted).
7. **A millimetre of disagreement is normal — absorb it and say so.** Drafting
   packages round fitting take-outs, and a drawing dimension can sit ±1 mm off
   the `tablez/` value. Build to the tables, let the difference land in a derived
   pipe length, and **report every adjustment you made** rather than silently
   forcing the drawing number. See the short-pipe rule in §9.2.2. But a
   *hundred* millimetres of disagreement is not rounding — before you pad a
   dimension to make room, check whether the joint should have no pipe in it at
   all (§9.7.1).
8. **A stated relationship is a constraint, not a dimension.** "Aligned in X",
   "directly connected", "6 inches from the weld" must be *solved* through the
   port chain, never approximated by a tuned constant — and then **verified
   numerically out of the built document** before handover (§9.7, §8).
9. **Object properties are `Quantity`, not `float`.** `flange.T1 + flange.trf`
   raises `Quantity::operator +(): Unit mismatch in plus operation`. Coerce with
   `.Value` before any arithmetic — take-out math touches these constantly, so
   keep a `val()` helper in the session (§2) and route every property read
   through it. This is the single most common runtime error in a build.
10. **You are working in a session that persists.** Names you define in one
    `execute_python` call are still there in the next, and so is the document you
    just modified. That is what makes the incremental loop in §10 possible, and
    it is also how a stale helper from an earlier build silently poisons a later
    one (§2.2).

---

## 2. Session preamble (always start here)

Quetzal is already imported in a session whose workbench is active, so there is
no path-hunting to do: **ask the running `pCmd` where it lives.** Send this once
per session, before any build code.

```python
import os, csv, FreeCAD, FreeCADGui, pCmd, pFeatures
from FreeCAD import Vector

# pCmd is imported by the workbench itself; its __file__ is the authoritative
# install path.  Quetzal puts a "/./" in sys.path, so normalise it out.
QDIR   = os.path.dirname(pCmd.__file__.replace(os.sep + "." + os.sep, os.sep))
TABLEZ = os.path.join(QDIR, "tablez")

def val(x):
    """Quantity -> float.  Golden Rule 9: never do arithmetic without this."""
    try:
        return float(x.Value)
    except AttributeError:
        return float(x)

def row(csv_name, psize):
    """Fetch the row for `psize` from tablez/<csv_name> (';'-delimited, BOM)."""
    with open(os.path.join(TABLEZ, csv_name), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            if r.get("PSize", "").strip() == psize:
                return r
    raise RuntimeError("No row for PSize=%s in %s" % (psize, csv_name))

def f(r, key, default=0.0):
    """Column by NAME with a default -- column sets differ by family (§4, §6)."""
    v = r.get(key, "")
    return float(v) if str(v).strip() not in ("", "None") else default
```

`pCmd.readTable("Pipe_SCH-STD.csv")` returns the whole file as `list[dict]` and
resolves `tablez/` for you — use it when you want to scan a table rather than
pull one row.

Verify the session before building:

```python
print(FreeCAD.Version()[:3], "GUI:", FreeCAD.GuiUp)
print("workbench:", FreeCADGui.activeWorkbench().name())   # want QuetzalWorkbench
print("QDIR:", QDIR)
print("docs:", {n: d.FileName for n, d in FreeCAD.listDocuments().items()})
print("bridge autosave:", FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/AICopilot"
).GetBool("AutoSaveBeforeRiskyOp", True))                  # see §2.1
```

### 2.1 Choose the target document deliberately

You are in the user's session, and it may already hold work. **Never assume the
active document is yours to build in.** Check `FreeCAD.ActiveDocument` and its
object count first, then either build into an empty scratch document or create
your own with `FreeCAD.newDocument("Spool")`. Say which you chose.

Wrap the build in `doc.openTransaction("...")` / `doc.commitTransaction()` so the
whole thing collapses to a **single undo** for the user. This is the courtesy
that makes building in someone's live session acceptable rather than intrusive.
Do not `saveAs` unless the user asked for a file, and never write an `.FCStd`
into the installed `Mod/Quetzal/` directory.

**The MCP bridge saves for you unless it is told not to.** Before running your
code, every `execute_python` call (and every `part_operations` boolean) saves the
**active** document, if it has a file path. It writes the state left by the
*previous* call, to the path it was opened from. A new, unsaved document is
never touched. The AICopilot preference `AutoSaveBeforeRiskyOp` controls this,
and it defaults to on. So:

- Read it in the preamble (§2). If it is on and any open document has a
  `FileName`, **stop and tell the user** before building. Offer to switch it off
  (`FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/AICopilot")
  .SetBool("AutoSaveBeforeRiskyOp", False)`), and do it only if they agree.
  Mention the setting again at handover.
- Never make a user's saved file the active document just to read from it.
  `FreeCAD.getDocument(name)` gives you the object without activating it.
- Once you `saveAs` a document into the repo, every later call rewrites it while
  it stays active. Run post-save checks against a scratch document, or accept
  the resulting git diff.
- **Create your build document with `view_control` `create_document` *before*
  the first `execute_python`.** The new, unsaved document becomes the active
  one, so the autosave that fires on that first call has nothing to write, even
  when the user has a saved model open. This matters most in a correction round
  after the user has saved your last build into the repo: that file is still
  open and probably still active. Rebuild into a fresh document created this
  way, and the user's file is never rewritten mid-build.
- **When you save a build, make `saveAs` the last call.** From then on, every
  call re-saves the file first. Take screenshots and run checks before the
  save, not after. Save a correction round beside the user's file under a new
  name, such as `..._rev1.FCStd`, unless they asked you to overwrite it. Their
  copy may be untracked, with nothing in git to recover it from.

### 2.2 The session namespace persists — and that cuts both ways

Names defined in one `execute_python` call are visible in every later call, which
is what lets you build incrementally and re-query the model afterwards (§10).
Two consequences:

- **`__name__` is `"builtins"`, not `"__main__"`.** An `if __name__ ==
  "__main__":` guard carried over from the old macro skeleton will **silently
  never fire** — your build code appears to run and does nothing. Do not use an
  entry guard in code sent over MCP. (It is still correct in a `.py` file written
  out under §7.1, where the file *is* run as `__main__`.)
- **Stale definitions leak between builds.** A `DIMENSIONS` dict or helper left
  over from an earlier job is still bound, so a later build that forgets to
  redefine one silently uses the old value. Redefine every name your build
  depends on in the same call sequence that uses it, and prefer explicit
  re-assignment over relying on what is already there.

### 2.3 The installed workbench and the git checkout are two different copies

MCP executes inside the **installed** workbench
(`getUserAppDataDir()/Mod/Quetzal`), so `QDIR` above always points there — while
the repo you are reading and editing is a separate checkout. A table you can see
in the repo's `tablez/` may simply not exist at run time; a brand-new CSV, still
untracked in `git status`, is the classic case, and it fails with a bare
`FileNotFoundError` naming the *AppData* path. **That path in the error is the
diagnosis, not a bug.** Tell the user which file to copy into the installed
`Mod/Quetzal/tablez/` — don't work around it by reading the checkout's copy,
which would build from a table the workbench itself cannot see.

The same split applies to code: editing `pCmd.py` in the repo does not affect the
running session. If the user changes workbench source, they must sync it across
and then reload it (`importlib.reload(pCmd)`, plus any module it imports that
also changed, or restart FreeCAD) before it takes effect. The MCP
`reload_modules` tool is **not** this. It reloads only the MCP addon's own
handlers, and in doing so it empties the `execute_python` namespace, so re-send
the §2 preamble after it.

---

## 7. Workflow for the agent

1. **Parse the prompt** into components, sizes, schedule/class, lengths,
   orientations, and connections. Convert imperial → mm; map NPS → DN.
   *(Working from a drawing rather than prose? Do §9.1 first — read it at
   magnification and reconcile its redundant data — before anything below.
   Working from prose? See §11 for what a text prompt must pin down, what to ask
   about, and what to default. Working from a field photograph? See §12 — decode
   the annotation file first, and note that photo-derived stations carry an error
   bar an iso dimension does not.)*
2. **Pick the flange type deliberately** (WN for welded spools). If the prompt is
   ambiguous on something that changes geometry (flange type, concentric vs
   eccentric reducer, whether to save a file), **ask the user** before building.
3. **Confirm the session and the tables.** Send the §2 preamble; check the
   workbench is loaded and pick the target document (§2.1). Confirm every
   requested size/rating resolves to a real CSV file with a `PSize` row present.
   If a size/rating has no table, say so — don't invent dimensions.
4. **Build incrementally over `execute_python`** (§10.1): read rows → create with
   the makers → `recompute` → `alignTwoPorts` → `recompute`, inside one
   transaction. Keep each call small enough that a traceback names the step that
   broke.
5. **Verify numerically in the same session** (§10.2) — port closures, take-out
   reconciliation, `geometric_verification`, `spatial_query`. This is not
   optional and it is not a visual check.
6. **Show the user the model**: a screenshot (§10.3) plus the report (§9.6 /
   §11.6). Because you built it live, they can rotate the real thing while
   reading your numbers.
7. **Write a `.py` file only if asked** (§7.1), and say plainly whether anything
   was saved to disk.

### 7.1 When the user wants a macro file as well

Building over MCP does not forbid producing a `.py` — it changes *when* you write
it. Build and verify live first, then write out the code you actually ran, so the
file records something proven rather than a hopeful draft.

A file meant to be re-run needs three things the MCP calls did not: path
resolution to find Quetzal (there is no already-imported `pCmd` to interrogate
when it runs from **Macro → Execute**), a `build()` entry point, and an
`if __name__ == "__main__":` guard — which *is* correct here, unlike in code
sent over MCP (§2.2).

Do not hand-roll the path resolution: use `quetzal_env.py` at the root of this
repo. Every macro opens with the same preamble, which walks up from `__file__`
to find `quetzal_env`, then asks it for `pCmd` and the `tablez/` rows:

```python
_ROOT = _repo_root()            # walks up to the directory holding quetzal_env.py
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import quetzal_env as qenv

pCmd = qenv.import_pcmd()
_read_row = qenv.read_row       # tablez/<csv> row for a PSize
_f = qenv.f                     # float from a row, by column name
```

Write the file into `examples/<something>/`, never into the installed
`Mod/Quetzal/` — that is a separate checkout and not yours to write to. Anything
the macro saves (a `.FCStd`) goes **beside the macro**, in its own example
folder, for the same reason. Worked examples already follow this shape, e.g.
`examples/spool_8in_600_elbow/make_spool_8in_600_elbow.py`.

---

## 8. Sanity checks before handing over

- Lengths in mm; a 24" pipe → `Height == 609.6`.
- Pipe `ID == OD - 2*thk`; WN flange `d == OD - 2*thk`.
- Flange `FlangeType`, `FClass`, and `PRating` are what you intended.
- Overall assembly length ≈ pipe length + sum of the parts added at each end
  (e.g. a flanged spool ≈ `L + 2*(T1 + trf)` for WN flanges).
- The build ran inside one transaction (§2.1), so the user can undo it in one
  step, and nothing was written to disk that they did not ask for.
- **You have actually built it in the live session and verified it there** (§10).
  Every pipe length positive, no traceback, every port closure at 0.000 mm, and
  the printed checks reconciled. "It should work" is not a handover — and neither
  is "it built without errors".
- **Every constraint the user stated is verified numerically, not visually.** A
  clean build only proves the code *ran*. "Aligned in X", "directly
  connected", "6 inches from the weld", "centred on the tee" are all assertions
  you can measure out of the built document — so measure them and quote the
  number. Query the finished doc rather than trusting the code you just wrote:

  ```python
  doc = FreeCAD.ActiveDocument            # the doc you just built, still live
  a, b = [o for o in doc.Objects if " Valve DN200" in o.Label]
  print("dX", abs(a.Placement.Base.x - b.Placement.Base.x))     # want 0.000000
  print("seated", (world(tee, 0) - world(flange, 1)).Length)    # want 0.000000
  ```

  Over MCP this is a *separate* `execute_python` call against the document that
  is already built (§2.2) — which is the point: you are interrogating the model
  the user is looking at, not re-running your own build code and trusting it to
  produce the same thing twice.

  Reporting `dX = 0.000000 mm` and `gap = 0.000000000 mm` is a different claim
  from "I made them aligned", and it is the one worth making. It also catches the
  case where you satisfied the letter of a correction while breaking a
  neighbouring one.

---

## 10. Build and verify over MCP

This replaces the old headless `ViewObject`-shim smoke test, which existed only
because there was no live GUI session to execute into. There is one now, so the
shim is gone: you build in the real session and verify against the real document.

### 10.1 Build incrementally, in small calls

Send the §2 preamble, then build in a few `execute_python` calls rather than one
large one. A traceback then names the step that broke instead of the whole build,
and the persistent namespace (§2.2) means each call still sees the last one's
objects.

```python
doc.openTransaction("Build spool")
fA = pCmd.makeFlange(fprops, Vector(0,0,0), Vector(0,0,1),
                     doOffset=True, rating=SCHED, fclass=FCLASS)
p1 = pCmd.makePipe(SCHED, [DN, OD, thk, L1]); p1.PRating = SCHED
doc.recompute()                                   # ports don't exist until execute()
pCmd.alignTwoPorts(p1, 0, fA, 1)                  # pipe near end -> flange weld end
doc.recompute()
doc.commitTransaction()
```

Set `.Label` on every object as you go (§9.6) — labels are how both you and the
user address parts in later calls.

### 10.2 Verify numerically — this is the part that matters

A build that raised no exception has proved almost nothing. Query the finished
document in a **separate call** and print numbers you can quote:

```python
def wpos(o, i): return o.Placement.multVec(o.Ports[i])
def wdir(o, i): return o.Placement.Rotation.multVec(o.PortDirections[i]).normalize()

for name, a, ia, b, ib in joints:
    gap = (wpos(a, ia) - wpos(b, ib)).Length
    dot = wdir(a, ia).dot(wdir(b, ib))
    print("%-24s gap=%.6f mm  dot=%+.6f" % (name, gap, dot))   # want 0.000000, -1.000000
```

Every joint must close at **gap ≈ 0 and dot ≈ −1** (anti-parallel = face to
face). A non-zero gap means a missed `recompute()` or a wrong port index; a dot
near +1 means you mated two ports that both point the same way.

Then reconcile the **take-out chain** — sum the catalogue take-outs by hand and
compare against the built extents, remembering `val()` (Golden Rule 9):

```python
flg  = val(fA.T1) + val(fA.trf)        # WN flange: raised face -> weld end
vert = flg + L1 + val(el.BendRadius)   # elbow take-out for a 90 is BR
print("expect %.2f, built %.3f, delta %.4f" % (vert, dz, abs(dz - vert)))
```

Four MCP tools do the rest without any code of yours:

| Tool | Use |
|---|---|
| `geometric_verification` `verify_no_self_intersection` | Per-object OCCT validity |
| `spatial_query` `batch_interference` | All pairs at once |
| `spatial_query` `clearance` / `alignment_check` | A stated gap or alignment (§9.7) |
| `measurement_operations` `find_root_cause` | A check failed on something built from several inputs (an `App::Part`, a compound): names the part that introduced the defect, not the container that inherited it |

**Read `batch_interference` correctly.** Welded neighbours *touch*, so a
correctly built spool reports one "collision" per joint, each with **zero overlap
volume** ("sub-tolerance contact"). That is the pass signature, not a failure.
A real interference is a non-trivial common volume, and a pair that is *not*
adjacent in your chain showing contact is the genuine warning.

A few adjacent pairs show **real volume that is still not a placement error**.
They come from the tables and the makers, and every joint in the model shows
the same number:

| Pair | Typical overlap | Cause |
|---|---|---|
| `Bolts_Nuts` ↔ each of its two flanges (or valve ends) | identical on both sides, e.g. 48 230 mm³ at DN200 600# | The nuts sit ~3.85 mm into the flange back faces. The bolt holes *are* cut; the stud set is just short. Equal volume on both sides means it is centred correctly |
| `Bolts_Nuts` ↔ `Gasket` | a few mm³ | Centring ring OD (`CROD`) is ~0.1 mm past the inner edge of the studs |
| SW pipe ↔ socket fitting | < 1 mm³ | Pipe-table OD 33.401 vs fitting-table socket 33.4 |
| `U-Bolt` ↔ support `Beam` | `2·π·(d/2)²·tf`, e.g. 1429.4 mm³ at DN50 on a W6x15 | The legs pass through the top flange, which has no bolt holes cut. A larger value means the legs are in the web (§3.5) |

Recognise them by that symmetry and repetition. Mention them once in the
report as table artefacts, and move on. Anything that is **not** one of these
(a different volume, a non-adjacent pair, one side of a joint only) is a real
clash and needs finding. `common().BoundBox` of the pair says where. A
valve's gearbox against a pipe nearby is the usual culprit (§3.2.1).

### 10.3 Show it, then leave the session clean

`view_control` `fit_all` + `set_view isometric`, then capture. **Use `saveImage`
via `execute_python`, not the `screenshot` operation:**

```python
v = FreeCADGui.ActiveDocument.ActiveView
v.viewIsometric(); v.fitAll()
v.saveImage(path, 1100, 800, "White")
```

`view_control screenshot` base64-encodes the PNG into the socket frame, against a
50 KB `MAX_MESSAGE_SIZE`. Anything past roughly 800×600 — even on a five-object
scene — exceeds it, and the handler then *discards the response*, so the call
hangs for the full 120 s and returns a timeout while the real message
("Refusing to send oversized message … would desync framing") appears only in the
FreeCAD console. It also ignores the `filename` argument entirely, writing to a
temp file it deletes. `saveImage` has no size ceiling, honours the path, takes
well under a second, and lets you set the background.

Finally, respect the session you borrowed: the build is one undo (§2.1), nothing
is saved unless asked (which, with the bridge's autosave on, means no saved
document was ever active: §2.1), and no `.FCStd` is written into `Mod/Quetzal/`.
