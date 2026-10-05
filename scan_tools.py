# -*- coding: utf-8 -*-
"""Turn a 3D scan mesh (phone LiDAR / photogrammetry) into numbers a model can
be built from.

Plain numpy (+ optional PIL for texture colour), so it runs both inside
FreeCAD over MCP and in a stand-alone Python where scipy / matplotlib are
available for the heavier analysis.  Nothing here creates FreeCAD objects:
the ``skills/scan-to-model`` skill builds Part solids from what these
functions return.

Conventions (skill ``scan-to-model``):

* Output frame is **Z-up, millimetres**.  A scan exported Y-up (COLLADA from
  3d Scanner App, Polycam, ...) is rotated with :func:`yup_to_zup`.
* A *frame* is a 4x4 numpy matrix mapping scan coordinates (already Z-up, mm)
  to site coordinates.  Every fitted quantity is reported in site
  coordinates; keep the matrix so the mesh can be overlaid on the model.

Typical use::

    import scan_tools as st
    S = st.load_dae("scan.dae", texture="textured_output.jpg")   # cached .npz
    V = st.yup_to_zup(S["V"])
    ...
"""

import os
import re

import numpy as np

__all__ = [
    "IN", "FT",
    "load_dae", "facet_colours",
    "yup_to_zup", "facet_normals", "facet_centroids", "facet_areas",
    "rot_z", "translate", "apply",
    "fit_plane_ransac", "level_frame", "dominant_plan_angle",
    "raster",
    "similarity_2d", "similarity_matrix", "fit_faces_to_survey", "face_profile",
    "ground_cells", "filter_ground", "terrain_grid",
    "concrete_mask", "find_trunks",
]

IN = 25.4        # mm per inch
FT = 304.8       # mm per foot


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

def _array_text(data, tag_re):
    """Return the text body of the first element whose opening tag matches."""
    m = re.search(tag_re, data)
    if not m:
        raise ValueError("no element matching %r" % tag_re)
    start = m.end()
    end = data.index(b"<", start)
    return data[start:end]


def load_dae(path, texture=None, cache=True):
    """Read a single-mesh COLLADA (.dae) file into numpy arrays.

    Returns a dict:

    ``V``  (n,3) float64 vertex positions in **mm**, in the file's own axes
    ``F``  (m,3) int32 vertex indices per triangle
    ``UV`` (m,3,2) float32 texture coordinates per triangle corner, or None
    ``C``  (m,3) uint8 per-facet colour sampled from *texture*, or None

    FreeCAD's own DAE import drops the texture coordinates and merges
    vertices, so read the file directly when colour matters.  The result is
    cached beside the file as ``<name>.npz`` (a 150 MB DAE parses in about
    half a minute; the cache loads in about a second).
    """
    npz = os.path.splitext(path)[0] + ".npz"
    if cache and os.path.isfile(npz) and os.path.getmtime(npz) >= os.path.getmtime(path):
        z = np.load(npz)
        out = {k: z[k] for k in z.files}
        out.setdefault("UV", None)
        out.setdefault("C", None)
        if out.get("C") is None and texture:
            out["C"] = facet_colours(out["UV"], texture)
            np.savez(npz, **{k: v for k, v in out.items() if v is not None})
        return out

    with open(path, "rb") as fh:
        data = fh.read()

    unit = 1.0
    m = re.search(rb'<unit[^>]*meter="([0-9.eE+-]+)"', data)
    if m:
        unit = float(m.group(1))

    pos = np.array(_array_text(data, rb'<float_array[^>]*positions-array[^>]*>').split(),
                   dtype=np.float64).reshape(-1, 3) * unit * 1000.0

    # The <triangles> element names its inputs and their offsets.
    tri = re.search(rb"<triangles[^>]*>(.*?)<p>", data, re.S)
    offs = dict((s.decode(), int(o)) for s, o in
                re.findall(rb'<input semantic="(\w+)"[^>]*offset="(\d+)"', tri.group(1)))
    stride = max(offs.values()) + 1
    p = np.array(_array_text(data, rb"<p>").split(), dtype=np.int64).reshape(-1, 3, stride)
    F = p[:, :, offs["VERTEX"]].astype(np.int32)

    UV = None
    if "TEXCOORD" in offs:
        uv = np.array(_array_text(data, rb'<float_array[^>]*map-0-array[^>]*>').split(),
                      dtype=np.float32).reshape(-1, 2)
        UV = uv[p[:, :, offs["TEXCOORD"]]]

    # Node transform, if it is not identity.
    mm = re.search(rb'<matrix[^>]*>([^<]*)</matrix>', data)
    if mm:
        M = np.array(mm.group(1).split(), float).reshape(4, 4)
        if not np.allclose(M, np.eye(4)):
            M[:3, 3] *= unit * 1000.0
            pos = apply(M, pos)
    del data

    out = {"V": pos, "F": F, "UV": UV, "C": None}
    if texture and UV is not None:
        out["C"] = facet_colours(UV, texture)
    if cache:
        np.savez(npz, **{k: v for k, v in out.items() if v is not None})
    return out


def facet_colours(UV, texture):
    """Mean texture colour at each triangle's centroid UV -> (m,3) uint8."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    img = np.asarray(Image.open(texture).convert("RGB"))
    h, w = img.shape[:2]
    c = UV.mean(axis=1)
    u = np.clip((c[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(np.int64)
    v = np.clip((1.0 - (c[:, 1] % 1.0)) * (h - 1), 0, h - 1).astype(np.int64)
    return img[v, u]


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

def yup_to_zup(V):
    """Rotate Y-up coordinates to Z-up (x, y, z) -> (x, -z, y)."""
    V = np.asarray(V)
    return np.column_stack([V[:, 0], -V[:, 2], V[:, 1]])


def facet_centroids(V, F):
    return V[F].mean(axis=1)


def facet_normals(V, F):
    """Unit normals and areas (mm^2) per triangle."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    s = np.linalg.norm(n, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = n / s[:, None]
    u[~np.isfinite(u)] = 0.0
    return u, 0.5 * s


def facet_areas(V, F):
    return facet_normals(V, F)[1]


def rot_z(deg):
    t = np.radians(deg)
    M = np.eye(4)
    M[0, 0], M[0, 1], M[1, 0], M[1, 1] = np.cos(t), -np.sin(t), np.sin(t), np.cos(t)
    return M


def translate(dx, dy, dz=0.0):
    M = np.eye(4)
    M[:3, 3] = (dx, dy, dz)
    return M


def apply(M, P):
    """Apply a 4x4 matrix to (n,3) points."""
    P = np.asarray(P, float)
    return P @ M[:3, :3].T + M[:3, 3]


def fit_plane_ransac(P, tol=25.0, iters=400, seed=0):
    """Plane through (n,3) points: returns (normal, d, inlier mask), n.z >= 0.

    Least-squares refit on the inliers of the best random triple.
    """
    rng = np.random.default_rng(seed)
    best = None
    n_pts = len(P)
    for _ in range(iters):
        i = rng.choice(n_pts, 3, replace=False)
        nrm = np.cross(P[i[1]] - P[i[0]], P[i[2]] - P[i[0]])
        L = np.linalg.norm(nrm)
        if L < 1e-9:
            continue
        nrm /= L
        d = -nrm @ P[i[0]]
        cnt = np.count_nonzero(np.abs(P @ nrm + d) < tol)
        if best is None or cnt > best[0]:
            best = (cnt, nrm, d)
    _, nrm, d = best
    inl = np.abs(P @ nrm + d) < tol
    Q = P[inl]
    c = Q.mean(axis=0)
    _, _, vt = np.linalg.svd(Q - c, full_matrices=False)
    nrm = vt[2]
    if nrm[2] < 0:
        nrm = -nrm
    d = -nrm @ c
    inl = np.abs(P @ nrm + d) < tol
    return nrm, d, inl


def level_frame(normal, d):
    """4x4 matrix that rotates *normal* onto +Z and puts the plane at z = 0."""
    n = np.asarray(normal, float) / np.linalg.norm(normal)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(n, z)
    s, c = np.linalg.norm(v), n @ z
    R = np.eye(3)
    if s > 1e-12:
        k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + k + k @ k * ((1 - c) / s ** 2)
    M = np.eye(4)
    M[:3, :3] = R
    # A point on the plane: -d * n.
    M[:3, 3] = -(R @ (-d * n)) * np.array([0, 0, 1])
    return M


def dominant_plan_angle(normals, areas, min_horiz=0.95):
    """Plan rotation (deg, -45..45) that squares the walls to the axes.

    Uses near-vertical facets (|n.z| small), weights by area, and folds the
    normal azimuth mod 90 deg, so walls at right angles vote together.
    Rotate the scan by the *negative* of the result.
    """
    h = np.hypot(normals[:, 0], normals[:, 1])
    sel = h > min_horiz
    az = np.degrees(np.arctan2(normals[sel, 1], normals[sel, 0])) % 90.0
    w = areas[sel]
    hist, edges = np.histogram(az, bins=360, range=(0, 90), weights=w)
    # circular smoothing over +-1 deg
    k = np.ones(9) / 9.0
    hs = np.convolve(np.concatenate([hist[-4:], hist, hist[:4]]), k, mode="valid")
    i = int(np.argmax(hs))
    peak = 0.5 * (edges[i] + edges[i + 1])
    # refine: circular mean within +-3 deg of the peak
    dd = ((az - peak + 45.0) % 90.0) - 45.0
    near = np.abs(dd) < 3.0
    peak = peak + np.average(dd[near], weights=w[near])
    return ((peak + 45.0) % 90.0) - 45.0


def raster(P, values, x0, y0, nx, ny, cell, how="max", fill=np.nan):
    """Grid (n,) *values* at (n,2|3) points P onto an (ny,nx) array.

    how: 'max', 'min', 'count', 'sum' or 'mean'.  Row j covers
    y0 + j*cell .. y0 + (j+1)*cell; column i likewise in x.
    """
    i = np.floor((P[:, 0] - x0) / cell).astype(np.int64)
    j = np.floor((P[:, 1] - y0) / cell).astype(np.int64)
    ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    i, j, v = i[ok], j[ok], np.asarray(values)[ok]
    flat = j * nx + i
    if how == "count":
        return np.bincount(flat, minlength=nx * ny).reshape(ny, nx)
    if how in ("sum", "mean"):
        s = np.bincount(flat, weights=v, minlength=nx * ny).reshape(ny, nx)
        if how == "sum":
            return s
        n = np.bincount(flat, minlength=nx * ny).reshape(ny, nx)
        with np.errstate(invalid="ignore", divide="ignore"):
            out = s / n
        out[n == 0] = fill
        return out
    G = np.full(nx * ny, -np.inf if how == "max" else np.inf)
    (np.maximum if how == "max" else np.minimum).at(G, flat, v)
    G[~np.isfinite(G)] = fill
    return G.reshape(ny, nx)


# --------------------------------------------------------------------------
# Calibration to a survey
# --------------------------------------------------------------------------

def similarity_2d(x, P):
    """Plan transform used for survey calibration, applied to (n,2|3) points.

    ``x = (theta, sx, sy, tx, ty)``: rotate by theta, then scale x and y
    separately (phone LiDAR drifts differently along and across the walk
    path), then translate.  Z is passed through unchanged.
    """
    th, sx, sy, tx, ty = x
    c, s = np.cos(th), np.sin(th)
    P = np.asarray(P, float)
    out = np.column_stack([sx * (c * P[:, 0] - s * P[:, 1]) + tx,
                           sy * (s * P[:, 0] + c * P[:, 1]) + ty])
    if P.shape[1] > 2:
        out = np.column_stack([out, P[:, 2:]])
    return out


def similarity_matrix(x):
    """4x4 matrix equivalent of :func:`similarity_2d` (for Mesh.transform)."""
    th, sx, sy, tx, ty = x
    c, s = np.cos(th), np.sin(th)
    return np.array([[sx * c, -sx * s, 0, tx], [sy * s, sy * c, 0, ty],
                     [0, 0, 1, 0], [0, 0, 0, 1.0]])


def fit_faces_to_survey(P, N, A, features, x0, n_per=3000, windows=(250, 120, 60, 60),
                        vert_tol=0.3, seed=0):
    """Fit :func:`similarity_2d` so scanned wall faces land on survey lines.

    *P*, *N*, *A*: facet centroids (mm, levelled and squared, roughly in the
    site frame), unit normals, areas.  *features*: list of dicts::

        dict(name="bldg W", axis=0, sign=-1, rough=-5000, along=(y0, y1),
             z=(1000, 5000), survey=10.0 * FT, control=True)

    ``axis`` 0 means the face is a line x = const (normal along x), 1 means
    y = const; ``sign`` is the outward normal direction; ``rough`` is its
    position in the *input* frame (first pass only); ``along`` limits the
    other coordinate (input frame); ``survey`` is the survey value in mm.
    Features with ``control=False`` are reported but not fitted -- keep at
    least one back as an independent check.

    Returns ``(x, table)``; table rows are
    ``(name, survey_mm, scan_mm, residual_mm, sd_mm, n, control)``.
    """
    from scipy.optimize import least_squares
    rng = np.random.default_rng(seed)
    vert = np.abs(N[:, 2]) < vert_tol
    x = np.asarray(x0, float)
    T = None

    def select(f, win):
        ax, o = f["axis"], 1 - f["axis"]
        s = (vert & (P[:, 2] > f["z"][0]) & (P[:, 2] < f["z"][1])
             & (P[:, o] > f["along"][0]) & (P[:, o] < f["along"][1])
             & (f["sign"] * N[:, ax] > 0.8))
        idx = np.flatnonzero(s)
        if T is None:
            keep = np.abs(P[idx, ax] - f["rough"]) < win
        else:
            keep = np.abs(T(P[idx])[:, ax] - f["survey"]) < win
        idx = idx[keep]
        if len(idx) > n_per:
            idx = rng.choice(idx, n_per, replace=False)
        return idx

    groups = None
    for win in windows:
        groups = [select(f, win) for f in features]

        def res(xx):
            r = []
            for f, idx in zip(features, groups):
                if f.get("control", True) and len(idx):
                    q = similarity_2d(xx, P[idx, :2])
                    r.append((q[:, f["axis"]] - f["survey"]) / np.sqrt(len(idx)))
            return np.concatenate(r)
        x = least_squares(res, x, loss="soft_l1", f_scale=30.0 / np.sqrt(n_per)).x
        T = lambda p, xx=x: similarity_2d(xx, p[:, :2])

    table = []
    for f, idx in zip(features, groups):
        if len(idx) == 0:
            table.append((f["name"], f["survey"], np.nan, np.nan, np.nan, 0, f.get("control", True)))
            continue
        q = similarity_2d(x, P[idx, :2])[:, f["axis"]]
        m = np.median(q)
        table.append((f["name"], f["survey"], m, m - f["survey"], q.std(), len(idx),
                      f.get("control", True)))
    return x, table


def face_profile(P, N, A, axis, sign, across, along, step, z=(300, 2600), min_area=1e4):
    """Position of the dominant face along a wall, in bins of *step*.

    Use it to find jogs, recesses and projections: a wall that is straight in
    reality but drifts steadily along the profile is scan warp; a step that
    holds over several bins *and* several height bands is geometry.  Returns
    a list of ``(bin_start, position or nan)``.
    """
    o = 1 - axis
    s = ((sign * N[:, axis] > 0.85) & (P[:, axis] > across[0]) & (P[:, axis] < across[1])
         & (P[:, 2] > z[0]) & (P[:, 2] < z[1]))
    out = []
    for b in np.arange(along[0], along[1], step):
        t = s & (P[:, o] >= b) & (P[:, o] < b + step)
        if A[t].sum() < min_area:
            out.append((b, np.nan))
            continue
        v, w = P[t, axis], A[t]
        h, e = np.histogram(v, bins=max(1, int((v.max() - v.min()) / 10) + 1), weights=w)
        i = np.argmax(np.convolve(h, np.ones(3) / 3, "same"))
        c = 0.5 * (e[i] + e[i + 1])
        m = np.abs(v - c) < 40
        out.append((b, np.average(v[m], weights=w[m])))
    return out


# --------------------------------------------------------------------------
# Ground and terrain
# --------------------------------------------------------------------------

def ground_cells(P, N, x0, y0, nx, ny, cell, exclude=(), zmax=1200.0, min_pts=15, pct=0.1):
    """Low-percentile height of up-facing facets per grid cell -> (ny,nx).

    *exclude* is a list of ``(x0, x1, y0, y1)`` boxes (buildings, decks,
    steps) whose facets are ignored.  Cells with fewer than *min_pts*
    facets are NaN.
    """
    m = (N[:, 2] > 0.85) & (P[:, 2] < zmax)
    for a, b, c, d in exclude:
        m &= ~((P[:, 0] > a) & (P[:, 0] < b) & (P[:, 1] > c) & (P[:, 1] < d))
    i = np.floor((P[m, 0] - x0) / cell).astype(np.int64)
    j = np.floor((P[m, 1] - y0) / cell).astype(np.int64)
    z = P[m, 2]
    ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    key, z = (j * nx + i)[ok], z[ok]
    order = np.lexsort((z, key))
    key, z = key[order], z[order]
    starts = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    ends = np.r_[starts[1:], len(key)]
    G = np.full(nx * ny, np.nan)
    for s0, e0 in zip(starts, ends):
        if e0 - s0 >= min_pts:
            G[key[s0]] = z[s0 + int(pct * (e0 - s0))]
    return G.reshape(ny, nx)


def _fill(G, ok, cx, cy):
    from scipy import interpolate
    pts = np.column_stack([cx[ok], cy[ok]])
    lin = interpolate.griddata(pts, G[ok], (cx, cy), method="linear")
    near = interpolate.griddata(pts, G[ok], (cx, cy), method="nearest")
    return np.where(np.isfinite(lin), lin, near)


def filter_ground(G, x0, y0, cell, passes=((15, 150), (9, 100), (5, 60))):
    """Progressive filter: drop cells standing above a robust local surface.

    Each pass fills the holes, takes a 30th-percentile filter over *window*
    cells and rejects cells more than *thr* mm above it (shrubs, mulch beds,
    cars, bins, steps).  Returns ``(ok_mask, filled_smoothed_grid)``.
    """
    from scipy import ndimage
    ny, nx = G.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cx, cy = x0 + (xx + 0.5) * cell, y0 + (yy + 0.5) * cell
    ok = np.isfinite(G)
    for win, thr in passes:
        F = _fill(G, ok, cx, cy)
        S = ndimage.percentile_filter(F, 30, size=win, mode="nearest")
        ok &= ~((G - S > thr) | (S - G > 3 * thr))
    F = ndimage.gaussian_filter(_fill(G, ok, cx, cy), 1.0, mode="nearest")
    return ok, F


def terrain_grid(F, x0, y0, cell, xr, yr, step):
    """Resample a filled, smoothed ground grid onto a control grid of *step* mm.

    Returns ``(gx, gy, Z)`` for ``Part.BSplineSurface.interpolate``.  Only
    interpolate a *smoothed* grid -- a cubic through raw cells rings across
    every kerb and bed edge (a +-1 m overshoot was seen).
    """
    from scipy import interpolate
    ny, nx = F.shape
    f = interpolate.RectBivariateSpline(y0 + (np.arange(ny) + 0.5) * cell,
                                        x0 + (np.arange(nx) + 0.5) * cell, F, kx=3, ky=3, s=0)
    gx = np.arange(xr[0], xr[1] + step, step)
    gy = np.arange(yr[0], yr[1] + step, step)
    return gx, gy, f(gy, gx)


# --------------------------------------------------------------------------
# Classification helpers
# --------------------------------------------------------------------------

def concrete_mask(C, N, P, zmax=450.0, sat_max=0.16, bright_min=70, exg_max=15):
    """Up-facing, low, unsaturated, not-green facets: concrete or paving.

    Strong sun and shadow defeat colour thresholds; use the mask to find the
    edges the scan saw and take the rest of a slab from the survey.
    """
    c = C.astype(float)
    mx, mn = c.max(1), c.min(1)
    sat = (mx - mn) / np.maximum(mx, 1)
    exg = 2 * c[:, 1] - c[:, 0] - c[:, 2]
    return ((N[:, 2] > 0.85) & (sat < sat_max) & (mx > bright_min)
            & (exg < exg_max) & (P[:, 2] < zmax))


def find_trunks(P, N, hag, x0, y0, shape, cell=50.0, band=(900, 1600), exclude=None,
                min_pts=150, max_extent=1500.0):
    """Circle fits to vertical clusters at breast height.

    *hag* is height above ground per facet; *exclude* a boolean mask of
    facets to ignore (buildings).  Returns rows
    ``(cx, cy, dia, median_residual, n)``, largest cluster first.  A real
    trunk keeps a consistent width over several 0.5 m bands -- check that,
    and the colour, before modelling one: bins, grills and posts fit circles
    too.
    """
    from scipy import ndimage
    s = (np.abs(N[:, 2]) < 0.4) & (hag > band[0]) & (hag < band[1])
    if exclude is not None:
        s &= ~exclude
    pts = P[s, :2]
    ii = np.floor((pts[:, 0] - x0) / cell).astype(int)
    jj = np.floor((pts[:, 1] - y0) / cell).astype(int)
    ok = (ii >= 0) & (ii < shape[1]) & (jj >= 0) & (jj < shape[0])
    pts, ii, jj = pts[ok], ii[ok], jj[ok]
    G = np.zeros(shape, bool)
    G[jj, ii] = True
    lab, _ = ndimage.label(ndimage.binary_closing(G, iterations=2))
    lp = lab[jj, ii]
    out = []
    for k in range(1, lab.max() + 1):
        m = lp == k
        if m.sum() < min_pts:
            continue
        p = pts[m]
        if (p.max(0) - p.min(0)).max() > max_extent:
            continue
        Am = np.column_stack([2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))])
        cx, cy, c0 = np.linalg.lstsq(Am, (p ** 2).sum(1), rcond=None)[0]
        r = np.sqrt(c0 + cx ** 2 + cy ** 2)
        out.append((cx, cy, 2 * r,
                    np.median(np.abs(np.hypot(p[:, 0] - cx, p[:, 1] - cy) - r)), int(m.sum())))
    out.sort(key=lambda o: -o[4])
    return out
