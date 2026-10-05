# Levelling, squaring and segmentation

Part of the `scan-to-model` skill.

## Level

Take the up-facing (`n.z > 0.95`), low facets and run `fit_plane_ransac`
with `tol` of about 60 mm. A site is rarely flat (graded pads, drainage
slopes, berms), so expect only about half the facets to be inliers. Then
`level_frame(n, d)` gives a 4x4 matrix that puts that plane at z = 0. Report
the tilt. Z = 0 is then *a* ground plane, not a datum. Say what it is, and
give grade near each structure relative to it. If the site has a plant datum
or a benchmark on the survey, tie to it in the calibration.

## Square and orient

`dominant_plan_angle(normals, areas)` takes a histogram of vertical facet
azimuths, folded mod 90°. Rotate by the negative of the result. Then work out
north from the survey's layout: which structures sit where, and where an
access road enters. Apply a further multiple of 90°. **Check handedness.** If
the layout only matches the survey mirrored, something upstream flipped an
axis.

The squaring is good to about 1°. Fences, trees, piping at odd angles and
round tanks vote in the histogram, and the calibration fit takes up the rest.
On a site laid out on a plant grid, square to the grid's dominant structures
(buildings, racks), not to everything.

## Rasters to look at first

Use `raster(P, values, x0, y0, nx, ny, cell, how)` at 50 mm for the overview:

- an **ortho** (mean colour of up-facing facets);
- a **ground height** map (min z of up-facing facets);
- **surface minus ground** (max z minus ground) for heights;
- **wall density** (count of vertical facets in a 0.3–2.5 m band).

Plot them with the survey outline overlaid once you have a frame, and read
them. These four images answer most questions about what is where, and they
show the scan's coverage. Write the coverage down. Unscanned areas become
"from survey" or "extrapolated" in the report.

## Wall and shell faces

- **Face histograms.** In a box around a structure, take the area-weighted
  histogram of x for facets with `|n.x| > 0.9` (and of y for `|n.y| > 0.9`).
  The peaks are wall faces. The standard deviation per face is about 20 mm on
  phone LiDAR. A round shell (a tank, a vessel) gives no peak. Fit a circle to
  its vertical facets in plan instead.
- **`face_profile`** gives the face position along a wall in short bins. A
  steady drift along the whole wall is rotation or warp. A step that holds over
  several bins is a jog. Run it in **several height bands**:
  - The lowest band (0.3–1 m) is cluttered: vegetation, stored material,
    parked vehicles, small equipment and piping along the wall all look like
    projecting wall.
  - Glazing, open louvres and grating let the LiDAR see the surface *behind*
    them, which looks like a recess.
  - An extension, a canopy or an upper level that overhangs shows as a
    constant offset between bands.
  - Colour separates masonry, metal cladding, insulation jacketing and
    vegetation. Print the mean RGB per band.

## Ground, slabs and clutter

- **Ground cells:** `ground_cells` (10th percentile of up-facing z per cell
  of about 300 mm, with buildings, foundations and platforms excluded), then
  `filter_ground`. The filter is progressive: it rejects anything that stands
  above a robust local surface, such as vehicles, pallets, bins, small
  equipment and low piping.
- **Concrete:** `concrete_mask` finds low-saturation, non-green, up-facing,
  low facets. Sun and shadow make it patchy, so take slab and foundation
  *edges* where the scan sees them, and the extent from the survey. Gravel
  surfacing is also low-saturation, so check the edges against the ortho.
- **Heights of features:** go per feature with up-facing percentiles (top of
  concrete, platform deck, landing, step) and down-facing ones (beam bottoms,
  canopy undersides, the bottom of pipe). The median of the right facet
  orientation is far more robust than a max.

## Openings from wall elevations

For each wall, render two images in that wall's coordinates (along-wall
distance against z), using facets within about ±0.9 m of the plane. Remove
warp first: fit the wall plane per bin of about 300 mm on the upper band and
subtract a linear trend.

- **Depth:** the minimum depth behind the plane per pixel. Glass and open
  louvres give LiDAR returns from the room behind, so they show as patches
  80–250 mm behind the face, or as holes. A closed roll-up door shows as a
  shallow recess with horizontal ribs.
- **True colour:** the mean texture colour of facets within 250 mm of the
  face. This is effectively an orthophoto of the wall, and the best single
  source. Door frames, louvres, signage and penetrations are all readable on a
  150 mm grid.

Automatic detection (pixels more than 70 mm behind a 15th-percentile local
surface, then connected components and a size and fill filter) finds only
some of the openings. Equipment, piping and conduit along the wall, canopies
and sun glare hide the rest. Treat it as a hint. Read each opening off the
colour elevation, and check its type against photos: personnel door, roll-up
door, louvre or window.

- **Regular patterns:** openings in a repeated layout (evenly spaced louvres,
  doors on a bay grid) let a photo set the pattern and the scan set the size.
- **Hidden openings:** an opening the scan cannot see (behind equipment,
  above the range limit) comes from a photo by proportion. Mark it as an
  estimate.

## Structures you can't name from a raster

Slice by height: up-facing facets and vertical facets in bands of about
0.6 m, plotted in plan on a 300 mm grid, coloured by z. The parts then
separate on their own:
- platforms and decks are up-facing patches at a constant z;
- columns and posts are small vertical blobs through every band;
- handrails and beams are thin lines in the upper bands;
- pipe runs are lines at a constant z, with down-facing facets underneath
  and no up-facing floor;
- a span with no up-facing floor is a pipe bridge or a beam, not a walkway.

Model the parts (columns, beams, platforms, rails, pipe), not one envelope
box. A user who knows the structure will notice a missing platform at once.

## Columns, poles, trees and other vertical things

`find_trunks` clusters vertical facets at 0.9–1.6 m above ground and fits a
circle to each cluster. Despite its name, it finds any vertical round or
compact object: columns, poles, bollards, vertical pipes, small tanks and
trees. Then, for each candidate:

- look at its width in 0.5 m bands up to the scan ceiling, and its mean
  colour;
- a column, pole or tree keeps a similar width through the bands, and its
  colour says which;
- a person, a bin or a piece of portable equipment stops by about 2 m;
- something under 100 mm across (a small post, a conduit riser) may not be
  worth modelling.

Render a coloured three-view scatter of anything large you cannot name. A
skid, a manifold or a dense run of piping looks like noise in a raster and is
obvious in a picture.
