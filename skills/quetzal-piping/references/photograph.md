# Building from a field photograph (§12)

Part of the `quetzal-piping` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

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

- **Supports**: whether to model them, and how. A post-and-cap support with a
  U-bolt suits the Quetzal makers (`makeBeam`, a `makePipe` post, `makeUbolt`).
  Shoes, guides, hangers and fabricated brackets do not, and are better as plain
  `Part` solids (§3.5). Leave out a temporary construction stand in the shot, such
  as a jack stand under a valve, unless the user says otherwise.

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
