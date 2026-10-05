# Building the simplified model

Part of the `scan-to-model` skill.

## Macro shape

- **A constants block first.** Each constant gets a comment tagging its source
  (`SURVEY`, `SCAN`, `PHOTO`, `USER`, `NAMEPLATE`, `ASSUMED`) and its error
  bar. Plan values stay in the survey's units (feet or metres) when they come
  off a survey, and heights are in mm. Helpers `P(x, y, z_mm)`, `box(...)`
  and `prism(polygon, z0, z1)` keep the build readable.
- **`build()`** closes and recreates its own document. It never touches the
  scan document.
- **Containers.** Put objects in `App::Part` containers by class, with plain
  colours: `Buildings`, `Structures` (racks, platforms, stairs), `Tanks`,
  `Equipment`, `Piping`, `Foundations`, `Paving`, `Fences`, `Terrain`,
  `Survey`, and so on. The aligned scan goes in as a hidden `Mesh::Feature`.
- **Data file.** The macro reads only the analysis `.npz` (matrix, calibration,
  terrain grid). Rerunning the analysis and then the macro must reproduce the
  model.

## Element recipes

The aim is solids whose dimensions you can defend, not a detailed copy.
Model each element at the level the scan supports, and call anything coarser
an envelope.

### Buildings and enclosures

| Element | Build | Notes |
|---|---|---|
| Building footprint (control or MCC building, metal building, shelter, block house) | `prism(footprint)` from survey vertices, or from fitted wall faces where the survey does not show it | Projections and recesses come from the survey, confirmed by the face profile |
| Low-slope or flat roof | Box or thin prism on the wall tops, with the parapet as thin wall boxes | The roof itself is rarely scanned. Take the height from the wall tops only if a photo confirms they are not the range limit |
| Gable roof (metal building, shelter) | Triangle in the end plane, extruded along the ridge. Cut it with the same prism dropped by `t / cos(pitch)` to leave a thin shell, and add the gable-end triangles as wall solids | Pitch from a photo (§Heights from a photo). A solid roof prism draws the gable end in roof colour |
| Hip roof | `Part.Solid(Part.Shell(faces))` from five planar faces: the eave rectangle, two end triangles and two side trapezoids. With equal pitch, the ridge length is length − width (overhangs included) | A scan that catches the roof shows the hips as facets tilting along the ridge axis at the ends |
| Openings (personnel and roll-up doors, louvres, windows) | For each opening: a recess box cut from the wall solids (100 mm), a 20 mm panel at the back coloured by kind, and an optional trim ring proud of the face | Define openings as `(wall, u0, u1, z0, z1, kind)` against a table of wall planes, so a wall that steps is just another plane. A `centred(wall, u_c, (w, h), z_c, kind)` helper lets a user's size replace a scanned one without moving the opening |
| Small canopy or hood | Prism extruded from the wall | |

### Tanks, vessels and equipment

| Element | Build | Notes |
|---|---|---|
| Vertical tank | `makeCylinder` for the shell, with a `makeCone` (cone roof) or a spherical cap (dome roof) on top | Fit the diameter to the shell facets in several height bands, and check it holds. `find_trunks` works with a raised `band` and `max_extent` above the tank diameter. A nameplate or the user's tank data beats the scan. The shell top is often past the scan ceiling, so take it from a photo |
| Horizontal vessel or bullet | Cylinder for the shell, with heads as flattened spheres (2:1 ellipsoidal) or hemispheres, on saddle boxes | Fit the axis and diameter from the shell facets. Head type comes from a photo. Tan-to-tan length is the shell length |
| Equipment (pumps, compressors, skids, transformers, coolers) | Envelope box per unit, or a few boxes for the main parts (driver, driven unit, base) | Name each one as an envelope in the report. Nameplate or vendor data, if the user has it, replaces the scanned envelope |
| Foundations, pads, sleepers | Boxes from below grade to the scanned top of concrete | Bound the top by its edges in the plan plot, not by the percentile of everything at that height (SKILL.md). Centre equipment on its foundation only if the scan agrees |

### Structures

| Element | Build | Notes |
|---|---|---|
| Pipe rack or structural frame | Columns as boxes the size of the member, and beams as boxes between column centres at each tier's top-of-steel | Fit column positions with a circle or box fit in plan, and tier heights from the down-facing facets under the beams. Don't snap to a regular bay spacing unless the user confirms it |
| Platforms and walkways | Box for the deck at the scanned top of grating, posts and toe plate as thin boxes | Grating is partly see-through to LiDAR. Take the deck top as the median of the up-facing hits, not the maximum |
| Stairs and ladders | A stepped prism or an envelope prism for a stair, and a thin box for a ladder and its cage | Count the treads in a photo if the scan blurs them |
| Handrails | Thin boxes or small cylinders along the edge polyline at the standard height | Standard height is `ASSUMED` unless scanned |
| Poles, posts, bollards, light standards | `makeCylinder` from the circle fit | `find_trunks` finds them, along with trees. Classify them first (SKILL.md) |

### Piping

| Element | Build | Notes |
|---|---|---|
| Above-ground piping to be worked on | Get the centreline and OD from the scan, snap the OD to a nominal size, then build it with Quetzal (`quetzal-piping` skill), not with Part cylinders | Fit a cylinder to each straight run from its facets. Elbow positions come from the intersections of straight-run axes. The user's line list or isometric beats the scan for size, schedule and class |
| Background piping (context only) | Part cylinders along the fitted axes, in a `Piping` container, coloured as context | Say in the report that it is not a Quetzal model |
| Small-bore lines, tubing, conduit | Usually not resolved by a handheld scan (below about 2"). Leave them out or trace them from photos, and list them as omitted | |

### Site

| Element | Build | Notes |
|---|---|---|
| Roads, gravel and paved areas, thin paths on terrain | Quad prisms along a breakpoint polyline `(y, x_left, x_right)`, in pieces of about 1.5 m or less, each topped just above the **highest** terrain point under it | A flat piece set on the mean height sinks into the ground in places, and the ground shows through it |
| Curved edges drawn on the survey | Edges traced row by row from the survey image (calibration.md §Tracing), built as above | A 4-point hand trace comes out lumpy and uneven |
| Containment berms and dike walls | Quad prisms along the wall's polyline, from the outside grade to the scanned top | Report the inside floor height and the contained volume if asked |
| Fence | Thin box, or a quad prism between two survey ties. A chain-link fence often scans as posts only, so model the posts and a thin transparent panel | Top from the median of a clean scanned run. Check it is not a hedge first (SKILL.md) |
| Boundary, setback, clearance or classified-area line | A vertical `Part.Face` along the line, from the mean grade (the mean of the terrain grid inside the surveyed area) to the height asked for, in its own `Survey` container, about 70% transparent. A volume (a hazardous-area zone, a clearance envelope) is a transparent solid | Report what crosses it |
| Tree | `makeCylinder` for the trunk from below grade to the scan ceiling | Say the top is the range limit, not the tree height |
| Unidentified structure | Envelope boxes, 50% transparent | Name it in the report as an envelope |
| Terrain | `Part.BSplineSurface().interpolate(grid)` then `face.extrude(-300)` | A grid at 400 mm met a p95 of about 25 mm on gently sloping ground. Use a smoothed grid only |

## Heights from a photo

The scan has a height ceiling (SKILL.md), so the tops of tall elements
(building roofs, tank shells and roofs, stacks, upper rack tiers) usually
come from a photo. The method, for a photo taken roughly square to a face:

1. **Vertical scale on a reference plane.** Use two heights the scan measured
   on one plane facing the camera, such as a door threshold and a scanned
   beam or soffit: `s = Δpx / Δmm`. Applied to another scanned edge on that
   plane, it should reproduce the scan's height to about 10 mm. Check that
   before you trust it.
2. **Depth scale.** An element further from the camera than the reference
   plane appears smaller. Scale by the ratio of a length that is equal at
   both depths: `s_r = s · L_far_px / L_near_px`. On a gable roof that is the
   ridge against the eave. On a tank it is the diameter at the top against
   the diameter at the scanned band.
3. **Horizon from an assumed camera height** (eye level above the grade at the
   camera): `y_h = y_ref + s·(z_ref − z_cam)`. Then
   `z_top = z_cam + (y_h − y_top)/s_r`. A ±300 mm camera-height error moves the
   result only about ±75 mm. Edge pixels that are hidden or blurred dominate
   the error, which comes to about ±250 mm.
4. **Roof pitch** = (ridge − eave) / (half depth + overhang). Round it to a
   common pitch and state the measured value.

Photos from other sides are for **identification**, not measurement. Use them
to settle roof form, head types, ladder versus stair, and which equipment is
which. Ask the user for them early. An older photo is fine for form, but not
for anything that may have been changed since.

## Dimensions the user gives you

- **A user's measurement replaces the scan's number but not its position.**
  Keep the scanned centre and apply the given size. The same goes for
  nameplate data and vendor drawings: a tank diameter from its data sheet
  replaces the fitted one, about the fitted centre.
- **"Identical" means shared elevations too.** Put identical items (columns
  in a row, matching pumps, a row of openings) on one elevation: the mean of
  their scanned values. Do the same for spacing when the user says they are
  evenly spaced.
- **Clearances from a feature** (a stated distance from a column line, a
  tank shell or a corner) are offsets from that feature's face or
  centreline. Build them as expressions of the feature's constant, so the
  dependent item moves if the feature does.
- **When two given numbers over-determine a dimension** (two edge offsets
  plus a width that don't add up to the slab), keep the stated size, centre
  it between the offsets, and report the residual.
- **When two statements can't both hold**, say which two and ask. Don't pick
  one silently. Translate compass words through the true north first
  (calibration.md §The site frame). Once corrected, many apparent
  contradictions disappear.

## Proposed changes (design mock-ups)

Asked to mock up an addition or alteration on the as-built model (new
equipment, a building extension, a new pipe run or rack tier):

- Gate it with one flag (`ADDITION = True`) and build it in a function of its
  own, into its own `App::Part` container, in a distinct colour so it reads as
  a proposal. New piping is built with the `quetzal-piping` skill, into that
  container.
- **Never alter the existing elements.** Build every replacement (moved/modified
  elements) inside the proposal container. Keep the originals
  in their own containers, and only hide them while the proposal is shown.
  List them in a constant (`ADDITION_REPLACES`).
- Provide a `show_<proposal>(on)` function that swaps the two sets. A
  `Visibility` expression (`Addition.Visibility ? 0 : 1`) is accepted, but it
  does **not** re-evaluate when the container is toggled, so it can't do the
  swap. Tell the user that toggling the container by hand won't hide the
  originals.
- Derive dependent dimensions from the constraint, not from a number. "Edge on
  the setback line" means `wall_y = line_y + overhang`, so a later overhang
  change keeps the edge on the line.
- Check: zero gap and zero overlap (`distToShape`, `common`) where the
  proposal should touch existing elements (a foundation, a rack, a tie-in),
  and clearance where it should not: existing structures, piping, equipment,
  access ways, and any boundary or clearance line.
- Keep a "Proposed" section in the report, separate from existing
  conditions, with each assumed value (heights, sizes, spacings) as something
  the user can change.

## Checks specific to the build

- Rebuild from scratch after every constant change. The macro is fast (about
  1 s plus the mesh copy).
- Compare one built dimension per constant against its source. Survey ones
  should come out to 0.0 mm.
- Look at the model with the mesh overlaid, from at least two sides. Building
  edges, tank shells, rack tiers and pipe runs should sit on the scan
  wherever the scan reaches.
