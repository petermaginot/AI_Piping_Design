# Verification

Part of the `animation` skill. A timeline that plays without an error
proves only that the code ran. Print these from the solved scene and the
stepped timeline, not from the code, before playing and again before you
hand over.

## Before playing

- **Solved quantities:** every travel, stop gap (≈ 1e-5 mm) and lift height,
  with what it was solved against.
- **Path ends:** each arc lands on its elbow's outlet port (0.0000 mm), and
  a path ends on its end port.
- **Rigid links and fixed lengths:** the error over a few hundred sampled
  poses (≈ 1e-11 mm).
- **Clashes at key frames:** start, each step's end, and a few points
  through each long move. Check every moving solid against the visible
  model solids with `common()` volume or `distToShape`. Explain every
  overlap that remains. The expected ones are:
  - a stud set's inner nuts in the flange during the first 15–30 mm of
    withdrawal;
  - the uncut run-pipe wall under an olet;
  - a rigid body chording a bend.
- **Valves:** every animated valve in both states against the model. The
  only overlaps should be table artefacts that are the same open and
  closed.
- **Parked positions** (blinds aside, studs out, spools at the laydown) are
  clear of the model, with the minimum clearance printed.

## After stepping the whole timeline

Run `step_to(steps, len(steps))` and check:

- the end state is the one the procedure says (which valves are open, which
  parts are off, every spool at its home);
- then `reset()`, and check every mover is back at its recorded home
  (placement error 0), visible, at its original transparency, with every
  valve in its starting state.

## Real-time play

- `play()` runs to `p.done()` (`p.i == len(p.steps)`), and the console
  shows the player's "done" message.
- Look at the frames you saved, not just the numbers.

## Handover

Report the numbers above, the expected overlaps and why, the files, and how
to replay. Say which documents the bridge autosaved during the session.
