# Quetzal components, flanges, ports and tables (§3–§6)

Part of the `quetzal-piping` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 3. The maker functions (component catalog)

All live in `pCmd.py`. `propList` order matches the corresponding feature
class `__init__` in `pFeatures.py` — when in doubt, read that constructor.
`pos` (Vector, default 0,0,0) and `Z` (Vector axis, default 0,0,1) orient the
part; you usually create at the origin and snap with `alignTwoPorts` afterward.

| Component | Function | `propList` |
|-----------|----------|------------|
| Pipe | `makePipe(rating, propList, pos, Z)` | `[DN, OD, thk, H]` |
| Elbow | `makeElbow(propList, pos, Z, rating)` | `[DN, OD, thk, BA, BR]` (BA=bend angle, BR=bend radius) |
| Flange | `makeFlange(propList, pos, Z, doOffset, rating, fclass)` | see §4 (17 elements) |
| Cap | `makeCap(propList, pos, Z, rating)` | `[DN, OD, thk]` |
| Reducer | `makeReduct(propList, pos, Z, conc, smallerEnd, rating)` | `[DN, OD, OD2, thk, thk2, H, DN2?]` (`conc=True` concentric) |
| Tee | `makeTee(propList, pos, Z, insertOnBranch, rating)` | `[DN, OD, OD2, thk, thk2, C, M, DN2?]` |
| Gasket | `makeGasket(propList, pos, Z)` | `[DN, FClass, IRID, SEID, SEOD, CROD, SEthk, Rthk]` |
| Bolts+nuts | `makeBolts_Nuts(propList, pos, Z)` | `[DN, FClass, dBolt, dNut, tNut, df, n, lBolt, SEthk]` |
| Outlet | `makeOutlet(propList, pos, rot, carrierOD)` | `[rating, DN, OD, thk, A, B, endType, angle, E]` (see §3.1) |
| Valve | `makeValve(propList, pos, Z, flgPropList, actuator)` | see §3.2 (flanged: body + BL-flange list) |
| Socket cap | `makeSocketCap(propList, pos, Z)` | `[DN, OD, A, C, E, Conn]` — maps 1:1 onto `Cap_<class>_SW.csv`; mates via port **0** |
| Socket ell | `makeSocketElbow(propList, pos, Z, rating)` | `[DN, OD, BA, A, C, D, E, G, Conn]` (§3.3) |
| Socket tee | `makeSocketTee(propList, pos, Z, insertOnBranch, rating)` | `[DN, DN2, OD, OD2, A, C, D, E, G, Conn]` (§3.3) |
| Socket coupling | `makeSocketCoupling(propList, pos, Z)` | `[DN, DN2, OD, OD2, A, C, D, E, Conn]` — reducing rows included (§3.3) |
| Socket union | `makeSocketUnion(propList, pos, Z)` | `[DN, OD, A, C, D, E, Conn]` (§3.3) |
| Beam (support) | `makeBeam(propList, pos, Z)` | `[rating, SSize, stype, H, W, ta, tf, Height]` (§3.5) |
| U-bolt (support) | `makeUbolt(propList, pos, Z)` | `[PSize, ClampType, C, H, d]` — no `PortDirections`, place by `Placement` (§3.5) |

> **This table is NOT exhaustive, and a substitution is a claim you must verify.**
> A socket cap is the trap for the unwary: `makeCap`'s propList is
> `[DN, OD, thk]`, which does not fit `Cap_3000lb_SW.csv`'s
> `PSize;OD;A;C;E;Conn` — but that mismatch is not grounds for shipping a
> butt-weld cap and a "no table fits" note, because `makeSocketCap` maps onto
> those columns exactly. **Before you write the words "no exact table/maker
> exists", `grep -n "^def make" pCmd.py` and read the list.**
> An unnecessary substitution is worse than a missing feature: it puts
> wrong geometry in the model *and* tells the user it was unavoidable.

**Two propList quirks — do not trip on these:**
- **Outlet** embeds the **rating as element [0]** of the propList, *not* as a
  separate function arg like every other maker. It also takes `rot`
  (a full `FreeCAD.Rotation`) instead of a `Z` axis vector.
- **Gasket** and **Bolts+nuts** carry **`FClass` as element [1]**, and the maker
  uses it as the object's rating (`propList[1]`). Read the gasket's `SEthk` and
  pass the same value into the bolt propList (it drives bolt length).

To learn the exact `propList` any GUI form builds from a CSV row, read the
`insert()` method of the matching form in `pForms.py` (e.g. `insertPipeForm`
~L303, `insertFlangeForm` ~L1441). Those are the authoritative examples.

### 3.1 Branch fittings (outlets)

A sockolet / weldolet is placed on the *surface* of a run pipe, not on a port.
Use the placement helper — never compute the position by hand:

```python
# t = axial distance from pipe Port[0] (mm); phi_deg = circumferential clock
# angle measured from the pipe's local +X, CCW when viewed from Port[1];
# alpha_deg = spin of the fitting about its own outward axis (matters only for
# 45deg laterals).
pos, rot = pCmd.outletPlacementOnPipe(pipe, t=406.4, phi_deg=90.0)   # pCmd.py ~L2802
outlet = pCmd.makeOutlet(
    ["3000lb", "DN25", OD, thk, A, B, endType, angle, E],  # rating at [0]!
    pos, rot, carrierOD=pipe.OD)                            # carrierOD = run OD
```

- `endType` = `"BW"`/`"SW"` (CSV `Conn`), `angle` = `0` straight / `45` lateral
  (CSV `Ang`), `E` = socket depth. Data file: `Outlet_<rating>.csv`, keyed by the
  **branch** DN.
- **Columns vary by file:** the socket file `Outlet_3000lb.csv` is
  `PSize;OD;thk;A;B;E;Ang;Conn` (SW, carries `E`); the butt-weld schedule files
  `Outlet_Sch-STD/XS/XXS.csv` are `PSize;OD;thk;A;B;Ang;Conn` with **no `E`**
  (pass `E=0`). Every PSize has both a straight (`Ang=0`) and a 45° lateral
  (`Ang=45`) row — **filter on `Ang`** as well as `PSize`.
- The Outlet exposes a **single port** (index 0) at the branch outlet end, dir
  `+Z` outward in its local frame. Weld the next part to it with
  `alignTwoPorts(part, weldPort, outlet, 0)`.
- Always pass **`carrierOD`** = the run pipe's OD so the fitting base is shaped
  flush to the pipe surface.
- **A TOR (Thread-O-Ring) fitting is just another outlet.** `Outlet_TOR.csv`
  (`PSize;OD;thk;A;B;Ang;Conn`, BW, no `E`) goes through `makeOutlet` with
  `"TOR"` at element [0]. Its `B` is `OD + 0.001`, which is enough taper to
  avoid the zero-taper crash described below. Only the fitting body is
  tabulated, not the TOR plug or closure, so say so in the report. A cap on it
  (`makeSocketCap`, mated port 0 to the outlet's port 0) is the nearest stand-in.
- **Measure an outlet's station along the pipe axis, not as a distance.**
  `outletPlacementOnPipe` puts `Placement.Base` on the pipe's *outer surface*.
  `(outlet.Placement.Base - pipe_port0).Length` therefore includes the radius
  (24.000" read as 24.384" on a DN200). Project onto the axis instead:
  `(outlet.Placement.Base - wpos(pipe, 0)).dot(pipe_axis)`. A check that
  disagrees with the prompt by roughly `sqrt(t² + r²) − t` is this, not a
  build error.
- **"Edge" of a weldolet or sockolet means its base, `B/2` from its
  centreline.** "4 in between the flange weld and the edge of the weldolet"
  puts the centreline at `t = 4·25.4 + B/2` from the pipe end at that weld.
  Keep that gap as a named constant, and print the toe-to-weld distance in the
  report.
- **`B == OD` in the table is a hard crash, not a warning.** `Outlet.execute`
  builds a butt-weld body as `Part.makeCone(r_B, r_od, A, …)`, and OCC raises
  `Part.OCCDomainError: creation of cone failed` for a zero-taper cone. A
  hand-written outlet table whose base diameter equals the branch OD will stop
  the build dead at that fitting. The fix belongs in the **table** (give `B` a
  real value) or in `pFeatures` (fall back to `makeCylinder` when
  `abs(r_B - r_od)` is tiny) — resist "fixing" it in the build by nudging `B`,
  which silently overrides the user's data. A taper as small as 0.001 mm builds
  fine, so this is genuinely a data-entry symptom.
- **`outletPlacementOnPipe` takes a `Pipe` — nothing else.** Branches do land on
  fittings (a vent thredolet on the *body* of a tee is common, and is usually
  what "on the side of the tee" means). Place those by hand, keeping the
  signature parallel to the pipe case so both read alike:

  ```python
  def mk_outlet_on_body(host_WP, run_axis, out_dir, station, carrier_OD, ...):
      pos = host_WP + run_axis.normalize() * station + out_dir * (carrier_OD / 2)
      rot = FreeCAD.Rotation(Vector(0, 0, 1), out_dir)     # local +Z points out
      return pCmd.makeOutlet([...], pos, rot, carrierOD=carrier_OD)
  ```

  `station = 0` puts it dead centre on the fitting's work point — which is what
  "centred on the tee" asks for, and it is worth printing the offset as a check.
- **Clocking is ambiguous in prose.** A prompt like "outlet at 90 degrees" may
  mean the circumferential clock (`phi_deg`) *or* a 45deg-style branch angle.
  Confirm with the user, and expose `phi_deg` as an obvious named constant.
- **Give every branch its own direction constant.** Which way a takeoff faces is
  one of the hardest things to read off an iso, and two branches that look alike
  often point opposite ways. `BRANCH_DIR_L` / `BRANCH_DIR_R` costs nothing and
  turns "flip that one 180°" into a one-character edit; a single shared
  `BRANCH_DIR` forces a code change.
- **Don't guess `phi_deg` to aim a branch at a world direction** (e.g. "straight
  up" or "off the pipe bottom") — the pipe's local frame depends on how it was
  built. Solve it from the pipe's actual rotation:

  ```python
  def phi_for_dir(pipe, desired):    # desired = world unit vector the branch points
      R = pipe.Placement.Rotation
      ex, ey = R.multVec(Vector(1, 0, 0)), R.multVec(Vector(0, 1, 0))
      return math.degrees(math.atan2(desired.dot(ey), desired.dot(ex)))
  # phi_for_dir(runPipe, Vector(0,0,1)) -> branch up;  Vector(0,0,-1) -> off bottom
  ```

### 3.2 Flanged valves

`makeValve(propList, pos, Z, flgPropList, actuator)` builds a flanged valve when
**`flgPropList is not None`** (that presence selects the flanged path). It takes
two lists:

- `propList = [DN, VType, H, Kv, Conn, BottomH?, TopH?]` — `H` = face-to-face
  length, `Conn` = pressure class (e.g. `"300lb"`), `VType` = the CSV valve type
  (e.g. `"Ball_LongPatternRF"`). Data file `Valve_Ball_<class>RF.csv`
  (cols `PSize;VType;H;Kv;Conn`), keyed by the run DN. (Flanged tables are the
  ones whose `Conn` is a class like `300lb`, vs `SW`/`TH`.)
- `flgPropList = [PSize, FlangeType, D, t, f, n, df, drf, trf]` — read straight
  from the matching blind-flange table `Flange_ASME-BL-RF-<class>.csv`. It draws
  the valve's **integral end flanges**, so do NOT add separate flanges/gaskets for
  the valve's own faces.
- `actuator` = `"Handle"` (default) or `"Gearbox"`.

**Other flanged families follow the same call** with a different file:
`Valve_Gate_<class>RF.csv`, `Valve_Plug_…`, `Valve_Check_Swing_…`,
`Valve_Ball_Floating_…`, `Valve_Ball_Trunnion_…`. Their **column sets differ** —
Gate/Ball/Plug carry `TopH;WheelD` and have **no `BottomH`** (pass `0`), while
`Check_Swing` carries `BottomH;TopH`. Read by name with a default (§6). Also note
`Valve_Ball-Threaded.csv` spells the type column **`Vtype`**, not `VType`.

**No table for the called-up valve type?** Not every body style exists at every
class — there is, for instance, no 300# RF *globe* table. Ask the user which
substitute they want, then **drive the geometry from the drawing's B16.10
face-to-face, not the substitute's catalogue `H`**, so the run still closes on
the iso dimensions; expose it as a named constant and state the substitution:

```python
V80_F2F = 318.0        # drawing B16.10 F2F; the DN80 gate table's H is 283
```

Ports: **port 0 at `+H/2` (dir +Z), port 1 at `−H/2` (dir −Z)** — the two flange
faces. `makeValve` auto-orients port 0 to face `Z` and drops it at `pos`, but in
an assembly just create it and mate with `alignTwoPorts`, e.g.
`alignTwoPorts(valve, 1, upstreamFlange, 0)` then `alignTwoPorts(blind, 0, valve, 0)`
to cap the far side.

#### 3.2.1 Set the actuator roll — `alignTwoPorts` will not

**The handle/gearbox is drawn along the valve's local `+Y`** (`pFeatures.py`
~L2085 gearbox, ~L2434 handle), with the flow axis on local `Z` and the handwheel
spin axis on local `X`. `alignTwoPorts` fixes position and makes the ports
anti-parallel but **leaves the roll about the flow axis free** (§9.3), so every
gearbox and lever lands at an arbitrary clock — typically sideways or underneath.
On a real drawing or photo they are almost always *on top*, so set the roll
explicitly rather than accepting the shortest-arc default:

```python
def seat_valve(v, mate_obj, mate_port, actuator_dir):
    """Seat valve port 1 on mate_obj/mate_port, rolled so the actuator aims at
    actuator_dir.  Local Z = flow, local Y = actuator."""
    flow = mate_obj.Placement.Rotation.multVec(mate_obj.PortDirections[mate_port])
    flow.normalize()                                  # mate -> valve
    ydir = Vector(actuator_dir)
    ydir = ydir - flow * ydir.dot(flow)               # orthogonalise
    if ydir.Length < 1e-6:
        raise RuntimeError("actuator direction is parallel to the flow axis")
    ydir.normalize()
    R = Rotation(ydir.cross(flow), ydir, flow)        # (xdir, ydir, zdir)
    mate_world = mate_obj.Placement.multVec(mate_obj.Ports[mate_port])
    v.Placement = Placement(mate_world - R.multVec(v.Ports[1]), R)
```

The same applies to a valve you place directly rather than mate: pass the
three-axis constructor where local X, Y and Z must point, e.g. a valve on a run
along `+X` with its gearbox up is
`Rotation(Zhat.cross(Xhat), Zhat, Xhat)` — **not** `Rotation(Zhat, Xhat)`, which
sets the flow axis and lets the roll fall where it may. This is cosmetic-looking
but obvious in the model, and it is the kind of thing a user notices immediately.

**The handwheel sits on the valve's local `+X` side, and that is a second
choice.** Once the gearbox is up, the handwheel can face either way across the
run. Find out which way it faces now by measuring the valve's vertex extents
along its world-mapped local X (about 285 mm on one side and 184 mm on the
other for a DN200 600# trunnion valve). Don't assume. When the user wants the
handwheels "facing out of the loop", or away from where an operator would
stand, turn the valve **180° about its gearbox axis through the valve
centre**:

```python
c = (wpos(v, 0) + wpos(v, 1)) * 0.5
v.Placement = Placement(Vector(), Rotation(Zhat, 180), c).multiply(v.Placement)
```

A flanged ball valve is the same at both ends, so nothing else moves. But its
**ports swap ends**: port 0 is now where port 1 was. Update any joint list you
verify against (flip `0 ↔ 1` for that valve), or the next closure check
reports a false gap of one face-to-face length.

**A clash from the actuator envelope is a report item, not something to fix
on your own.** `TopH`/`WheelD` in the valve tables are generous, so a gearbox
on a drain valve tucked under a large barrel can overlap the barrel (8130 mm³
on a DN50 drain under a DN300 barrel). If the user specified that orientation,
build it, report the overlap with its volume, and offer a fix, such as the
smallest spacer pipe that clears it (found by translating a copy of the valve
shape until `common()` is empty). The user may know the real actuator is
smaller. If the orientation was *your* default, choose a clear one and say so.

#### 3.2.2 Small-bore socket-weld valves

There is **no socket-weld valve table**. `makeValve` does have a SW/TH path,
`[DN, VType, OD, ODBody, H, E, Conn, Kv?]`, and `Valve_Ball-Threaded.csv`
supplies every value except `Conn` (spelled `Vtype`, and `Conn = TH`). Pass
`Conn = "SW"` to model a socket-weld valve on the threaded body dimensions,
and name it as a substitution in the report and the object label. Its ports
are at `z = ±(H/2 − E)` (±35.8 mm for DN25), dirs ±Z, at the socket bottoms.
Mate it with `seat_valve` like a flanged valve, so the handle roll is chosen,
not left to chance.

### 3.3 Socket-weld fittings (the 3000# SW family)

`makeSocketElbow`, `makeSocketTee`, `makeSocketCoupling`, `makeSocketUnion` and
`makeSocketCap` cover the socket families tabulated as
`<Fitting>_{3000,6000,9000}lb_SW.csv`. Each propList maps **1:1 onto its CSV row
in column order**, so there is nothing to compute:

| File | Columns = propList |
|---|---|
| `Elbow_3000lb_SW.csv` | `PSize;OD;BendAngle;A;C;D;E;G;Conn` |
| `Tee_3000lb_SW.csv` | `PSize;PSizeBranch;OD;OD2;A;C;D;E;G;Conn` |
| `Coupling_3000lb_SW.csv` | `PSize;PSize2;OD;OD2;A;C;D;E;Conn` |
| `Union_3000lb_SW.csv` | `PSize;OD;A;C;D;E;Conn` — **no header row** (§6) |

`A` is centre-to-face, **`E` is centre-to-socket-bottom**, `D` the bore, `C` the
socket boss wall, `G` the inner body wall. Pass `rating="3000lb"` and set
`PRating` afterwards, as for every other maker (Golden Rule 6).

**The ports sit at the bottom of the socket pocket, not at the fitting face.**

- **SocketEll:** `Ports = [(E,0,0), (−E·cosBA, E·sinBA, 0)]`, outward dirs
  `(1,0,0)` and `(−cosBA, sinBA, 0)`; **work point at the local origin.** This
  is a *different* local frame from the butt-weld `Elbow`, whose port 0 is at
  `(0,BR,0)` — do not carry an orientation helper across from one to the other.
- **SocketTee:** `Ports = [(0,0,−E), (0,0,E), (0,E,0)]` — run on local ∓Z/±Z
  (ports 0/1), branch on local +Y (port 2), work point at the local origin. Same
  tidy frame as the butt-weld `Tee`, so the three-axis
  `Rotation(xdir, ydir, zdir)` places it directly (§9.3).
- **SocketCoupling / SocketUnion:** `Ports = [(0,0,−(A−E)), (0,0,A−E)]`, centre
  at the local origin, overall length `2A`. On a *reducing* coupling port 0 is
  the `PSize` end and port 1 the `PSize2` end — orient it deliberately, because
  getting it backwards is invisible in a wireframe.

Two things to exploit and one to report:

1. **Span the ports and you get the true cut length, engagement included.** A
   pipe built as `(portA_world − portB_world).Length` runs socket-bottom to
   socket-bottom, which is exactly what the fabricator cuts. That is what lets
   §9.2's "place at work points, derive the pipes" survive a change of fitting
   class (§12.8).
2. **`makeSocketElbow` drops port 0 at `pos`, not the work point.** It rotates
   port 0's local direction onto `Z`, then translates so port 0 lands at `pos` —
   unlike `makeElbow`, whose `pos` *is* the work point. When placing by work
   point, ignore the `pos`/`Z` arguments and set `.Placement` yourself after a
   `recompute()`.
3. **The tables are thin in places, and that is a report item, not a bug.** A
   reducing coupling row carries a *single* `A` and `E`, so the small end is
   modelled with the large end's socket depth; and `Union_3000lb_SW.csv`'s DN15
   row repeats the coupling's dimensions, so the modelled union is
   coupling-length and visibly shorter than a real one. Say so rather than
   letting the user find it.

### 3.4 Eccentric reducers

`makeReduct(..., conc=False)` builds an eccentric reducer. Its local frame is
not the concentric one, and `alignTwoPorts` will not give you the flat side
where you want it:

- **Port 0 is the large end at the local origin. Port 1 is the small end at
  `((OD − OD2)/2, 0, H)`.** Both port directions are along ∓Z.
- **The flat side is local `+X`**, the line `x = OD/2` along the whole
  length. The small end is offset toward it.
- **Flat on bottom (FOB)**, which is what a pig launcher wants: map local
  `+X → −Z`. For a run along world `+X` with the small end mating a pipe's
  port 1, local Z must point `−X` (anti-parallel to the pipe's port
  direction):

  ```python
  R = Rotation(-Zhat, (-Xhat).cross(-Zhat), -Xhat)          # (x, y = z×x, z)
  red.Placement = Placement(wpos(pipe, 1) - R.multVec(red.Ports[1]), R)
  ```

  Flat on top (FOT, for pump suctions) maps local `+X → +Z` instead.
- **The large-end centreline moves off the small-end centreline by
  `e = (OD − OD2)/2`**: 52.39 mm for 12"×8", upward for FOB. Every fitting
  downstream inherits that. A branch that has to meet a line still at the old
  elevation now has a level change to absorb. Solve it through the chain
  (§9.3.1) rather than moving the other line. Check the flat side really is
  flat by comparing the pipe bottoms either side (`z_CL − OD/2`). They should
  agree to the table's rounding of `OD2` (0.0025 mm here).

### 3.5 Pipe supports

**First decide whether Quetzal's makers fit the support at all.** Quetzal
supplies three support-related makers: `makeBeam` (a structural section),
`makeUbolt` (a pipe clamp) and `makeBeamClamp` (a clamp onto a beam flange).
Together with `makePipe` for a post, these fit one family well: a **post-and-cap
support**. That is a vertical pipe post with a short wide-flange cap across the
line and a U-bolt round the line pipe. Steel frames built from standard sections
fit too.

Many supports are **not** that shape, and there is no maker for them. Examples:

- pipe shoes and saddles
- trunnions and dummy legs
- guides and line stops
- spring or rod hangers
- fabricated brackets
- concrete sleepers

Model these as plain `Part::Feature` solids (`Part.makeBox`, `makeCylinder`,
extruded profiles). Place them from the line pipe's geometry, meaning its
centreline and `OD/2`, never from a guessed elevation. Do not force a beam
section to stand in for a shoe, or a U-bolt for a band clamp. A substitute that
looks roughly right is harder to spot as wrong than a plain block that is plainly
a placeholder. Whichever method you use, say which one in the report.

Ask before modelling supports at all. Supports are often painted like the
piping, but they are structure, not piping, and the user may not want them. A
temporary construction stand (a jack stand or tripod under a valve) will be
removed, so it does not belong in the model even when it is in the photo.

#### Post-and-cap support with the Quetzal makers

| Part | Maker | Table | `propList` |
|---|---|---|---|
| Cap beam | `pCmd.makeBeam(propList)` | `Beam_W.csv`, `Beam_HEA.csv` | `[rating, SSize, stype, H, W, ta, tf, Height]`, where `Height` is the beam length |
| Post | `pCmd.makePipe(rating, propList)` | `Pipe_<sched>.csv` | `[DN, OD, thk, H]`, the same as a line pipe |
| U-bolt | `pCmd.makeUbolt(propList)` | `Clamp_DIN-UBolt.csv` (`PSize;C;H;d`, DN20–DN500) | `[PSize, "DIN-UBolt", C, H, d]` |

**`Beam_S.csv` differs from the other beam tables.** Its header spells the key
**`Psize`** (lower-case `s`) and **`Stype`**, and it has **no `tf` column**. A
lookup keyed on `PSize` silently finds nothing there, and `makeBeam` needs a flange
thickness the table does not carry. Prefer `Beam_W` or `Beam_HEA`. If an S-shape
is really needed, ask the user for `tf` rather than inventing one. The
`Section_*.csv` files are a different path, the FrameLine and Arch-profile
tools. Don't mix them up with `makeBeam`.

**`Beam` geometry.** The section is centred on the local Z axis and extruded
along local +Z from `0` to `Height`. Ports sit at `z = 0` and `z = Height`, facing
−Z and +Z. For `stype = "H"` the **flanges lie at local ±Y**, so the depth `H` runs
along local Y and the web lies in the local YZ plane at `x = 0`. The object sets
`FType = "Beam"` but no `PType`. To get a horizontal cap with its web vertical,
lying along `axis`, map local Y to world Z and local Z to `axis`:

```python
across = Zhat.cross(line_axis); across.normalize()   # cap runs across the line
Rb     = Rotation(Zhat.cross(across), Zhat, across)  # (x, y = depth -> Z, z = beam axis)
top_z  = line_CL.z - line_OD / 2                     # top flange carries the pipe
mid    = Vector(line_CL.x, line_CL.y, top_z - H / 2)
beam.Placement = Placement(mid - Rb.multVec(Vector(0, 0, L / 2)), Rb)
```

Put the post on the same vertical, running from grade (or its base plate) to
`top_z − H`. Derive its length from those two elevations, not from a constant.

**`Ubolt` geometry, and why it cannot be seated by ports.** The arc (diameter `C`)
lies in the local XY plane about the origin and passes over local +Y. The legs run
down to `y = C/2 − H`, and the rod diameter is `d`. The object has
`PType = "Clamp"`, a single meaningless port (`(0,0,1)`) and **no
`PortDirections`**, so `alignTwoPorts` cannot seat it. Set its `Placement`
directly, with the origin on the line-pipe centreline, local Z along the pipe and
local Y up:

```python
ub.Placement = Placement(line_CL_point + line_axis * UBOLT_OFFSET,
                         Rotation(Zhat.cross(line_axis), Zhat, line_axis))
```

Two things to account for:

- **Keep the U-bolt off the web.** A cap that crosses the line directly under its
  centreline has its web in the same vertical plane as the U-bolt legs. A U-bolt
  centred over the support therefore drives both legs into the web. A real U-bolt
  passes through the top flange *beside* the web, so offset it along the pipe
  axis by at least `ta/2 + d/2`, keeping it inside the flange width. Keep the
  offset as a named constant.
- **The DIN arc stands off the pipe.** Quetzal's own insert form centres the arc
  on the pipe axis. `C` is larger than the pipe OD, so the rod's inner face clears
  the pipe instead of gripping it: 2.84 mm at DN50, where `C/2 − d/2 = 33` against
  `OD/2 = 30.16`. That is a property of the table, not a placement error. Mention
  it rather than shifting the U-bolt down to touch.

`makeBeamClamp` (`Clamp_Beam.csv`, vendor beam clamps keyed by product code) is
for clamping *to* a beam flange. Read its docstring and table before using it,
because its columns (`Y;X;V;T;W`) are vendor dimensions, not a pipe size.

**What verification looks like for a support.** A clean support shows:

- `distToShape` = 0 from beam to line pipe, and from post to beam: they touch
  without cutting in;
- the post's bottom at the grade elevation;
- one U-bolt-to-beam overlap equal to `2·π·(d/2)²·tf`. That is the two legs
  through the top flange, because the beam object does not cut bolt holes. For
  DN50 on a W6x15 it is 1429.4 mm³. Any larger value means the legs are in the
  web: check the offset above.

Mark supports `[S#]` and U-bolts `[U#]`. The beam has no `PType` to map from, so
assign the prefix explicitly (§9.6).

---

## 4. Flanges (the tricky one)

`propList` positional order (matches `Flange.__init__` in `pFeatures.py`):

```
[DN, FlangeType, D, d, df, f, t, n, trf, drf, twn, dwn, ODp, R, T1, B2, Y]
```

- `D`=flange OD, `d`=bore, `df`=bolt-circle dia, `f`=bolt-hole dia,
  `t`=flange thickness, `n`=#bolts, `trf`/`drf`=raised-face thickness/dia,
  `twn`=weld-neck length, `dwn`=hub dia, `ODp`=matching pipe OD,
  `R`=hub fillet, `T1`=hub height, `B2`/`Y`=socket bore/depth (SW only).
- **`FlangeType`** is the connection style, NOT the face. Values:
  `WN` (weld-neck), `SO` (slip-on), `SW` (socket-weld), `LJ` (lap-joint),
  `BL` (blind). **RF (raised face) is implied by non-zero `trf`/`drf`**, not a
  type. All `Flange_ASME-*-RF-*` tables are raised-face.
- **For a welded spool, use `WN`.** A "Schedule NN" flange spec means a WN
  flange bored to that schedule.
- **WN bore rule:** compute `d = pipe_OD - 2 * pipe_wall_thk` (from the pipe
  schedule table), *not* the flange CSV `d` column. Match `insertFlangeForm`.
- **For WN, pass `rating=<schedule>` (e.g. `"SCH-40"`) and `fclass=<class>`
  (e.g. `"600lb"`).** The schedule drives bore/port helpers; the pressure class
  goes to `obj.FClass`. For non-WN types, `rating="No rating"`.
- **Pass `doOffset=True` when you will position with `alignTwoPorts`**, so
  `makeFlange`'s automatic type-based Z-offset doesn't fight your placement.

CSV column order differs from `propList` order — always map by column **name**,
never by position. Example WN 600# file `Flange_ASME-WN-RF-600lb.csv` columns:
`PSize;FlangeType;D;d;t;T1;dwn;twn;t1;ODp;R;f;n;df;drf;trf`.

**Column sets differ by flange type**, so don't assume a column exists: WN carries
`dwn/twn/R/T1`; SO has fewer (no neck columns); BL has **no bore** at all and adds
an `FClass` column. Read each row by column name and **default any missing column
to `0`** — that's exactly what `insertFlangeForm` does.

---

## 5. Ports and connecting parts

Every pype object exposes two parallel local-coordinate lists:
`obj.Ports` (Vector positions) and `obj.PortDirections` (outward unit vectors).
There is **no persistent joint object** — connecting is a one-time `Placement`
computation.

Port conventions (verify in `pFeatures.execute()` when unsure):
- **Pipe:** port 0 at `z=0` (dir `-Z`), port 1 at `z=H` (dir `+Z`).
- **WN flange:** port 0 = raised face at `z=-trf` (dir `-Z`, points outward);
  port 1 = weld end at `z=+T1` (dir `+Z`, mates to pipe).
- **SO flange:** port 0 = raised face at `z=-trf`; port 1 = pipe end at `z=+trf`.
- **Blind (BL) flange:** port 0 = raised face at `z=-trf`; port 1 = back face at
  `z=+t`. Mates to a gasket/flange via **port 0**.
- **Gasket:** ports at `z=0` and `z=+SEthk` (dir `-Z`/`+Z`); mates via **port 0**.
  `Bolts_Nuts` likewise connects via **port 0**.
- **Elbow:** ports are **NOT on the Z axis** —
  `Ports = [Vector(E,0,0), Vector(-E·cosBA, E·sinBA, 0)]` with **port 0 pointing
  local +X**. Mate the inlet with index **0**; continue the run from port **1**.
- **Outlet (weldolet/sockolet):** a **single** port (index 0) at the branch
  outlet end, dir `+Z` outward in local frame.
- **Valve (flanged):** port 0 at `+H/2` (dir +Z), port 1 at `−H/2` (dir −Z) — the
  two flange faces.

> **Never assume a part's ports lie on the Z axis.** Elbows, tees, and outlets
> have off-axis ports, so hand-computed Z placement silently produces wrong
> geometry. Always position with `alignTwoPorts`, which reads the actual port
> vectors and rotates the part for you.

Mate with:

```python
pCmd.alignTwoPorts(obj2, port2, obj1, port1)
# Moves obj2 so its port `port2` meets obj1's port `port1`, face-to-face
# (directions anti-parallel). obj1 stays put.
```

**Recompute before you align.** `alignTwoPorts` reads `Ports`/`PortDirections`,
which only exist after `execute()`. Call `doc.recompute()` after creating a part
and before aligning it. (`makeFlange` recomputes internally; `makePipe` does not.)
Skipping this throws `list index out of range` from the empty `Ports` list.

Spool pattern (flange on each end of a pipe):

```python
pCmd.alignTwoPorts(flangeA, 1, pipe, 0)   # weld end -> pipe near end
pCmd.alignTwoPorts(flangeB, 1, pipe, 1)   # weld end -> pipe far end
doc.recompute()
```

Build chained runs by aligning each new part's inlet port to the previous
part's open outlet port, in order. Keep one part stationary (e.g. the first
pipe) and mate everything else to it — since `alignTwoPorts` only moves `obj2`,
the anchor part stays at the origin throughout.

**Cap-off recipe** (bolt a blind flange onto an existing flange face):

```python
pCmd.alignTwoPorts(gasket, 0, flange, 0)   # gasket face -> flange raised face
pCmd.alignTwoPorts(bolts,  0, flange, 0)   # bolt set spans the joint
doc.recompute()
pCmd.alignTwoPorts(blind,  0, gasket, 1)   # blind face -> gasket far face
```

---

## 6. Dimension tables (`tablez/`)

Semicolon-delimited, `utf-8-sig`, key column = `PSize` (DN label).
Filename conventions encode the rating/class:
- Pipe: `Pipe_SCH-40.csv`, `Pipe_SCH-80.csv`, … (cols `PSize;OD;thk`).
- Flange: `Flange_ASME-<TYPE>-RF-<class>lb.csv`
  (e.g. `Flange_ASME-WN-RF-600lb.csv`, `-SO-`, `-BL-`).
- Elbow: `Elbow_SCH-STD_LR90.csv`, etc.
- Bolts/Gaskets: `Bolt_600lb.csv`, `Gasket_600lb.csv`.

So `rating="SCH-40"` ↔ `Pipe_SCH-40.csv`, and `fclass="600lb"` ↔ the `-600lb`
flange file. `pCmd.readTable("<file>.csv")` returns `list[dict]` if you prefer
it over rolling your own reader.

**Fitting tables do not cover every pipe schedule.** There is no
`Elbow_SCH-40*.csv` and no `Reduct_SCH-40.csv` — fittings are tabulated as
`SCH-STD` / `SCH-XS` / `SCH-XXS`. For a SCH-40 line, use the **`SCH-STD`**
fitting files: the wall thicknesses are identical up to DN250 (DN80 5.49,
DN100 6.02). Say so in the build's comments and report rather than leaving it
implicit.
Elbow variants are `_LR90`, `_SR90`, `_LR45`; note the **`LR45` `BendRadius` is
pre-scaled** (DN100 = 154.51, not 1.5·D), so always take the take-out from the
formula `E = BR·tan(BA/2)` — 64.0 for that row, not 154.51.

**`Reduct_*.csv` uses `>`-separated multi-value columns.** One row per major
size; `PSize2`, `OD2` and `thk2` each hold a `>`-joined list that must be split
and indexed **together**:

```python
idx = [s.strip() for s in row["PSize2"].split(">")].index("DN80")
OD2, thk2 = float(row["OD2"].split(">")[idx]), float(row["thk2"].split(">")[idx])
```

**Some tables need a two-column key.** `Tee_*.csv` is keyed on `PSize` +
`PSizeBranch`, and `Coupling_*_SW.csv` on `PSize` + `PSize2`. A lookup on
`PSize` alone silently returns the first row for that size — which in
`Coupling_3000lb_SW.csv` for DN20 is the straight DN20×DN20, *not* the DN20×DN15
reducer you asked for, because the reducing rows sit after all the straight
ones. Match on every key column.

**And one table has no header row at all.** `Union_<class>_SW.csv` starts
straight in on data, so `csv.DictReader` eats the first size as the header and
every later lookup misses. Read it positionally against `PSize;OD;A;C;D;E;Conn`.

**Read every column by name with a default**, because column sets differ between
files of the same family (§4). A tolerant accessor is worth the six lines:

```python
def _f(row, key, default=None):
    v = row.get(key, "")
    if v is None or str(v).strip() == "":
        if default is not None:
            return default
        raise KeyError(key)
    return float(v)
```
