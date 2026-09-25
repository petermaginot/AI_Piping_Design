# Spool prompt template

Copy this, fill in what you know, paste it as your prompt. Every section is
optional — anything you leave blank gets a documented default or one question
before the build starts (see the guide §11.2 / §11.3). This is a convenience,
not a required syntax; plain prose still works.

The point of the template is to make **omissions visible**. The four things prose
prompts most often leave out — the length convention, elbow turn directions, end
treatment, and where to save — are each their own heading below.

---

## Template

```markdown
## Line spec
Size:      <e.g. 8" (DN200)>
Schedule:  <e.g. Sch-STD>
Class:     <e.g. 600#>            # flanges and socket/threaded fittings

## Component chain            (in order, end A -> end B)
1. <Flange, WN RF, Sch-STD bore>
2. <Pipe, 36">
3. <Elbow, 90 LR>
4. <Pipe, 24">
5. <Flange, SO RF>

## Lengths
<Cut lengths | Work-point dims | Face-to-face> unless noted per item above.

## Orientation & routing
Start:  <first leg runs +Z from the origin>
Turns:  <elbow at item 3 turns to -X>

## Terminations
End A:  <bare raised face | gasket + bolts + blind | cap | continues off-drawing>
End B:  <...>

## Output
Document: <Spool_8in_SchSTD_600>
Save:     <yes -> beside the macro | no, leave unsaved>
```

---

## Filling in each section

### Line spec

Nominal size, schedule, and pressure class. Sizes are called out in inches; the
agent maps them to the DN labels the tables use (8" = DN200, 4" = DN100,
3" = DN80).

If the run changes size, give a **per-size** spec rather than one line:

```
Size/schedule:  10" Sch-STD run, 2" Sch-XS branches
Class:          300# throughout
```

For reducers spanning two schedules, the more conservative one governs — e.g. with
Sch-XS on 2" and Sch-STD on 3", specify the 2"×3" reducer as Sch-XS.

### Component chain

Numbered, in order, walking the spool from one end to the other. One component per
line, in the callout style of [spool_example_BOM.csv](../../../examples/iso_10in_300_branch_run/spool_example_BOM.csv):

```
Pipe, Sch-STD, 36"
Flange, WN RF, Sch-STD bore, 600#
Flange, SO RF, 600#
Elbow, 90 LR, Sch-STD
Tee, Sch-STD, equal
Reducer, concentric, 10" x 8"
Weldolet, Sch-XS, straight
Ball valve, flanged, 300#
```

For a branch, indent the branch chain under the item it hangs off, and say where
along the run it sits:

```
5. Weldolet, 2" Sch-XS, straight  -- 16" from the near end of item 4, pointing +Z
   5a. Flange, WN RF, Sch-XS bore, 300#
   5b. Ball valve, flanged, 300#
   5c. Flange, RF blind, 300#
```

Naming the flange **style** matters: `WN` (weld-neck, the default for a welded
spool), `SO` (slip-on), `SW` (socket-weld), `LJ` (lap-joint), `BL` (blind). "RF"
is the face and is implied by all the `-RF-` tables — it is not a style. A
"Sch-STD bore" weld-neck means the flange is bored to the pipe ID.

### Lengths

**State the convention once.** This is the highest-value line in the template.

- **Cut lengths** (the default assumption) — the number is the pipe's own length,
  as a fabricator would cut it.
- **Work-point dims** — the number runs to the centerline intersection of a
  fitting, so the elbow/tee take-out has to be subtracted out. This is what an
  isometric drawing uses (the guide §9.2).
- **Face-to-face / combined** — the number spans a flange face to something else
  and has a pipe embedded in it that must be calculated out.

Mixing conventions inside one spool is normal — flag the exceptions per item:

```
Lengths: cut lengths, except item 4 (48" is flange face to elbow work point).
```

### Orientation & routing

- **Start** — which way the first leg runs, and from where. Default: first pipe
  anchored at the origin running `+Z`, with everything else mated outward from it.
- **Turns** — for each elbow, the direction its outlet leg heads; for each tee, the
  direction the branch points. Use world axes (`+X`, `−X`, `+Y`, `−Y`, `+Z`, `−Z`).

Leaving turns unstated is fine for a simple two-leg spool: the result is a valid,
deterministic model, but the roll about the mating axis is *arbitrary* — the second
leg lands wherever the shortest-arc rotation puts it, not where you pictured it. Say
the direction whenever a later leg's orientation matters to you.

Elbows constrain what is possible: the two legs either side of a fitting must differ
by exactly its bend angle. A 90° elbow cannot join two legs 45° apart.

### Terminations

What happens at each open face:

- **bare** — the flange face is left as-is (default)
- **gasket + bolts + blind** — a full capped joint of the stated class
- **cap** — a butt-weld or socket cap
- **continues off-drawing** — an open pipe end, no fitting

### Output

Document name, whether to save an `.FCStd`, and where. Default is to build an
unsaved document; the reference macros save beside themselves.

---

## Worked example

### As originally asked (prose)

> A 8" 600# Sch-STD bore raised face weld neck flange attached to a 36" length of
> 8" Sch-STD pipe. At the far end of the pipe, attach a 8" Sch-STD LR elbow, then a
> 24" length of 8" Sch-STD pipe. At the far end of the 24" length of pipe, attach an
> 8" 600# slip on flange.

Complete on sizes, schedule, class, flange styles and lengths — and silent on four
things that had to be guessed or asked mid-build: whether 36"/24" were cut lengths,
which way the elbow turned, what happened at the two faces, and whether to save.

### The same request, filled in

```markdown
## Line spec
Size:      8" (DN200)
Schedule:  Sch-STD
Class:     600#

## Component chain
1. Flange, WN RF, Sch-STD bore
2. Pipe, 36"
3. Elbow, 90 LR
4. Pipe, 24"
5. Flange, SO RF

## Lengths
Cut lengths.

## Orientation & routing
Start:  item 2 runs +Z from the origin
Turns:  elbow at item 3 turns to -X

## Terminations
End A:  bare raised face
End B:  bare raised face

## Output
Document: Spool_8in_SchSTD_600
Save:     yes -> beside the macro
```

Result: [make_spool_8in_600_elbow.py](../../../examples/spool_8in_600_elbow/make_spool_8in_600_elbow.py). That macro
predates this template, so it takes the default roll rather than forcing the turn —
which happens to land leg 2 along −X. A prompt that states the turn gets it placed
explicitly instead (the guide §11.5).

### A second example — branches and capped ends

The spec behind [make_4in_300_inline_spool.py](../../../examples/spool_4in_300_inline/make_4in_300_inline_spool.py),
showing a branch and non-bare terminations:

```markdown
## Line spec
Size:      4" (DN100)
Schedule:  Sch-40  (fittings from the Sch-STD tables)
Class:     300#

## Component chain
1. Flange, WN RF, Sch-40 bore
2. Pipe, 36"
   2a. Sockolet, 1" 3000#, straight -- 16" from the near end of item 2, clocked 90 deg
3. Elbow, 90 LR, Sch-STD
4. Pipe, 72"
5. Flange, SO RF

## Lengths
Cut lengths. Branch location is measured from the near end of item 2.

## Orientation & routing
Start:  item 2 runs +Z from the origin
Turns:  elbow direction unspecified -- any valid roll is fine

## Terminations
End A:  gasket + bolts + blind, 300#
End B:  gasket + bolts + blind, 300#

## Output
Document: Spool_4in_Sch40_300
Save:     yes -> beside the macro
```

Two things this example pins down that prose tends to blur: butt-weld fittings are
tabulated as Sch-STD/XS/XXS only, so a Sch-40 line uses the **Sch-STD** elbow (the
walls are identical up to DN250); and the sockolet's `90 deg` is a *circumferential
clock angle* around the pipe, not a branch angle.

---

## What the agent does with a blank field

It will not invent dimensions. Anything omitted is either defaulted (and named in
the build report) or raised in a single batch of questions before any code is
written. If a size, schedule, class or component family has no table in `tablez/`,
it says so rather than substituting silently — see the guide §7 and §11.
