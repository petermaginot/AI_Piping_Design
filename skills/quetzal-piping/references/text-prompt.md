# Building from a text prompt (§11)

Part of the `quetzal-piping` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 11. Building from a text prompt

The counterpart to §9. There the geometry is *on the sheet* and the work is reading
it; here the geometry is only as complete as the sentence, and the work is noticing
what the sentence left out. Everything in §§1–8 still applies.

A prompt can be complete on sizes, schedule, class, flange styles and lengths and
still be silent on four things that change the model. [`spool_prompt_template.md`](spool_prompt_template.md)
is a fill-in template that surfaces them; point the user at it when a prompt turns
out to be under-specified, but never require it — plain prose is the normal input.

### 11.1 What a text prompt must pin down

| Item | Failure mode if missing |
|---|---|
| **Line spec** — size, schedule, class | Wrong table, or an invented dimension |
| **Component chain**, in order end-to-end | Wrong topology; no way to build the port chain |
| **Length convention** — cut vs work-point vs face-to-face | *Silent*: the model builds, every part is right, and the run is long by one take-out per fitting |
| **Orientation & turns** | The spool is geometrically valid but points somewhere the user didn't picture (§11.5) |
| **Terminations & output** | Missing caps/gaskets; a file written where it wasn't wanted |

The length convention is the dangerous one because nothing downstream catches it.
Everything else shows up as a traceback, a missing table, or something visibly odd
in the model.

### 11.2 Ask about these; don't guess

Batch them into **one** round of questions before writing any code — not a running
interrogation, and not one question per turn. Ask only when the answer changes the
geometry or the deliverable:

- **Length convention**, whenever a dimension could plausibly run to a fitting
  centerline rather than a pipe end. If every number is stated as "a 36" length of
  pipe" it is a cut length and needs no question; if it is "36" to the elbow", ask.
- **Flange style**, only when genuinely unclear. "Weld neck", "slip on", "blind" are
  answers; a bare "flange" on a welded spool means `WN` (§4) — take it and say so.
- **Turn direction** for an elbow or tee whose downstream leg has to point a
  particular way (§11.5).
- **End treatment** — bare faces vs gasket + bolts + blind, when the prompt stops at
  a flange without saying.
- **Support type**, when the prompt mentions supports without describing them.
  A post-and-cap support with a U-bolt maps onto the Quetzal makers. Shoes,
  guides, hangers and brackets are better as plain `Part` solids (§3.5).
- **Save target** — whether to write an `.FCStd`, and where. Ask too whether they
  want a re-runnable `.py` alongside the live model (§7.1); the build itself is
  delivered in their session either way, so this is about what they keep, not how
  they get it.

Everything else: pick the obvious reading, build it, and name the choice in the
report.

**A removal request removes exactly what it names.** "Remove the pipe and cap
on the vent and leave it open" meant the *downstream* nipple and cap. The
valve and the nipple feeding it were to stay, leaving the valve's outlet open.
Taking out every part between the named ones, because "open" seemed to call
for it, cost a correction round. When the parts named are not contiguous, or
the result is ambiguous, remove only what was named and ask about the rest.
"Leave it open" describes the end state of what's left, not a licence to
remove more.

### 11.3 Default these silently, and state them in the report

- **Anchor the first pipe at the origin and never move it.** `alignTwoPorts` only
  moves its first argument, so mating everything outward from a fixed anchor keeps
  the whole spool in a predictable frame.
- **First leg runs `+Z`** unless the prompt says otherwise.
- **`doOffset=True`** on every flange that will be positioned with `alignTwoPorts`
  (§4), and `PRating` set after creation on pipes/elbows/caps/tees/reducers
  (Golden Rule 6).
- **Imperial → mm at ×25.4**, with the inch value kept in the label and the report.
- **Every object gets a `.Label`** naming size, spec and role — the user selects
  parts by label when they want one changed.
- **Fittings come from the `SCH-STD`/`XS`/`XXS` tables** for a Sch-40/80 line (§6),
  because no butt-weld fitting tables exist for the numbered schedules.

### 11.4 The port-chain build pattern

A text prompt almost always describes a **linear chain**, which is simpler than §9's
work-point skeleton: there are no work points to solve, because each part's cut
length is given. Create a part, recompute, mate its inlet to the previous part's
open outlet, repeat.

```python
pipe1 = pCmd.makePipe(SCHED, p1_props); pipe1.PRating = SCHED
doc.recompute()                              # anchor: never moved

wn = pCmd.makeFlange(_wn_flange_props(OD, thk), doOffset=True,
                     rating=SCHED, fclass=FCLASS)
doc.recompute()
pCmd.alignTwoPorts(wn, 1, pipe1, 0)          # flange weld end -> pipe near end

elbow = pCmd.makeElbow(_elbow_props(), rating=SCHED); elbow.PRating = SCHED
doc.recompute()
pCmd.alignTwoPorts(elbow, 0, pipe1, 1)       # elbow inlet -> pipe far end

pipe2 = pCmd.makePipe(SCHED, p2_props); pipe2.PRating = SCHED
doc.recompute()
pCmd.alignTwoPorts(pipe2, 0, elbow, 1)       # pipe near end -> elbow outlet

so = pCmd.makeFlange(_so_flange_props(), doOffset=True,
                     rating=NORATE, fclass=FCLASS)
doc.recompute()
pCmd.alignTwoPorts(so, 1, pipe2, 1)
```

The port indices are the §5 conventions, and they are the thing to get right:
**flanges mate via port 1** (the weld/pipe end, leaving the raised face open at port
0); **pipes** run port 0 → port 1; **elbows** take the inlet at port **0** and
continue from port **1**. `doc.recompute()` before every `alignTwoPorts` — the port
lists don't exist until `execute()` has run.

Full worked example: `examples/spool_8in_600_elbow/make_spool_8in_600_elbow.py`.

### 11.5 Turn direction is the thing prose under-specifies

`alignTwoPorts` fixes position and makes the two ports anti-parallel, but leaves the
**roll about that axis free** (§9.3). For an in-line part that is irrelevant. For an
elbow it decides which way the whole downstream leg points.

The result is *deterministic* but not *chosen*: the shortest-arc rotation lands the
outlet somewhere valid, and rebuilding reproduces it, but it is not
information the prompt supplied. For a two-leg spool with no stated direction that
is fine — build it, and say in the report which way the second leg actually went
("leg 2 runs −X; direction was not specified").

When the user *does* name a direction, place the elbow explicitly instead of letting
`alignTwoPorts` choose — anchor its **inlet port** at the mate and aim the outlet
with the §9.3 `rot_two` helper:

```python
R = rot_two(d0, d1, inlet_dir, outlet_dir)
elbow.Placement = FreeCAD.Placement(matePortWorld - R.multVec(elbow.Ports[0]), R)
```

Check feasibility first — the legs either side of a fitting must differ by exactly
its bend angle, so a 90° elbow cannot join two legs 45° apart:

```python
assert abs(inlet_dir.getAngle(outlet_dir) - math.radians(180 - BA)) < 1e-6
```

### 11.6 What the report must contain

Lighter than §9.6 — there are no drawing closures to reconcile, but the user still
needs to check the build against what they asked for:

- Every component with its label, spec and the CSV row it came from.
- Every pipe cut length in **mm and inches**, so it can be read against the prompt.
- Take-outs actually read from `tablez/` (elbow `BendRadius`, flange `T1`/`trf`) —
  never hardcoded numbers repeated in prose.
- Per-leg extents and the §8 sanity checks (`Height`, WN bore `== OD − 2·thk`,
  `FlangeType`, `FClass`).
- **Every default applied under §11.3**, especially the starting axis and any turn
  direction that was not specified.
- **The §10.2 verification numbers** — port closures and the take-out
  reconciliation — quoted, not summarised as "verified".
- The document you built into, and the save path, or a note that nothing was
  written to disk. Include the state of the bridge's `AutoSaveBeforeRiskyOp`
  preference (§2.1), and any file it saved.
