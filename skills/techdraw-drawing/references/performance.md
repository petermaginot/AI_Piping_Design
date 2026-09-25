# Page performance (§12–§13)

Part of the `techdraw-drawing` skill. Section numbers (§) are shared across the skill's files; `SKILL.md` has the table saying which file holds which section.

---

## 12. Keeping the page off

`page.KeepUpdated = False` stops the page redrawing on every change. Turn it on
while you build (you need the views to project, §5.2) and leave it **off** when
you hand over, so the user's next edit to the model does not stall the GUI.

It is a page property, independent of the global
`Mod/TechDraw/General/KeepPagesUpToDate`.

---

## 13. Why the page is slow

The usual guess is that hidden-line removal cannot cope with the geometry. It
is not that. For an 11-component spool, the whole geometry pipeline is
sub-second:

```
TechDraw.projectEx(compound, direction)   0.18 s     # HLR
TechDraw.edgeWalker(visible_edges)        0.14 s     # face finding
```

What actually costs is **how many objects are in the container**, because the
scene layer builds a graphics item per edge, per vertex and per found face, for
every view. Measured end to end on the same spool — time from `touch()` until
every view has really projected:

| Container holds | Views | Solids | Faces | Time to drawn |
|---|---|---|---|---|
| Welded only | 1 | 11 | 124 | **1.65 s** |
| + gaskets, bolting, valves | 1 | 87 | 1786 | **36.48 s** |
| Welded only | 3 | 11 | 124 | **4.79 s** |
| + gaskets, bolting, valves | 3 | 87 | 1786 | **59.40 s** |

Bolting is what does it. A single `Bolts_Nuts` object is **16 solids, 336 faces,
720 edges** — 2.7x the entire welded spool. Two bolt sets and a pair of valves
turn a five-second page into a minute.

The geometry pipeline only grew from 0.32 s to 2.84 s across those two cases. The
other 56 seconds are scene construction. That is why raising the HLR settings
does little and why trimming the container does a lot.

Levers, in the order worth trying:

1. **Take bolting, gaskets and valves out of the container.** This is the whole
   game, and it is also what a weld spool drawing should show.
2. **`page.KeepUpdated = False`** while working (§12).
3. **`view.HardHidden = False`** unless the view genuinely needs hidden lines —
   it roughly doubles the items in the scene.
4. **`view.SmoothVisible = False`** drops tangent edges, which are numerous on
   pipe and elbows.
5. **`view.CoarseView = True`** switches to polygonal HLR. Fast and ugly; useful
   while laying a page out.

If a page is still slow after that, count the solids before blaming TechDraw.
