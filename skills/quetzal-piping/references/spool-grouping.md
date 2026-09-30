# 14. Grouping a finished model into spool part containers

Directions for organising an **existing** Quetzal model into `App::Part`
containers, one per spool piece, plus an assembly-material container. Optionally
one more level up: one container per header or system. The geometry already
exists and is correct. Nothing here may move it.

Read §2.1 first (target document, transaction, the bridge's autosave). This is
a change to the user's own open file, which is the case §2.1 is most careful
about.

## 14.1 What the user is asking for

Requests come in a few shapes. Ask only about what the prompt leaves open.

- **Flat:** "group into spool containers plus one assembly-material container."
  One level of parts.
- **Nested:** "one container per header; inside each, sub-containers per spool
  plus an assembly-material container." Two levels.
- **A follow-up that moves things:** "the blinds and vent stubs on top of each
  valve stack go to assembly material instead."

The default classification below is the working convention. A user's stated
rule overrides it, and a later correction overrides the first answer, so keep the
rules in one function (§14.3) that you can change and re-run.

## 14.2 What is a spool, and what is assembly material

A **spool** is a welded piece: everything joined by shop welds. It ends at each
flanged joint, where a gasket and studs sit between two flange faces.

| Goes in the spool | Goes in assembly material |
|---|---|
| Pipe, elbows, bends, tees, reducers | Gaskets (`PType == "Gasket"`) |
| Flanges welded to a fitting (WN, SO), including both sides of a flange pair | Stud sets (`PType == "Bolts_Nuts"`) |
| Sockolets, weldolets, TOR outlets and their socket caps | **Flanged** valves (`PType == "Valve"`, `PRating != "Ball_Threaded"`) |
| Nipples, stubs and **threaded** valves hanging off an outlet | Blind flanges (label ` BL `), and when the user says so, the nipple and threaded valve tapped into them |
| | Anything else the user names |

Nipples and threaded valves are on the spool by default, because they are shop
welded to it. The exception is the blind-flange vent: a blind flange is bolted
on, so the blind and the stub and valve on it are field material, and the user
may ask for them to be moved. Follow the user's wording. Do not decide it.

**Pipe supports** (beams, plates, posts, U-bolts) are not spool pieces and are
not assembly material. If the model has them and the prompt does not say where
they go, put them in their own `Supports` container per system and say so at
handover, so the user can dissolve them if unwanted.

## 14.3 Read the model first, read-only

Before creating anything, list what is there. Object `Label` prefixes are
marks (`[F1]`, `[P7]`, §9.6), and `PType`, `PRating`, `PSize` say what each
object is. Objects without `PType` (support beams) need `getattr`.

```python
import re, itertools
doc = FreeCAD.ActiveDocument
def tag(o):  return o.Label.split("]")[0][1:]           # "[F1] Flange ..." -> "F1"
PT = lambda o: getattr(o, "PType", "")
print(len(doc.Objects), [o.Name for o in doc.Objects if o.TypeId == "App::Part"])
for o in doc.Objects:
    print(o.Name, "|", o.Label, "|", PT(o), getattr(o, "PRating", ""), getattr(o, "PSize", ""))
```

Also check for existing `App::Part` / `App::DocumentObjectGroup` objects. A model
that is already grouped needs a decision (extend, or rebuild), not a second
layer piled on top.

Object counts include each part's own `Origin`, axes and planes (9 objects per
container). Exclude them when you count members and when you look for orphans.

## 14.4 Finding the spools from connectivity

Do not guess spools from marks or from label text such as "flange pair". Derive
them from the ports, the same way §10.2 checks joints. Two objects are welded
when a port of one coincides with a port of the other (within 1 mm). Group the
non-assembly objects with a union-find, and every connected set is a spool.

```python
def isasm(o):                                   # the §14.2 table, in one place
    return (PT(o) in ("Gasket", "Bolts_Nuts")
            or (PT(o) == "Valve" and o.PRating != "Ball_Threaded")
            or (PT(o) == "Flange" and " BL " in o.Label))

mains = [o for o in doc.Objects if not isasm(o) and getattr(o, "Ports", None)]
pts   = {tag(o): [o.Placement.multVec(p) for p in o.Ports] for o in mains}
par   = {t: t for t in pts}
def find(x):
    while par[x] != x: x = par[x]
    return x
for a, b in itertools.combinations(pts, 2):
    if any((p - q).Length < 1.0 for p in pts[a] for q in pts[b]):
        par[find(a)] = find(b)
```

Two things do **not** connect this way, and both need handling:

1. **Branch outlets.** A sockolet, weldolet or TOR is welded to the *wall* of a
   run pipe, so no port of the pipe touches it. Attach each outlet's port 0 to
   the nearest run pipe by distance to the pipe's axis segment. Exclude nipples
   and drop pipes from the candidates. Assert that the distance is plausible
   (it is roughly the run's outside radius plus the outlet's height, so a few
   hundred mm at most). A large number means it picked the wrong pipe.

   ```python
   def dseg(p, a, b):
       d = b - a; t = max(0, min(1, (p - a).dot(d) / d.Length**2))
       return (p - (a + d * t)).Length
   ```

2. **Socket caps and other port-less objects.** `SocketCap` has no useful
   `Ports`. Attach it to the outlet it touches, by placement distance.

Then sanity-check the result before you build any container:

- The groups should match what a fabricator would draw: each ends at a flange
  face with a gasket beyond it.
- **A spool containing two flanged ends and a long run of pipe is normal.** A
  spool that appears to span a flange break is *not*. It means either the
  model welds through it, or a gasket is missing. Say so and let the user
  decide where it splits; do not split it silently.
- Every non-assembly, non-support object lands in exactly one group. Assert it.

## 14.5 Grouping by header or system first

When the model holds several headers or lines, bucket first and find spools
inside each bucket. A spool never crosses a header, and a flanged tie-in is
exactly where two headers meet.

- Bucket by the strongest cue available: the label text ("header A"), then
  shape colour (`ViewObject.ShapeColor`), then connectivity.
- **Decide where a shared joint's assembly material goes, and say so.** A tie-in
  flange pair has a gasket, studs and often a valve that belong to neither side
  of the joint. Follow the user's stated boundary ("the red line ending at its
  tie flange [F1]" means the flange is in the red line, and the gasket, studs
  and valve past it belong to the other header). Report the ambiguous ones.
- Assert that every object landed in exactly one bucket before you go on.

## 14.6 Creating the containers

```python
def mk(label, l2, parent=None):
    p = doc.addObject("App::Part", "Part"); p.Label = label; p.Label2 = l2
    if parent: parent.addObject(p)
    return p

doc.openTransaction("Group into spool parts")           # one undo (§2.1)
for i, g in enumerate(spools, 1):
    p = mk("Spool %02d" % i, ", ".join(g))
    for t in g: p.addObject(objs[t])
asm = mk("Assembly material", ", ".join(sorted(assembly_tags)))
for o in assembly: asm.addObject(o)
doc.commitTransaction(); doc.recompute()
```

- A new `App::Part` has an identity placement, so adding a Quetzal object to it
  does **not** move the object. Do not touch `Placement`.
- For the nested form, make the header container first and pass it as `parent`
  when making its sub-containers. `parent.addObject(child)` nests.
- **Name for a person.** `Spool A-01` (header letter, then a two-digit number),
  or `Spool 01` when there is a single system. Put the member marks in `Label2`
  so the contents are visible without expanding the tree. Sort spools along the
  flow or by centroid position, not in creation order.
- Keep the original object `Name`s and `Label`s as they are. Marks are how the
  user and every drawing find the parts (§9.6).

### Moving things between containers afterwards

Take the object out of its old container before you put it in the new one, or it
will belong to two:

```python
src.removeObject(o); dst.addObject(o)
```

Delete an emptied container with `doc.removeObject(part.Name)`. Its origin
objects go with it. Then **renumber** the remaining spools so the numbering has
no gaps, and rebuild `Label2` on the container that received the objects.

## 14.7 Verify

A clean run proves the code ran, not that the grouping is right (§8, §10.2).
In a separate call, print:

```python
parts   = [o for o in doc.Objects if o.TypeId == "App::Part"]
skip    = re.compile(r"^(Origin|X-axis|Y-axis|Z-axis|XY-plane|XZ-plane|YZ-plane)")
members = lambda p: [c for c in p.Group if not skip.match(c.Name) and c.TypeId != "App::Part"]
allobj  = [o for o in doc.Objects if o.TypeId != "App::Part" and not skip.match(o.Name)]
placed  = [c for p in parts for c in members(p)]
print("objects", len(allobj), "placed", len(placed), "unique", len(set(placed)))
print("orphans", [o.Label for o in allobj if o not in placed])    # want []
print([(p.Label, len(members(p))) for p in parts])
```

- `placed == unique == objects`: nothing dropped, nothing in two containers.
- Compare each container's count with your plan, and with the classification
  table in §14.2.
- Nothing moved: the geometry was not changed, but a reader will ask. Compare
  each object's `Shape.BoundBox` centre before and after if in doubt.

## 14.8 Handover

Report, briefly:

- the containers and how many members each holds;
- every judgement call: where supports went, where shared tie-in material went,
  what a spool that spans a flange break was left as;
- that nothing was saved (or that the bridge's autosave was on and may already
  have written the user's file, §2.1);
- that the change is one undo.

Do not write a `.py` file for this unless asked (§7.1).
