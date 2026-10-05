---
name: scan-to-model
description: Convert a 3D scan mesh (phone LiDAR or photogrammetry, e.g. a COLLADA .dae from 3d Scanner App or Polycam, OBJ, PLY) of a site, plant, facility or building into a simplified FreeCAD model of plain Part solids in the user's live FreeCAD session over MCP, calibrated to a plat of survey, drawing or tape dimensions. Covers ingest with texture colour, levelling and squaring, fitting a scan-to-survey transform, extraction of walls, slabs, tanks, vessels, racks, equipment envelopes, existing piping, terrain and trees, openings from wall elevations, using photos for what the scan missed (roofs, tank and stack tops), user correction rounds, boundary and clearance lines, and mocking up a proposed addition (equipment, a pipe run, a building) alongside the as-built model. Use when the user asks to turn a scan, mesh or point cloud into a CAD/FreeCAD model, as-built, site model or terrain, to calibrate a scan against a survey, or to mock up a change on such a model.
---

# Scan to simplified FreeCAD model

Directions for an AI agent that turns a scan mesh into a simplified,
dimensioned FreeCAD model in the user's **live FreeCAD session over MCP**. The
output is a few dozen `Part` solids (buildings, tanks, racks, equipment
envelopes, foundations, fences, terrain) whose dimensions you can defend. It is not a re-meshed copy of the
scan. Later the same frame can host a Quetzal piping model (`quetzal-piping`).

## Read before you build

| File | Contents | Read |
|---|---|---|
| this file | Workflow, frame, tolerance rules, pitfalls | always |
| [references/ingest.md](references/ingest.md) | Loading the mesh and its texture colour, caching, which tool runs where | always |
| [references/segmentation.md](references/segmentation.md) | Levelling, squaring, rasters, face histograms and profiles, telling geometry from clutter | always |
| [references/calibration.md](references/calibration.md) | Fitting the scan to a survey, check features, what is authoritative, the verification table | whenever a survey, drawing or tape dimension exists |
| [references/primitives.md](references/primitives.md) | Element recipes as Part solids: buildings and roofs, openings, tanks and vessels, equipment envelopes, foundations, racks and platforms, existing piping (handed to Quetzal), paving and berms on terrain, fences, trees, terrain, boundary and clearance planes; heights from photos; applying user-given dimensions; proposal mock-ups | before writing the build macro, and before any correction round or mock-up |

The code lives in [`scan_tools.py`](../../scan_tools.py) at the repo root
(numpy, plus optional scipy/PIL). It creates no FreeCAD objects.

## Workflow

1. **Confirm the session.** Run `check_freecad_connection`, then list the open
   documents (`FileName`, modified flag, which is active). A scan opened from
   a .dae is usually an unsaved document, so there is no autosave risk. If
   the active document is a saved file with changes, stop and say so (see
   the autosave rule in `quetzal-piping` §2.1).
2. **Probe the mesh in the session** (facet count, bounding box, a height
   histogram, a coarse plan grid). Then read the source file yourself
   (ingest.md). The FreeCAD import drops texture coordinates.
3. **Level, square and orient** (segmentation.md): fit the ground plane, take
   the dominant wall angle, turn north up. Render an ortho, a ground-height
   map and a wall-density map, and **look at them**.
4. **Calibrate** (calibration.md): fit wall faces to survey lines, hold some
   features back as checks, and print the residual table. **Pause and show the
   user that table.** Ask, in one round, about what the scan cannot settle:
   roof form, things you can't identify, and which source is authoritative.
5. **Extract** each element class with its own method (segmentation.md,
   primitives.md). Record every number as a named constant tagged with its
   source: `SURVEY`, `SCAN`, `PHOTO`, `USER` or `ASSUMED`.
6. **Build** with a macro that runs in the session, into a new document. Put
   the scan mesh into the site frame (`Mesh.transform` with the 4x4 matrix)
   as a hidden overlay.
7. **Verify** (calibration.md): validity, survey dimensions on the built
   solids, terrain residuals inside the lot, and overlay screenshots in a
   *perspective* camera. Look at every image.
8. **Hand over:** the files, the frame, the calibration table, the per-element
   source table, and the open questions.
9. **Correction rounds.** Expect many; the user knows the site. Each round:
   - change the named constants;
   - rebuild from scratch;
   - re-run the checks (validity, the dimension you changed, contacts with its
     neighbours);
   - append the round to the report.

   When the user says "the selected window", read the selection
   (`Gui.Selection.getSelectionEx(doc)`: object, sub-element and
   `PickedPoints`). Convert the picked point to site feet, and match it to
   the constant that made it. Then remove or fix that entry in the macro.

## Rules

- **Survey beats scan for anything the survey dimensions.** Phone LiDAR
  drifts 0.5–2% in scale and warps by a few cm over a building-sized loop. A
  single best-fit transform still leaves ±1–2" residuals, so a straight scan
  cannot meet ±1". Build the surveyed footprints from survey numbers. Place
  everything else from the scan through the fitted transform, and say which
  is which.
- **Hold back at least one check feature** that the fit does not use: a
  building face is best. Its
  residual is the honest accuracy figure.
- **The user's tape beats scan and survey.** Anything the user measures
  replaces the number from either source. Tag it `USER` in the macro and the
  report.
- **The scan has a height ceiling.** A handheld scan reaches about 6–6.5 m.
  Wall or shell tops at a ragged, uniform height are the range limit, not the
  eave or the top.
  Roofs, tank tops and upper rack tiers are usually missing entirely. Get
  them from photos (primitives.md §Heights from a photo), and label them as
  estimates.
- **One height band can lie.** Shrubs read as a projecting wall, and glass
  doors let the LiDAR see the inner door. Decide what a face is from several
  height bands, and from colour. A step that holds across bands is geometry.
  An offset in only the lowest band is planting.
- **Name the class of every object before modelling it.** Circle fits find
  tree trunks, but also bins and posts. Check that a trunk's width holds
  over several 0.5 m bands and that its colour makes sense. A "fence" along a
  boundary can be a hedge: check the share of green facets
  (`2G − R − B > 15`). Vegetation scores far higher than masonry or
  timber. A survey's fence
  ties may describe a fence that has since gone. Ask about large
  unknowns (like additional structures not noted on other documents) rather than guess. 
- **Don't re-mesh.** The deliverable is solids with named dimensions. Keep
  the mesh only as a hidden overlay.
- **Keep private sites private.** Scans, surveys, photos, and the model are not public. Work in the user's private folder or
  the gitignored `private/`. Only generic code and lessons go into the repo
  (see `AGENTS.md`).

## Pitfalls that already cost a round

- **The dominant-angle histogram was 1° off** because fences and trees voted.
  The survey fit absorbs this (its rotation term). Don't trust the squaring
  to better than about 1°.
- **A cubic B-spline through raw ground cells rang to ±1 m** across kerbs,
  beds and steps. Filter (`filter_ground`), smooth, *then* interpolate
  (`terrain_grid`).
- **Ortho `saveImage` clipped** a site-sized scene into nonsense. Use
  `setCameraType("Perspective")` for overview shots.
- **Thin slabs vanished in renders** although `section` showed them a few
  centimetres above the terrain. The terrain's default display deviation
  (0.5% of a site-sized box) bulged its tessellation by tenths of a metre. Set
  `ViewObject.Deviation = 0.02` on the terrain, and check burial numerically
  rather than from a picture.
- **A slab measured from up-facing scan facets swallowed its surroundings**:
  planting beds, loose blocks and steps at the same height. The user's tape
  came out well short of the scan's figure. Bound a slab by its edges in the plan plot,
  where they are crisp, not by percentiles of everything at that height. A
  user's tape measurement beats both scan and survey.
- **The survey draws undimensioned features schematically.** Paths and
  paved areas are drawn, not dimensioned, and are good only to the tracing
  tolerance (calibration.md). Anchor them to whatever edges the scan sees.
- **A heredoc with Python in it broke on quoting.** Write scripts to the
  scratchpad and run the file.
- **First impressions of the front elevation were wrong twice** (planting, then
  glazing). The survey's small numbers were right both times. When scan and survey disagree about a small offset, look at
  more bands and a photo before you overrule the survey.
