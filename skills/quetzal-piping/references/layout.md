# Dimensions, orientation and constraints (§9)

Part of the `quetzal-piping` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 9. Interpreting an isometric drawing → model

Reconstructing a 3D model from a piping isometric (hand-drawn or CAD) is a
supported use case. Quetzal has **no** iso/PCF/isogen importer, so you parse the
drawing yourself and build with the makers above. Work through it like this.

### 9.1 Read the drawing (checklist)

1. **Find the axis legend / north arrow.** An iso has three axes: one **vertical**
   (elevation) and two horizontal drawn at ~30° from horizontal. Map each to a
   world unit vector — e.g. vertical → `(0,0,1)`, up-right → `(0,1,0)`,
   down-right → `(1,0,0)`. Use the drawing's own legend; don't assume.
2. **List every component from its callout/BOM** (e.g. "Flange, 3" 600# SO",
   "Elbow, 90 LR, Sch-STD"). Each callout → one maker + one CSV row.
3. **Read the dimensions** and note which axis each runs along.
4. **Note the terminations**: flanges, caps, and open **continuation arrows**
   (an open arrowhead = the line continues on another drawing; model it as an
   open pipe end). Small circled numbers are **BOM item tags**, not geometry.

#### 9.1.1 Zoom in before you commit — a first read WILL be wrong

A scanned or exported iso is typically ~1000 px wide; dimension text renders 6–8
px tall and **`5`/`3`, `6`/`9`, `8`/`0`, `2`/`7` are genuinely ambiguous** at that
size. Do not build from a whole-page read. Crop each dimension cluster and
upscale it 5–9× (Lanczos) before transcribing:

```python
from PIL import Image
im = Image.open(src).convert("L")
r = im.crop((240, 570, 400, 680))                 # one dimension cluster
r.resize((r.width * 9, r.height * 9), Image.LANCZOS).save("bot_left.png")
```

A magnified pass routinely corrects a digit, re-datums a dimension from one
feature to another, or relocates a fitting to the far end of a leg. Each of
those, left uncaught, produces a silent and entirely plausible-looking wrong
model.

#### 9.1.2 Mine the drawing's redundant data — it is your closure check

A production iso carries several **independent** encodings of the same geometry.
Reconcile them all *before* you start building; each one that closes to the
millimetre is strong evidence the reading is right, and one that doesn't tells
you exactly where to look again.

| Source | What it pins down |
|---|---|
| **Plant coordinates** (`N …`, `W …`, `EL …`) on tie-ins and branches | Absolute position; anchor the model on the fixed tie-in and print the derived N/W/EL for every other callout next to the drawing value |
| **Elevations** (`EL +101523`) | Vertical work points — crisp six-digit numbers, usually the most reliable data on the sheet |
| **Title block CL length**, per nominal size | Total route centre line; catches an error anywhere in the chain |
| **BOM take-off** (`17.6 M` of DN100 pipe) | Sum of cut lengths, to ~1 % |
| **BOM quantities** (`4 × 90° elbow`, `1 × 45° elbow`) | The *topology*. If your route needs five 90° elbows and the BOM lists four plus a 45°, your route is wrong |
| **Bolt counts** (`48 studs` ÷ 8 per DN100 joint) | Exact number of flanged joints, by size |
| **`Fn Gn Bn/Bn/Bn` callouts** | Which flange / gasket / bolt BOM items make up each joint — and, by elimination against the BOM quantities, *which* flange goes where (e.g. the single WN vs the single erection SO) |

Cross-check them against each other too: a joint count derived from the stud
quantities can settle whether a valve is flanged or socket/threaded, and a
title-block CL length can confirm a short sub-chain that is otherwise unreadable.

Emit these as printed checks in the build's report (§9.6) rather than only
checking them once yourself — the user can then adjudicate anything that still
disagrees.

### 9.2 Dimensions are to WORK POINTS, not cut lengths

This is the key rule. Iso dimensions run to **work points (IPs)** — the
**centerline intersections** of fittings — not to pipe ends. "48\" from the flange
face to the elbow" means 48" along that axis from the flange face to the point
where the elbow's two centerlines cross. So:

1. **Build the work-point skeleton in 3D first.** Pick one IP as the origin and
   step along the mapped axis vectors by each dimension to get the other IPs.
2. **Place each fitting at its work point.** For a Quetzal `Elbow` and `Tee` the
   **local origin is the work point** (all centerlines pass through it), so
   setting `obj.Placement.Base = WP` lands the fitting exactly. Take-outs:
   elbow center-to-face `E = R·tan(BA/2)` (= `R` for 90°); tee `C` (run
   half-length) and `M` (branch). Read them back from `obj.Ports` to stay exact.
3. **Derive pipe cut lengths by spanning the placed fittings' ports** — create
   each straight pipe from one fitting's world port to the next
   (`length = (portB_world - portA_world).Length`). This avoids hand-computing
   take-outs and is robust to the model's exact fitting dimensions.

> **Watch for chained (cumulative) dimensions.** Two or more dims in a row along
> one axis are often measured end-to-end, **not** each from a common datum — e.g.
> "2'-0" then 2'-6"" along +X means the far work point is at **4'-6"** from the
> flange face, with a branch/feature at the 2'-0" tick. When a leg carries several
> dims that don't obviously share an endpoint, sum the chain to reach the far work
> point and treat the intermediate ticks as feature locations. A hand sketch
> rarely makes the datum explicit, so **confirm with the user.**

#### 9.2.1 One drawing mixes dimension conventions

Within a single leg you will find, side by side:

- **True cut pipe lengths** — the fabricator's number for one spool piece.
- **Combined flange/pipe/fitting lengths** — e.g. `263` = elbow take-out `152`
  + pipe + flange `2·trf`; the pipe must be *calculated out* of it.
- **Component dimensions** — a valve face-to-face (`305`), a reducer length
  (`101` ≈ the table's `H` of 102), a fitting take-out.

You usually cannot tell which is which from the drawing alone. Two things make
this survivable:

1. **Recognise the component dims first.** Match each short dim against the
   `tablez/` values you already read — reducer `H`, valve `H`, elbow take-out,
   flange `T1`. A dim within ~1 mm of a catalogue number almost certainly *is*
   that number, not a pipe.
2. **Build the run as a port chain and let the pipes fall out.** Place the
   fixed-length components in order with `alignTwoPorts`, give each pipe either
   its stated cut length or a length derived by spanning, and never hand-compute
   a station. Both conventions then resolve correctly and a misread dim shows up
   as an absurd pipe length instead of silently wrong geometry.

#### 9.2.2 The short-pipe rule (fitting take-outs disguised as pipe)

**A fabricated stub shorter than `min(50 mm, OD/2)` does not exist.** If a
combined dim leaves you with one, the drawing number was a *fitting take-out that
the drafting package rounded* — e.g. `153` against a DN100 LR elbow whose real
centre-to-face is `152`, leaving a nonsense 1 mm pipe. The correct model welds
the two fittings directly together.

Implement it as a filter on every dimensioned stub, not as a one-off deletion,
and **list each adjustment in the report** (Golden Rule 7):

```python
MIN_PIPE_ABS = 50.0

def mk_pipe(dn, L, label, snap=False):
    lim = min(MIN_PIPE_ABS, od_of(dn) / 2.0)
    if L < lim:
        if snap:
            adjust.append((label, L, lim))   # weld the neighbours directly
            return None                      # chain() skips a None entry
        short.append((label, L, lim))        # span-derived: warn, still build
    ...
```

Note the limit is size-dependent: DN100 → 50.00, DN80 → 44.45. A 45 mm DN80 stub
passes; a 43 mm one does not — so when a marginal stub trips the rule, suspect
the *digit*, not the geometry, and re-crop that dimension (§9.1.1).

### 9.3 Orientation & roll (critical for elbows/tees)

`alignTwoPorts` fixes a part's position and makes one port anti-parallel to its
mate, but **leaves the roll about that axis free** (shortest-arc). For a straight
in-line part that's fine; for an **elbow or tee the free roll decides which way
the outlet/branch points**, so set the orientation explicitly instead.

> **Do NOT hardcode a fitting's local port layout — read it.** Different classes
> put their ports in different local frames, and the numbers are not obvious. The
> `Elbow` (from `makeElbow`), for a 90°, has **port0 at `(0,BR,0)` dir +Y and
> port1 at `(BR,0,0)` dir +X**, with its **work point at the local origin** — and
> which port ends up "inlet" vs "outlet" is easy to get backwards. (`SocketEll`
> uses a *different* `(E,0,0)/(0,E,0)` layout — another reason not to assume.)
> Guessing here silently offsets the pipes by the elbow take-off.

> **Angle feasibility check — run this on paper before you build.** For any
> elbow, the angle between the **outward** inlet port direction and the outgoing
> leg direction is `180° − BendAngle`: 90° for a 90° elbow, **135° for a 45°**.
> Equivalently, the leg directions either side must differ by exactly the bend
> angle. `rot_two` below silently produces garbage if you hand it two directions
> whose separation doesn't match the fitting, so check it first:
>
> ```python
> assert abs(inlet_dir.getAngle(outlet_dir) - math.radians(180 - BA)) < 1e-6
> ```
>
> **Mind which convention you are in.** That form compares the *outward* inlet
> direction against the outgoing **leg** direction. If instead you are handing
> `rot_two` two *outward port* directions — which is what `PortDirections`
> gives you — the two must be exactly `BA` apart, not `180 − BA`. Write the
> assert against the same vectors you pass to `rot_two`, or it encodes the wrong
> convention and passes on a route that is wrong.
>
> This is a fast, decisive test on a candidate route, and it costs nothing to run
> before any build code exists. A 45° elbow proposed between two legs that are
> 90° apart is geometrically impossible, so the route has been misread — no
> amount of careful placement will rescue it. Combined with the BOM elbow
> quantities (§9.1.2), it usually pins the topology outright.

The robust pattern: **read the actual local port directions**, build the rotation
that carries them onto the two desired world directions, and anchor the fitting's
true work point (the intersection of its port centerlines) at the target IP:

```python
def rot_two(a0, a1, b0, b1):       # R with R*a0==b0 and R*a1==b1
    def frame(u, v):
        x = Vector(u).normalize(); z = x.cross(Vector(v)); z.normalize()
        return FreeCAD.Rotation(x, z.cross(x), z)
    return frame(b0, b1).multiply(frame(a0, a1).inverted())

elbow = pCmd.makeElbow([...], rating="SCH-STD"); doc.recompute()
d0, d1 = elbow.PortDirections[0], elbow.PortDirections[1]
wp_local = line_intersect(elbow.Ports[0], d0, elbow.Ports[1], d1)  # port CLs cross
R = rot_two(d0, d1, inlet_dir, outlet_dir)   # e.g. inlet_dir=-Y, outlet_dir=+X
elbow.Placement = FreeCAD.Placement(WP_elbow - R.multVec(wp_local), R)
```

The **Tee**'s local frame *is* tidy — run along local ∓Z/±Z (ports **0/1**),
branch along local +Y (port **2**), work point at the local origin — so it can be
placed directly with the three-axis constructor
`FreeCAD.Rotation(xdir, ydir, zdir)` (pass where local X, Y, Z must point):

```python
# Tee run along world X, branch up +Z:  localZ->+X, localY->+Z, localX->+Y
tee.Placement = FreeCAD.Placement(
    WP_tee, FreeCAD.Rotation(Vector(0,1,0), Vector(0,0,1), Vector(1,0,0)))
```

Pick the run port that faces upstream, leave the other open (or flange it), and
mate a flange to the branch with `alignTwoPorts(flange, 1, tee, 2)`. When in
doubt about any fitting, **print its `Ports`/`PortDirections` after a recompute**
and orient from those rather than from an assumption.

**Fittings welded directly together (no pipe between)** — a flange bolted straight
onto an elbow, or an elbow welded onto a weldolet outlet — are still placed by
*port*, not work point:
- If the new part is axisymmetric (a flange), free roll is fine:
  `alignTwoPorts(flange, 1, elbow, outletPort)` seats it and its raised face
  points the right way automatically.
- If the new part is itself an **elbow** whose outlet must aim a chosen way, anchor
  its **inlet port** (not its work point) at the mate, then aim the outlet:
  ```python
  R = rot_two(d0, d1, inlet_dir, outlet_dir)          # e.g. inlet +Z, outlet +X
  elbow.Placement = Placement(matePortWorld - R.multVec(elbow.Ports[0]), R)
  ```
  (Anchoring the work point here would offset the joint by the elbow take-out.)

> **A direct weld makes two dimensions dependent — exploit that as a check.**
> If an elbow welds straight onto a tee, its tangent *is* the tee's weld face, so
> `ell_tangent_sta == tee_sta + C` exactly. Two constants you might otherwise
> have measured independently are now one degree of freedom, and the second
> measurement becomes a **closure check** rather than an input. Drive the chain
> from whichever end you measured more reliably, derive the other, and print both
> with the delta (§9.6):
>
> ```python
> ELL_TANGENT_DERIVED = TEE_STA + TEE_C
> TANGENT_DELTA = ELL_TANGENT_DERIVED - ELL_TANGENT_MEASURED
> ```
>
> This routinely catches errors of hundreds of millimetres, because the two
> constants are usually measured to very different standards — a tee station
> taken off a leader arrowhead, say, against a bend tangent measured on the pipe
> itself. Re-deriving the weaker from the stronger closes the joint to 0.0 mm.
> Say in the report that the two constants are locked, so a user editing one
> knows to edit the other.

#### 9.3.1 Absorbing a small level change by rolling a tee and an elbow

A branch that has to reach a line at a slightly different elevation doesn't
need an extra pair of elbows. The typical case is a kicker line off a barrel
that an eccentric reducer lifted (§3.4). Tilt the branch instead:

1. Place the far fitting's work point where the far line needs it. Here that is
   the elbow at the kicker run's elevation, directly across from the tee.
2. **Aim the tee's branch straight at that work point:**
   `u = WP_elbow − WP_tee`, normalised. Place the tee with
   `Rotation(u.cross(run), u, run)`. Local Y is the branch, local Z the run,
   and local X = Y × Z keeps it right-handed.
3. **Place the elbow with `rot_two(d0, d1, −u, outlet_dir)`.** A 90° elbow
   stays feasible as long as `u ⊥ outlet_dir`, which holds whenever the tilt is
   in the plane normal to the outlet leg. The feasibility assert (§9.3) checks
   exactly this.
4. **Derive the sloped pipe by spanning** the tee's branch port and the elbow's
   inlet port (§9.2). Its length and angle then follow from the geometry; you
   don't set them.

Report the tilt in degrees: `asin(−u.z)` gave 1.35° for 52.4 mm over 2.2 m.
Say that the outgoing leg is still level. If the elevation step changes, the
whole thing re-solves with no constant to re-tune (§9.7).

### 9.4 Callout → maker/CSV cheat-sheet

| Callout | Maker | CSV |
|---------|-------|-----|
| Pipe, Sch-STD 3" | `makePipe("SCH-STD", [DN, OD, thk, H])` | `Pipe_SCH-STD.csv` |
| Elbow, 90 LR, Sch-STD | `makeElbow([DN, OD, thk, 90, BR], rating="SCH-STD")` | `Elbow_SCH-STD_LR90.csv` |
| Tee, Sch-STD 3" | `makeTee([DN, OD, OD2, thk, thk2, C, M, DN2], rating="SCH-STD")` | `Tee_SCH-STD.csv` |
| Flange, 3" 600# SO | `makeFlange([...], fclass="600lb")` | `Flange_ASME-SO-RF-600lb.csv` |
| Flange, 3" 600# RF Sch-STD | WN flange, bore = `OD-2·thk` | `Flange_ASME-WN-RF-600lb.csv` |
| Weldolet, 2" Sch-XS straight | `makeOutlet(["Sch-XS", DN, OD, thk, A, B, "BW", 0, 0], pos, rot, carrierOD=runOD)` | `Outlet_Sch-XS.csv` (Ang=0) |
| Ball valve, 2" flanged 300# | `makeValve([DN, "Ball_LongPatternRF", H, Kv, "300lb", 0, 0], flgPropList=<BL row>, actuator="Handle")` | `Valve_Ball_300lbRF.csv` + `Flange_ASME-BL-RF-300lb.csv` |

Reminder: sizes are DN labels — **3" = DN80**, 4" = DN100, 6" = DN150.

### 9.5 Built-in auto-router — avoid for standard elbows

`makePypeLine2` / `makeBranch` (`pCmd.py` ~L1574 / ~L1619) auto-generate
pipes+elbows along a Draft wire or Sketch. **Do not rely on them here:** the
elbows they emit use a bend radius of **0.75·OD**, which does **not** match
standard long-radius (1.5·NPS) or short-radius elbows. Reconstruct runs with
explicit `makeElbow` using the real `BendRadius` from the CSV. (A future
enhancement could have the auto-router prompt for the elbow spec — out of scope
for now.)

### 9.6 Structure the build so the user can true it up

An iso reconstruction is a *collaboration*: you will misread something, and the
user has the original. Structure the build so a correction is a one-number edit
and a re-run, not an archaeology exercise.

- **One `DIMENSIONS` block, sent first** holding every number taken off the
  drawing — elevations, leg dims, the short sub-chains, branch directions, plant
  coordinates — each with a comment saying what it measures between. No build
  code below it should contain a literal dimension. Over MCP this is a dict
  defined in its own `execute_python` call; a correction is then a one-line
  re-send of that dict followed by a rebuild, and the persistent namespace (§2.2)
  keeps everything else in place.
- **Keep the build re-runnable.** Wrap it in a `def build():` in the session
  namespace so a correction is `build()` again into a fresh document, rather than
  patching a half-built model in place. Rebuilding from the corrected
  `DIMENSIONS` is far safer than nudging placements on the objects that exist.
- **Anchor on the fixed tie-in** (the vessel/equipment nozzle), not on an
  arbitrary origin, so the derived plant coordinates are directly comparable to
  the drawing's callouts.
- **Label every object with its BOM item and spool number**, e.g.
  `"[5] Elbow DN100 90LR (P3) - spool 6"`. This is how the user finds the part
  they want changed.
- **With no BOM, give every component a typed mark**: `[P1]` pipe, `[E1]`
  elbow, `[T1]` tee, `[R1]` reducer, `[F1]` flange (WN and blind), `[V1]` valve,
  `[G1]` gasket, `[B1]` stud set, `[O1]` outlet (weldolet, sockolet, TOR),
  `[C1]` cap, `[S1]` support member (beam, post or Part solid), `[U1]` U-bolt.
  Map the prefix from the object's `PType`, not its label. Support members have
  no `PType` (a `Beam` carries `FType`; a post is a `Pipe`), so assign `[S]`
  explicitly for them (§3.5).
  Number the parts in a **walk order you write down explicitly**, one list of
  keys along the assembly, not in build order. Assert the list covers every
  object exactly once. Give flange/gasket/stud sets on either side of a valve
  a side name ("kicker valve, elbow side") rather than "near"/"far". Those words
  describe build order and read backwards when you walk the run the other way.
- **Keep marks stable across correction rounds.** The user refers to parts by
  mark ("add a drain to [P7]"). When parts are removed, leave the gaps. New
  parts take the next free number, and a deleted number is never reused for a
  different part. Offer a full renumber, but don't do one without being asked.
  A renumber silently repoints every mark in the conversation.
- **Print a report** (`FreeCAD.Console.PrintMessage`) containing: the work-point
  table with elevations; every pipe cut length with its label; the take-outs
  actually read from `tablez/`; every short-pipe adjustment (§9.2.2); derived
  plant coordinates beside the drawing values with the deltas; and each §9.1.2
  closure check beside its drawing/BOM target. Component counts vs BOM
  quantities catch a whole class of topology errors in one line.
- **Say what still disagrees.** If two independent checks pull opposite ways,
  report both deltas and name the sub-chain they implicate rather than picking
  one and staying quiet. The user can settle it from the original in seconds.

### 9.7 Solve constraints through the chain — never tune a constant to fake them

When the user states a *relationship* ("these two valves are aligned in X", "the
tee is welded straight onto that flange", "the drain lines up with the trap
valve"), that is a **constraint, not a dimension**. Encode it as an expression
solved from the port chain, and the model stays correct when anything upstream
changes. Tune a constant until it looks right and the next correction silently
breaks it.

```python
# WRONG: a station chosen so the two valves happen to line up today
X_TIE_VALVE_FACE = 10470.0

# RIGHT: solve the jog backwards from the other leg's flange face, through
# every take-out between.  Now nothing can drift out of alignment.
X_KICKER_JOG = _world(byp_flange, 0).x - (T1_8 + TRF_8) - L_KICKER_LEAD - BR8
```

This is not theoretical. Mid-build corrections routinely insert a component the
user first said was not there — a short lead pipe, an extra flange pair. When the
jog is *solved*, the whole fix is adding one term to one expression and the
alignment still holds at `dX = 0.000000 mm`. When the station is a tuned literal,
the new component pushes everything downstream of it out by its own length and
nothing complains.

Three corollaries:

- **A derived station is also a closure check.** Print it beside whatever you
  measured off the drawing or photo, with the delta (§9.6). A leg offset summed
  from a tee branch + flange pair + elbow take-out is a far better number than
  the one scaled off a plan view — but quoting both is what tells the user the
  two agree.
- **Assert the constraint you were given, in the build code.** A seated joint
  should be provably seated:
  `if (world(tee,0) - world(flange,1)).Length > 1e-6: raise`. That converts
  "I think I did what you asked" into a check that fails loudly — and over MCP it
  fails as a traceback on the call that broke it, while you are still building.
- **Drop the constant from `DIMENSIONS` once it is derived.** Leaving a now-unused
  `Y_BYPASS_TEE` in the block invites the user to edit a number that no longer
  does anything.

#### 9.7.1 A station that demands a negative pipe is usually a direct weld

When a measured station leaves no room for the fittings it has to contain, the
instinct is to enlarge it. Resist that: the far commoner truth is that **there is
no pipe there at all** and the two components are welded or bolted directly
together (§9.3), which makes the station derived rather than measured.

The tell is an arithmetic one: a tee read at ~2210 mm whose upstream stack (ell
take-out plus a WN/valve/WN set) already consumes 2085 mm, against the tee's own
`C` of 254 mm. Padding the constant to 2600 mm and writing up an "adjustment"
buries the problem. Confirming with the user that the tee is welded straight onto
the valve's downstream flange makes the station *derived*, and the adjustment
note disappears. The reading was never wrong by 390 mm; it was being asked to
describe a joint that has no pipe in it.

Padding a dimension to make room is a smell. Ask whether the gap should be zero.
