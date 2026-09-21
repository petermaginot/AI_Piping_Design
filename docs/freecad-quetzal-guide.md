# AI-Assisted Piping Design with Quetzal

Directions for an AI agent that builds piping designs (spools, runs, assemblies)
with the **Quetzal** workbench, from a natural-language user prompt, by driving
the user's **live FreeCAD session over the MCP server**
([blwfish/freecad-mcp](https://github.com/blwfish/freecad-mcp)).

Read this end-to-end before you build. It captures the non-obvious rules that
make the difference between a model that is right and one that silently produces
wrong geometry or crashes.

> **This document was rewritten for the MCP workflow.** It previously described
> emitting a `.py` macro file for the user to run from **Macro → Execute**. You
> now build *directly* in their running FreeCAD via `execute_python`, and verify
> the result numerically in the same session before saying you are done. The
> headless `ViewObject` shim that used to be the only way to test a macro is
> gone — §10 is now the live build-and-verify loop that replaced it.
>
> A macro file is still a perfectly good *deliverable* when the user asks for one
> (something to re-run, check into git, or hand to a colleague). What changed is
> that it is no longer the delivery *mechanism*: build and verify over MCP first,
> then write the file out only if it was asked for (§7.1).

---

## 1. Golden rules (read first)

1. **You build in the user's live GUI session, over MCP.** Quetzal's `execute()`
   methods set `fp.ViewObject.Deviation`, so `Pipe`/`Flange`/etc. only build
   geometry when a GUI ViewObject exists — headless `freecadcmd` fails with
   `'NoneType' object has no attribute 'Deviation'`. The MCP target *is* a GUI
   session, so this requirement is satisfied for free and needs no workaround.
   Build with `execute_python`, verify in the same session (§10), and show the
   user the finished model rather than instructions for producing it.
   **Confirm the session before you build** — `check_freecad_connection`, and
   check that the Quetzal workbench is loaded (§2).
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
print("docs:", list(FreeCAD.listDocuments()))
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
and then reload (`reload_modules`, or restart FreeCAD) before it takes effect.

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

Three MCP tools do the rest without any code of yours:

| Tool | Use |
|---|---|
| `geometric_verification` `verify_no_self_intersection` | Per-object OCCT validity |
| `spatial_query` `batch_interference` | All pairs at once |
| `spatial_query` `clearance` / `alignment_check` | A stated gap or alignment (§9.7) |

**Read `batch_interference` correctly.** Welded neighbours *touch*, so a
correctly built spool reports one "collision" per joint, each with **zero overlap
volume** ("sub-tolerance contact"). That is the pass signature, not a failure.
A real interference is a non-trivial common volume, and a pair that is *not*
adjacent in your chain showing contact is the genuine warning.

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
is saved unless asked, and no `.FCStd` is written into `Mod/Quetzal/`.

---

## 11. Building from a text prompt

The counterpart to §9. There the geometry is *on the sheet* and the work is reading
it; here the geometry is only as complete as the sentence, and the work is noticing
what the sentence left out. Everything in §§1–8 still applies.

A prompt can be complete on sizes, schedule, class, flange styles and lengths and
still be silent on four things that change the model. `reference/spool_prompt_template.md`
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
- **Save target** — whether to write an `.FCStd`, and where. Ask too whether they
  want a re-runnable `.py` alongside the live model (§7.1); the build itself is
  delivered in their session either way, so this is about what they keep, not how
  they get it.

Everything else: pick the obvious reading, build it, and name the choice in the
report.

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
  written to disk.

---

## 12. Building from a field photograph

The third input mode. §9 has a drawing whose geometry is *stated*; §11 has prose
whose geometry is *described*; here the geometry is **visible but unmeasured**,
usually with a marked-up photo naming the components. Everything in §§1–8 applies,
and §9's work-point method is still how you build — what changes is where the
numbers come from and how much you are allowed to claim about them.

### 12.1 Decode the annotation file before you read the photo

Annotated photos usually arrive as a PowerPoint-exported PDF, which carries the
callouts as **text plus leader-line vectors** — far more precise than reading them
off a rendered page, and it survives when no PDF rasteriser is installed. There is
real signal in the leader geometry: each arrowhead tells you *which* feature a
callout names.

1. Inflate the content stream (`zlib.decompress` of each `stream`…`endstream`).
2. Text is often hex-encoded against a subset font, so parse the **`ToUnicode`
   CMap** (`beginbfchar` / `beginbfrange` blocks) and map the codes back.
   Collect each `Tm` position with the `TJ` string that follows it.
3. Pull the leader paths (`x y m` / `x y l`) — the three-point group at one end is
   the **arrowhead**; its middle vertex is the tip.
4. Map each tip into photo pixels using the image's placement rectangle
   (`… re` clip + `cm` matrix), remembering PDF y runs **up** and image y runs
   **down**:

   ```python
   px = tip_x * W / page_w
   py = (img_top_pdf_y - tip_y) * H / img_pdf_h
   ```

Sorting the resulting features along the run gives you the component chain in
order, which is the topology — the single most valuable thing on the sheet.

**Get the photos out of the PDF yourself.** Do not assume a PDF rasteriser is
installed — reading the PDF as an image may just fail with *"pdftoppm is not
installed"*, and you still need the pixels to measure anything. You don't need
one: an embedded `/Filter/DCTDecode` image's raw stream **is** a JPEG file, so
write the bytes straight out (trim at the `FFD9` end-of-image marker) and read
each page's photo as an ordinary image.

```python
b = objs[img_obj]                                  # e.g. /Subtype/Image /DCTDecode
raw = b[b.find(b"stream") + 6:b.rfind(b"endstream")].lstrip(b"\r\n")
open("page4.jpg", "wb").write(raw[:raw.rfind(b"\xff\xd9") + 2])
```

**Re-decode from scratch when the user says they updated the sheet.** A revised
PDF often keeps the *same* image bytes and adds the new information as **vector
overlay** — a coloured polyline, a dimension, a route sketch. The image object
stays byte-for-byte identical while the page's content stream grows several-fold
(~1 kB to ~7 kB is typical for one added route), so diffing image sizes concludes
"nothing changed" and you miss the update. Look for stroke-colour changes
(`1 0.753 0 RG`) followed by `m`/`l`/`S` runs, and map those vertices through the
same image rectangle as the arrowheads.

Such an overlay is **vector art, not pixels**, so it is the most precise data on
the whole sheet — better than anything you can measure off the photograph. Treat
a user-drawn route as authoritative for topology *and* for station, and say so in
the report. Watch for P&ID-style symbols drawn into it: a **bowtie** is a valve,
and its drawn span is an independent check — measure it and compare against the
catalogue face-to-face for that size and class, which confirms the symbol's
identity and the scale in one step.

### 12.2 A leader arrowhead is a pointer, not a datum

It lands *somewhere on* the thing it names, not on that thing's work point. Using
arrowhead spacing as a station is the characteristic photo-reconstruction error,
and it is worth hundreds of millimetres: an arrow that lands on a valve/flange
cluster rather than the tee centreline behind it drags the whole station with it.

**Prefer a feature you can measure on the pipe itself** — a bend tangent, a girth
weld, a flange pair — and let the arrowheads establish *order and identity* only.
Where a direct weld ties two features together, derive one from the other
(§9.3) instead of measuring both.

### 12.3 Scale from a catalogue dimension, and state the error bar

There is no dimension line to trust. Establish mm/px from something whose true
size you already read out of `tablez/` — a flange OD is ideal, being large,
high-contrast and circular:

```python
PHOTO_SCALE_MM_PER_PX = 558.8 / 134.0   # DN300 600# flange OD / measured px
```

Then **say what that is worth**. Perspective, lens distortion and the run not
being parallel to the image plane put a photo-derived station at roughly ±15%,
which is a different kind of number from an iso dimension and must never be
reported as though it were one. Put every station in the §9.6 `DIMENSIONS` block,
print the scale basis in the report, and say plainly that they are estimates to be
replaced with field measurements.

**Look for a scale bar before you settle for catalogue scaling.** A plan view is
often a Google Earth / drone capture that carries a burnt-in scale bar (and a
`Camera: NNN m` altitude). Find its end ticks in pixels and you have a *directly
measured* scale — roughly ±5% rather than ±15%, and on a near-orthographic plan
view it is free of the perspective error that dogs an elevation shot:

```python
PHOTO_SCALE_TOP = 3000.0 / 148.0        # labelled "3 m" spanning 148 px
```

**Then use the two bases to check each other**, which is the closure check §9.1.2
gives you on a drawing and which a photo package otherwise lacks entirely:

- Scale bar → catalogue: measure a large known feature (a barrel or flange OD) in
  pixels, apply the bar's mm/px, and compare against the `tablez/` value.
  Agreement to a few percent validates the bar.
- One view → another: scale a span that appears in both views and use it to carry
  the plan-view mm/px onto the elevation view. That transferred scale should then
  agree with the elevation view's own catalogue-OD measurement.

Report both bases and the fact that they agree. Use the **plan view for
along-the-run stations** and the elevation only for elevations and ordering.

#### 12.3.1 Know the blur floor before you claim a measurement

Work out how many pixels the feature you want is *worth* before you try to
measure it. A JPEG at these scales has 2–3 px of edge blur, so a feature under
roughly 2× that cannot be measured at all, however you threshold it.

A 16"→12" reducer, for instance, is a step of only `(406.4 − 323.85)/2 = 41 mm`
in radius — around 3–4 px at typical package scales. Bottom-edge tracing and
half-max width profiling both return noise there, and that *is* the answer:
**the step is not resolvable.** The honest outcome is not a number but a flagged
assumption — the split between the two barrels rests on a leader arrow alone
(§12.2) while their *sum* is well supported, so say exactly that in the report
and point at the two constants to edit.

Say "this cannot be measured here" rather than reporting the output of whichever
method happened to return a plausible-looking value. Also resist reading a
diameter change off apparent width where the pipe is lit against a pale
background — pale gravel and white cladding defeat a brightness threshold, and
the "edge" you find will be the ground shadow.

#### 12.3.2 A tape measure in the shot beats every other scale

If the photographer laid a tape along the run, stop scaling from catalogue
dimensions — you have real dimensions, and they are **absolute stations** rather
than spans. `examples/photo_example/` is the worked case: the tape is hooked
over the cut end of the black 3/4" pipe in `dimension_2.png` and read again,
further along the same run, in `dimension_1.png`, so every fitting on both
sheets shares one datum and the chain falls out by subtraction.

- **Confirm the datum is shared before relying on it.** Two shots of one tape is
  the normal case, but a photographer who re-hooked between shots gives you two
  local spans instead. That is one question, and it changes every station.
- **Read the tape at magnification (§9.1.1), interpolating between two labelled
  inch ticks** rather than off one. On a tape read right-to-left the digits are
  upside-down, and `6`/`9` and `3`/`8` are exactly as ambiguous as on an iso.
- **Expect ±1/4" from parallax alone.** The tape lies on the ground; the
  centreline you want is half a diameter above it, and the camera is not
  overhead. Quote that error bar.
- **A dimension shot may show a different state of the assembly.** In
  `dimension_2.png` the 3/4" tee's branch is a bare nipple, while the annotated
  overview shows that branch carrying an ell and a second nipple. Take
  *stations* from the dimension shots and *topology* from the overview.

**Then use the tape to calibrate the overview photo** — the closure check
(§9.1.2) a photo package otherwise lacks entirely. Two tape-measured spans
appearing in the same wide shot give two independent px/inch figures; in the
worked example they came out 39.2 and 57.1 px/in over the far and near halves,
a 46% spread that is pure perspective. That spread is itself evidence the two
dimension shots share a datum, and fitting px/inch linearly along the run then
lets you interpolate a station for whatever the tape did not reach — there, the
reducing coupling at 20.8" — at roughly ±15% instead of a guess. Report which
stations came off the tape and which off that interpolation; they are different
kinds of number and the user will want to re-measure only the second kind.

### 12.4 What a photograph *can* tell you reliably

Some things read better off a photo than off a drawing — use them:

| Cue | What it settles |
|---|---|
| **Bolt-circle foreshortening** | Branch direction. A near-circular bolt circle means that flange axis points at the camera; a thin ellipse means it lies across the view. This is how to decide whether a branch runs horizontally away from you or straight up |
| **Girth welds** | Whether two fittings are welded directly together or have a pipe between them — decisive, and it changes the dimension chain (§9.3) |
| **Actuator position** | Gearbox/handwheel orientation, which you must then set explicitly (§3.2.1) |
| **Where the line meets grade** | Elevation of the run, and whether an end continues underground (model it as an open pipe end) |
| **Apparent diameter along the run** | Whether the run is roughly parallel to the image plane, i.e. how far to trust one uniform scale |

Edge-detection on the pipe silhouette is *not* worth the effort — grass, shadow
and background clutter swamp it. Crop and magnify (§9.1.1) and measure the
high-contrast machined features by eye instead.

### 12.5 Treat the spec file as partial until proven otherwise

A photo job's spec file is often a copy from another job, covering only one line
size and carrying stale fields. Reconcile it against the photo annotations before
building, and **report every conflict** rather than silently picking one:

- A spec covering only the small-bore line says nothing about the header — ask.
- A stale document name or a referenced sketch that does not exist is a signal the
  file was copied; do not honour it blindly.
- Where the spec and the annotation disagree (e.g. spec says SO flanges, the
  callout says WN), follow the annotation and §4, and name the conflict.

### 12.6 What to ask before writing any code

Batch these into one round (§11.2). For a photo the answerable-only-by-the-user
set is narrower but sharper than for prose:

- **Line spec for anything the annotations do not cover** — schedule and class.
- **Dimensions**: offer your photo-derived estimates *with the error bar* versus
  the user supplying real spacings. Most users will accept estimates once they see
  they are named constants.
- **End configuration** where the line disappears from view — one bend or two,
  buried continuation or terminated.
- **Branch direction**, if the foreshortening cue is not decisive.
- **Which way a branch leaves the ground plane**, for an assembly photographed
  lying flat. `+Z` (up, off the slab) and `−Z` (down through it, with the
  assembly propped on that leg) look nearly identical from above, and the
  giveaways — a shadow gap, what the thing is resting on — are exactly what a
  close-up crops out. Name both readings and ask. In the worked example this was
  the one thing the user had to correct after the build.

**Ask when two of the user's own statements cannot both be true**, and say which
two. The common shape is one callout placing a tee "just upstream of" a flange
while another says the ell connects *directly* to that flange — leaving no room
for the tee. Rather than silently picking one, quote the conflict; it usually
gets an answer in a single exchange. Use the same round to raise anything plainly
visible in the photo that the annotations never called out. A conflict you can
name is cheap to resolve; one you resolve silently becomes a wrong model that
looks deliberate.

### 12.7 Expect several correction rounds — that is the workflow, not a failure

A photo reconstruction converges over three or four passes. The user is reading
the model against a site they know and you don't, so budget for it and build to
absorb it:

- **Re-run the full numeric verification after every round** (§8, §10.2) — every
  port closure and every stated constraint, not just the joints you touched.
  Corrections interact: restoring a deleted pipe moves a valve that an earlier
  correction had aligned. Rebuilding from the corrected `DIMENSIONS` (§9.6) and
  re-verifying is cheap over MCP; assuming the rest of the model held is what
  costs you a round.
- **A correction to a correction is normal.** "There is no pipe there" becomes
  "I was wrong, it exists as a short section, and it carries a vent." Handle it as
  new information, not as something to relitigate: make the change, re-verify,
  move on. Solved constraints (§9.7) are what make that cheap.
- **Delete the scaffolding a correction obsoletes.** When a station becomes
  derived, remove its `DIMENSIONS` constant, its adjustment note, and any helper
  only it used. Stale report text is worse than none — it describes a model that
  no longer exists.
- **A late correction can introduce a size the spec never listed.** A ½" vent
  means DN15, which the spec file may never have mentioned. Check that the size
  is tabulated at the line's class across everything it needs — pipe, flange,
  gasket, bolts, outlet, valve — then say in the report that it was absent from
  the spec and what you matched it to.

### 12.8 Modelling a different fitting class than the one in the photo

"These are 150# threaded fittings; model them as 3000# socket-weld" is a normal
request — the photo is of what exists, the model is of what will be built. The
substitution changes every take-out, so the thing to hold fixed is the **work
points**, not the pipe lengths. Do what §9.2 already says and it costs nothing:

1. Put every fitting's work point at its photographed station.
2. Derive every pipe by spanning the placed fittings' world ports (§3.3).

The take-out difference then lands where it belongs — in the pipe lengths — and
you can say so with numbers rather than assurances. In the worked example all
five tape stations and all five branch legs reconciled at `delta = ±0.000000 in`
while the pipes came out at lengths nobody typed in. **Name in the report which
fitting class the geometry is and which one the photograph is**, because the two
are now different and only the report records that.

One corollary is worth stating, because it is the cheapest evidence that the
chain really is solved: since the geometry comes from the stations, a correction
to a fitting's *orientation* must change no pipe length at all. When that job's
3/4" tee branch was re-aimed from `−Y` to `−Z`, the rebuild produced ten
identical cut lengths. A correction that moves a dimension you did not touch
means the chain is not solved but tuned (§9.7).
