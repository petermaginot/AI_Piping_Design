# Building the moves

Part of the `animation` skill. Every distance and direction below is solved
from the model, through Quetzal ports, when the scene is built. None of them
is a tuned constant.

## Removing and replacing bolted parts

- **Direction:** take it from the flange's port direction (`wdir`) at the
  joint. It points out of the joint. If there is no port to use (a stud set
  has only the flange-face ports), take the axis-aligned direction from the
  studs' centre toward the blind's centre, snapped to the dominant axis.
  This gives an exact direction and no drift.
- **Studs** back off along that axis until their trailing end clears the
  blind's outer face, plus a clearance (20 mm). Then hide them.
- **Blind and gasket** back off along the axis, then move aside or drop
  toward grade, and are hidden or parked. A raised-face gasket stands
  proud of the face, so it comes off with the blind.
- **A threaded plug** turns (three turns, say) while it rises its thread
  length, then lifts and moves aside.
- **Replacing** is the same moves in reverse order, ending exactly on the
  home placement (`at.home`), so nothing drifts.
- Check every **parked** position against the model with `distToShape`.

## Installation sequence

An installation animation sets spools into the model one at a time, from
where they arrive to their as-modelled positions.

- **The modelled position is the end state.** Each spool's home is where it
  sits in the model. The animation only works out where it *starts* and how
  it travels there. Never move the model to fit the animation.
- **Move the spool container.** If the spools are grouped into `App::Part`
  containers (quetzal-piping §14), each container's Placement moves all of
  its members as one. A container is normally at identity, so its home is
  identity, and a start pose is just the offset Placement. Assembly material
  (gaskets, bolts) is usually shown at bolt-up, not with the spool.
- **Order** comes from connectivity: start from what is already in place (a
  tie-in, an anchored header, equipment nozzles) and add spools whose ports
  meet something already set. Confirm the order with the user. It is a
  construction choice, not geometry.
- **Path:** start at the laydown or truck (beside the model, at grade),
  lift clear above the highest piping in the way, travel horizontally,
  then lower along the final joint's port direction for the last
  100–300 mm, so the spool comes straight onto its mating face. Solve the
  lift height from the bounding boxes of the installed parts, plus a
  margin, and check clearance with `distToShape` at sampled frames.
- **Before it arrives**, a spool is either hidden, or shown at its start
  pose. After it is set, bolt-up is the reverse of removal: studs come in
  along their axis to home, and the gasket goes in first.
- **Fade** the already-installed piping (transparency) only if it hides the
  spool being set.

## Valve handles

- **Turning a handle:** `valve_lockout_animation.build()` splits each
  valve into a `_Body` and a `_Handle` `Part::Feature`, cut at the top of the
  body (`ODBody/2` threaded, `FlgD/2` flanged), and hides the Quetzal valve.
  The handle's Placement is an expression: the valve Placement times a
  rotation about the valve's local Y by an angle property on an
  `App::VarSet`. Tween that angle (0 = open, 90 = closed) and `recompute()`
  only the handle object. Colour it at the halfway point.
- **Switching the actuator** (`anim_tools.set_valve`) is a jump between two
  Quetzal shapes. Use it when the turning motion does not matter.

## Poses from ports

- Build a moving object's frame from directions in the model: local X along
  the travel direction, local Z up. `anim_tools.frame(X, Y)` with
  `Y = -(X × Z_world)` returns the rotation. Its Placement is then
  `Placement(point, frame(X, Y))`.
- Take the travel direction from a port direction, not an ideal axis.
  Quetzal elbows can be a degree or so off 90°, and user-built runs can be
  skewed slightly in plan.

## Moving along a pipe centreline

For anything that travels through the piping (a tool, a plug, a flow
marker), trace the path from the model rather than assume it:

- **Walk the ports.** Start at a known port and walk through coincident
  ports (< 1 mm). Consider only Pipe, Elbow, Flange, Gasket, Valve, Tee and
  Reduct objects. Studs share the flange-face ports, so leave them out. At a
  tee, leave by the port that continues the run (the largest dot product
  with the entry direction). Stop at a named end object.
- **Pieces** are straights between elbows plus an arc for each elbow, built
  from its own ports: `t_in = -dir(entry)`, `t_out = dir(exit)`,
  `θ = acos(t_in·t_out)`, `n = normalise(t_out - t_in(t_in·t_out))`. The
  point at `φ` is `A + t_in R sinφ + n R(1 - cosφ)`. Report how far each
  arc's end lands from its elbow's outlet port (0.0000 mm expected). This
  works for any angle and skew.
- Place the object at `path_at(σ)` by path length, with its local X along
  the tangent. A rigid object chords a bend, so report the overlap.
- Scale the travel time with the path length (about 1 m/s reads well).

## Solving contact and rigid links

- **Contact or stop points** ("until it meets the reducer"): bracket the
  station between a known-clear and a known-touching position, then bisect
  for 50 iterations on `a.distToShape(b)[0] > 1e-6`. Report the final gap
  (≈ 1e-5 mm). Never use a tuned constant.
- **Rigid links** (a towed train, a linkage): for each trailing body,
  bisect on its path length so the 3D distance between its attach point
  and the one ahead equals the link length. Bracket between "touching" and
  twice the length behind. Report the link-length error over a few hundred
  sampled poses (≈ 1e-11 mm).
- **Fixed-length rope or cable:** never grow it to fit the geometry. Set its
  total length once, and solve the free variable (slack, hook height) per
  frame so the length is conserved. Report the length error in every phase.
