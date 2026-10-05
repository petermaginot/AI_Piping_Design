# Worked assembly: a pig receiver (§13.2)

Part of the `quetzal-piping` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

Companion to [pig-launcher.md](pig-launcher.md) (§13, §13.1). Read that file
first. Everything there about loops, eccentric reducers, actuator roll, marks
and the header survey applies here. This file covers what is different at the
receiving end.

---

## 13.2 Adding a receiver barrel between existing valves

The case this section was written from was an NPS 8 × NPS 12, 600#
receiver, built as the companion to an 8x12 launcher grouped into spools.
The user's model already held the header and both valves:
- an incoming pipeline into an equal 8" tie-in tee;
- the trap valve on the tee's run;
- a bypass leg to a junction tee, carrying the kicker valve, and on to the
  station.

The task was the barrel between the two valve faces. The user later added a
bypass valve, a spool grouping, and a construction iso of the barrel spool.
The build went into a revised copy, and the original file was left
untouched beside it (§2.1).

### Read the header first, offline

Read the `.FCStd` zip (§2.1) before any `execute_python`. The two open valve
faces fixed almost everything:

| Read | Value | What it fixes |
|---|---|---|
| Trap valve open face | (−1769.85, 0, 0), facing −X | Barrel axis along −X at y = z = 0 |
| Kicker valve open face | (−5080.40, +1329.35, 0), facing −Y | Kicker tee centre at x = −5080.40, and the branch length |

So the chain from the trap valve face to the kicker tee centre is a **fixed
total**: gasket, WN, minor pipe, reducer `H`, major pipe and tee `C` sum to
3310.55 mm. Only the split between the minor and major pipes is free. A
launcher has no such constraint, because its kicker connects through a loop
you design. On a receiver added between existing valves, say up front that the
valve positions set the barrel length. Then ask how the pig length is
measured, because that decides the split.

### Ask these in the first round (beyond §13 and §13.1)

- **How the pig length is measured on the minor barrel.** The user chose
  trap valve **face** → reducer **small-end weld** ≥ the pig length (96"). That
  is the conservative reading of the guideline: the pig's cups lose their seal
  at the reducer, so the whole pig must be past the valve before that. Minor
  pipe = `PIG_LEN − SEthk − (T1 + trf)` = 2294.15 mm. The alternative, minor
  pipe cut length ≥ the pig length, left only 10.7" of major pipe ahead of the
  tee.
- **Vent and drain construction**, when the model already has a vent or drain.
  Match what is in the model, not the launcher. Here the existing vent was a
  1" threadolet, a 6" XS nipple, a threaded ball valve and a hex plug, so all
  three new vents copied it.
- **Where to build.** The user's file was untracked in git and the bridge
  autosaves. Copy it to `_rev1` and open the copy (§2.1).

### Receiver design rules that differ from the launcher

- **Major barrel length:** the user's rule was "at least a typical mandrel
  pig, about 2 × the minor NPS" (16"). Two readings both need checking:
  - the major pipe ahead of the kicker tee: 415.15 mm against 406.4 mm;
  - the room past the kicker opening, from the downstream bore edge of the
    tee branch to the closure face: 661.7 mm.

  A receiver's pig drifts past the kicker toward the closure, so the second
  matters. Report both, and also the reducer large-end weld → closure face
  figure (1483.2 mm).
- **Kicker branch:** use a full-size tee plus an eccentric reducer, flat on
  bottom, welded straight onto the branch. The barrel reducer (FOB) lifts the
  major centreline by `e = (OD − OD2)/2`. A second reducer of the **same row**,
  also FOB on the branch, drops it by the same `e`, so the small end lands at
  the kicker valve's elevation exactly. That replaces the launcher's tilted
  branch (§9.3.1), and needs no slope. Place it with local `+X → −Z` and
  local `Z` along the branch. Assert `small_end.z == valve_face.z` before you
  derive the lead pipe by spanning to the WN weld.
- **Put the kicker lead pipe on the small side** (8", between the reducer
  and the WN), not between the tee and the reducer. It costs two 8" welds
  instead of two 12" welds.
- **Pig bars are required** in the kicker branch of a receiver. The pig
  passes the opening. They are not modelled, so say so (§13.1 has the launcher
  case, where they are not needed).
- **No vents or drains on the kicker tee.** The user stated it. Expect it on
  any trap.

### Olet stations from a weld-spacing rule

The user's rule was weld → olet **edge** ≥ ½ the **run** NPS: 4" on the 8"
minor barrel, 6" on the 12" major barrel. They gave it for the TOR; apply it
to every olet and say so. Station = gap + `B/2` from the weld (§3.1).

| Item | Pipe | Clock | Station |
|---|---|---|---|
| 1" vent, "as close to the trap valve as possible" | minor | top | 4" + B/2 from the trap-side WN weld |
| 2" drain near the trap valve | minor | bottom | 4" + B/2 from the same weld |
| 2" TOR, "as close to the reducer as practical" | minor | top | 4" + B/2 from the reducer weld |
| third 1" vent, "anywhere" | major, ahead of the tee | top | centred |
| 1" vent "as close to the closure as possible" | closure pup | top | 6" + B/2 from the closure WN weld |
| 2" drain near the closure | closure pup | bottom | 6" + B/2 from the same weld |

- **The closure pup exists only to carry the closure-end olets.** Its
  minimum length is `2 × gap + B_largest` (2 × 152.4 + 88.9 = 393.7 mm). A
  vent on top and a drain on the bottom can share a station band. Offer to
  round it to a stock length.
- **A vent and a drain at opposite clocks** may overlap axially. The spacing
  rule is weld to edge, not olet to olet across the pipe.
- With the barrel reducer FOB, the bottoms of the minor and major barrels
  are level, so both drains are true low points. The top of the major barrel
  is higher than the top of the minor, so gas in the minor barrel migrates up
  past the reducer. The trap-valve vent still catches gas held against a
  closed trap valve.

### Inserting a valve into an existing run

The user asked for a bypass valve "right after the elbow" on a leg that
already had a pipe there. The steps:

1. **Shorten the existing pipe in place.** Set its `Height` to the old
   length minus the stack (2 × (T1 + trf) + 2 × SEthk + valve `H` = 948.5 mm
   at DN200 600#). Then re-seat its **far** end on the downstream fitting:
   `alignTwoPorts(pipe, 1, downstream_tee, 0)`. Its `Name` and mark survive.
2. Weld the WN straight onto the elbow's port, then add gasket and studs, the
   valve, gasket and studs, and the WN.
3. Assert that the last WN's weld end meets the shortened pipe's port 0 at
   0 gap and dot −1. That closes the chain, because the stack length was
   computed from the same tables.

**"Match the other valves' style"** means the table row, the `Actuator`
property, the roll and the **colour**. Read `Actuator` and the world
direction of local +Y off the existing valves. Here they were `"Handwheel"`,
stem up. Gate valves take `"Handwheel"`, not `"Handle"` (§3.2). A new valve
comes out in the default grey. Copy `ViewObject.ShapeAppearance` and
`ShapeColor` from an existing valve. The user's existing valves were all blue,
small-bore vent valves included, so every new valve got the same colour.

### Changing a part in place keeps its mark

The user asked for the TOR's socket-weld cap to become a threaded cap. Edit
the existing object's properties instead of deleting and recreating it:
1. set `A`, `C`, `E`, `OD` and `Conn = "TH"` from `Cap_3000lb_TH.csv`;
2. set `PRating = "3000lb_TH"`;
3. recompute and re-seat on the TOR's port;
4. relabel.

The object keeps its `Name`, its mark ([C2]) and its spool container, and any
iso page that drew it still finds it. TOR caps are threaded (§3.1).

### Corrections this build took

These are a sample of what users change once they see a receiver:
- a bypass valve that the existing header lacked;
- spool containers (§14) nested under one receiver part, as on the launcher;
- **drain valves with handles instead of gearboxes** (`"Handle-closed"`). On
  a 2" drain under a 12" barrel this clears the tabulated gearbox envelope.
  It was an 8130 mm³ overlap with the closure pup. Offer it as the fix for
  that clash rather than a spacer pipe;
- a threaded TOR cap instead of a socket-weld one;
- a missing balloon on the construction iso. That was a generator issue,
  since fixed (see `techdraw-drawing` §18).

### Report items

- the two valve faces read from the model, and the fixed barrel total they
  imply;
- the pig space to the reducer weld (96.00" exact) and to the large end;
- the major-pipe and past-the-kicker lengths against the mandrel pig;
- every olet station with its edge-to-weld gaps on both sides, and its
  clock as `out_dir · Z = ±1`;
- the kicker small-end elevation against the valve centreline, and the pipe
  bottoms either side of each reducer;
- pig bars needed in the kicker branch;
- an equal tie-in tee on the pig's path needs guide bars (as in §13.1).

---

## 13.3 Joining a launcher and a receiver into one model

The case: the 8x12 launcher, with the companion receiver added at the far
end of its line, through a second 45° riser that mirrors the first.

### Read both models offline first

Read both `.FCStd` zips (§2.1) before any `execute_python`. Get every
object's label, `PSize` and `PRating`, and its world ports. That shows the
open end to build from and the receiver's attach port. Here it also showed:
- **The open pipe was not the object named in the prompt.** The user's
  "Tube001" was a label. Its `Name` was `Tube010`, and the object *named*
  `Tube001` was the major barrel. Match the user's word to labels first.
- **The existing riser was skewed 0.66° in plan.** Its bottom elbow's
  outlet was not exactly -X, so the far end of the 12 m pipe was 141.6 mm
  off the axis. A mirror image of that riser would rotate the receiver
  1.3° in plan. Ask, offering three options:
  - absorb the skew in the new bottom elbow;
  - mirror it exactly;
  - square up the existing pipe.

  The user chose to square it up. Re-place the elbow with `rot_two`,
  anchored at its inlet port with its outlet exactly on the axis. Then
  re-seat the long pipe with `alignTwoPorts`, and move anything parked in
  that pipe (a pig or tool model, for instance) by the same rigid delta.

### Copy, build the riser, merge, move

1. Copy the launcher file to the new name and open the copy (§2.1).
2. **"Identical" fittings copy the existing objects' properties**
   (`BendAngle`, `BendRadius`, `PRating`, `Height`), not a fresh table row.
   Here the two elbows carried `SCH-STD_SR45` and `SCH-STD_LR45` with the
   same 609.6 mm radius. Copy that rather than "fixing" it.
3. `doc.mergeProject(receiver_file)`. Diff `doc.Objects` before and after to
   get the merged set. Delete merged TechDraw pages, templates, views and BOM
   sheets: they draw the old marks and the old location.
4. **Move the receiver as one rigid body.** `alignTwoPorts` its attach pipe
   to the riser's outlet. Take `delta = new_pl · old_pl⁻¹` and apply
   `delta` to every other merged Quetzal object's `Placement`. Leave the
   `App::Part` containers at identity, so world ports stay
   `Placement · Ports` and later macros (an animation, say) need no global
   placements.
   Check the rigid-move error over every port (3.6e-12 mm here).

### Marks and labels after a merge

- **Offset the merged marks past the host's highest number per prefix**
  (`P+13, E+7, T+3, F+14, …`). Keep gaps that already exist (`[P5]` was
  missing on the launcher), and give new parts the next free number
  (`[C8]`, not the unused `[C1]`).
- **Mark the existing unmarked parts too.** The user-built riser was
  labelled `Elbow`, `Tube`, … Give them marks and descriptions in the host's
  format.
- **Make descriptions unique.** Roles such as "Trap valve" and "closure"
  repeat between launcher and receiver. The user chose to append
  ` (receiver)` to every receiver label, and to name the receiver's spools
  `Spool 04`–`06` and `Assembly material (receiver)`.
- **`mergeProject` renames clashing labels silently.** It appends `001`, in
  the middle of a mark label (`"... - closure001"`) and on containers
  (`"Spool 001"`). Search for `\d{3}( \(receiver\))?$` and repair them.
- Assert that no mark repeats, that no label repeats, and that no
  `App::Part` label repeats. Macros (drawings, animations) look parts up by
  mark and spool label.

### Verify

- Every port pair in the whole model that coincides closes at gap 0 and
  dot -1 (116 joints here).
- The only open ports are the ones you expect: blinds, pipeline
  continuations, valve outlets.
- The riser rise matches the first riser's (2512.357 mm).
- The receiver lands on the launcher's axis (y = 0, z = 0 here).
- The new parts are clash-free against everything, including anything
  parked in the pipe.
