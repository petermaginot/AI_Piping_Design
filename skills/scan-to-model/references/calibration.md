# Calibration to a survey, and verification

Part of the `scan-to-model` skill.

## Read the survey properly

- **Extract the page image.** A scanned survey is usually one DCTDecode JPEG
  inside the PDF. Write its stream bytes out (see quetzal-piping §12.1), then
  crop and magnify each dimension cluster. Reading the whole page at once
  loses the small numbers, and those are often the ones that matter (short
  projections, small offsets to secondary features).
- **Work out what every number is measured to.** Surveys usually dimension
  structures to their exterior faces and give offsets to the nearest face.
  Small arrowed dimensions at corners are usually jog depths. Two offsets to
  the same line that differ slightly at the two ends of a wall mean the
  structure is not quite parallel to the line. That difference is usually far
  below anything a scan resolves.
- **Ties to secondary features** (fences, walls, kerbs, posts) place those
  features relative to a boundary or control point. They make good check
  features, but only if the feature is still there. Confirm it from the scan
  colour or with the user. If something else has replaced it, it is only a
  rough check.

## Tracing undimensioned survey features

Paved areas, walks and other surfaces are often drawn but not dimensioned.
Trace them, don't eyeball them:

1. Crop the region from the extracted page image at full resolution.
2. **Calibrate each crop with two features of known position in that crop**
   (a boundary line and a structure face, or two faces of one structure).
   Scanned paper is not uniformly scaled. Crops of one sheet calibrated off
   different features can disagree by a noticeable fraction of a unit.
3. For each pixel row, list the runs of dark pixels (`gray < 110–120`)
   between the bounding features. Edges show up as runs that persist from row
   to row. Labels, hatching and arrows don't persist.
4. Convert to survey units, keep one `(y, x_left, x_right)` row at a regular
   spacing, and build from that table.
5. Anchor the result to anything the scan saw (an edge it captured, where the
   feature meets a structure). Quote the tracing tolerance for the rest.

## The site frame

Origin at a survey corner or control point, +X along a principal boundary
line, +Y across it, +Z up, mm. Convert survey values in feet with `FT`
(304.8), or in metres with 1000.

**Find the north arrow before naming any direction.** Surveys are often
drawn with the street or access at the bottom of the sheet, so page-up is
often *not* north. The arrow can be a small stylised glyph in the title
block. Cross-check it against corner notes that name a compass direction and
against the street names. A 90° mix-up can go unnoticed for several rounds.
The geometry is still right, but every compass direction the user mentions
is then misread. Keep the frame tied to the sheet if you like, but record the
true compass next to it, and translate the user's directions through it.

## Fitting

`fit_faces_to_survey(P, N, A, features, x0)` fits `similarity_2d`: a
rotation, separate x and y scales, and a translation, using soft-L1 least
squares. Each feature is one scanned face (axis, normal sign, height band,
along-range) matched to a survey line. It iterates with a narrowing capture
window (250 mm down to 60 mm), so a rough seed is enough.

- **Controls:** pick faces the survey dimensions directly and the scan sees
  well: full-height walls, both ends of each structure. Sample them equally
  (`n_per`) so a long wall doesn't swamp a short one.
- **Checks:** mark at least one face `control=False`. A structure face the
  fit did not use is the best kind. Report check residuals separately. They
  are the accuracy you can claim.
- **Expect** phone-scan scale factors of about 0.5–1.5%, possibly different
  in x and y, and rotations under about 1° (the squaring error). Residuals of
  a few centimetres after the fit are scan warp, and a better transform won't
  remove them. A scanned rectangle that is not rectangular is the signature
  of warp.

## What is authoritative

Tell the user, and get their agreement:

- **Survey:** structure footprints, boundary lines, and anything else it
  dimensions. Build these from the survey numbers.
- **Scan via the transform:** whatever the survey omits (slab and paving
  extents, fence and wall heights, vegetation, minor structures, grade,
  every height). It is good to about the fit residuals in plan, and better in
  height where the surface was seen.
- **Photo:** what the scan never reached (roofs, tall elements). Scale the
  photo from scan heights (primitives.md). Its accuracy is about ±5–10%.
- **Assumed:** thicknesses, hidden extents. List each one.

## Verification table (the deliverable's proof)

1. Every solid `isValid()`, with the solid count you expect.
2. Survey dimensions measured on the built solids (bounding boxes, edges):
   faces, widths, offsets. These should come out to 0.0 mm. If not, the
   macro has a typo.
3. Terrain against the filtered ground cells *inside the surveyed area*:
   `distToShape` from each cell's point to the top B-spline face. Report the
   median, p95, max and % within tolerance, plus the coverage %. Cells outside
   the surface's extent give huge distances, so exclude them rather than
   chase them.
4. Calibration residuals, controls and checks.
5. Overlay screenshots: the model at 60% transparency with the scan mesh
   visible, in front and perspective views.
6. A per-element source table (survey / scan / photo / assumed) with the open
   questions.
