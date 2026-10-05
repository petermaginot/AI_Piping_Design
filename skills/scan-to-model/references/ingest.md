# Ingest

Part of the `scan-to-model` skill.

## Where to run what

- **Analysis** (millions of facets, scipy, matplotlib plots): run it in a
  stand-alone Python that has numpy, scipy, PIL and matplotlib. Write each
  step as a script in the scratchpad, run it with Bash, and read the PNGs it
  saves. This keeps the FreeCAD GUI responsive and gives you plots.
- **Building and verifying**: run these in the live session with
  `execute_python`, by exec'ing the build macro. The macro reads a small
  `.npz` written by the analysis: the 4x4 scan-to-site matrix, the calibration
  vector and the terrain control grid.

Both import `scan_tools.py`. It only needs numpy, and it imports scipy or PIL
inside the functions that use them.

## Reading the mesh

`st.load_dae(path, texture=...)` parses a single-mesh COLLADA file directly:

- `V` is the vertex positions in **mm** (honours `<unit meter=...>`, applies a
  non-identity node `<matrix>`).
- `F` is the triangles. `UV` is the per-corner texture coordinates.
- `C` is the per-facet RGB sampled from the texture at the triangle centroid.

A 150 MB / 2.2 M-facet file parses in a few seconds. The result is cached as
`<name>.npz` beside the source, so keep that cache in the private folder too.

FreeCAD's own DAE import also works and gives the same coordinates in mm.
However, it **merges vertices and drops texture coordinates**, so you cannot
get colour from it. Use it only for the in-session overlay mesh.

Other formats: an OBJ or PLY reads into the same `V`, `F` (and per-vertex
colour) with a few lines of numpy. Keep the same dict shape so the rest of the
pipeline is unchanged.

## Axes

Exports from phone apps are usually **Y-up** (`<up_axis>Y_UP</up_axis>`).
Use `st.yup_to_zup(V)` before anything else: `(x, y, z) -> (x, -z, y)`.
The 4x4 that maps the FreeCAD-imported mesh into the site frame is
`similarity_matrix(x) @ M_level @ Yz`, where `Yz` is that same axis swap as a
matrix.

## Per-facet quantities

`facet_normals` returns unit normals and areas, and `facet_centroids` returns
centroids. Weight statistics by area, because scan triangles vary in size by
orders of magnitude.
