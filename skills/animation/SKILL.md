---
name: animation
description: Animate a FreeCAD piping model in the user's live session over MCP — an installation sequence (spools lifted from a laydown and set in place, bolted up), a valve line-up or lockout (valves turning, open/closed colours), removing or replacing blinds, studs and plugs, or equipment moving along a pipe — as a replayable macro with play, stop and reset. Use when the user asks to animate, demonstrate or show a sequence of steps on a model, or to make frames or a walkthrough of one.
---

# Animating a model

Directions for an AI agent that animates a model in the user's **live
FreeCAD GUI session over MCP**. The model is usually Quetzal piping, so the
rules of the `quetzal-piping` skill still apply: build live, mm and DN
labels, coerce every `Quantity` with `val()`, verify numerically. Read its
§1, §2 and §2.1 before you start. The autosave rule in §2.1 matters even more
here, because an animation changes the model constantly.

An animation is a **timeline**: a list of `(seconds, fn(u))` steps, where `u`
runs 0 → 1 over the step. A `Player` plays it on a Qt timer. The same steps
can be run synchronously to pose any single frame. The helpers are in
[`anim_tools.py`](../../anim_tools.py) at the repo root. Use them rather than
writing your own player.

## Read before you build

| File | Contents | Read |
|---|---|---|
| this file | Workflow, conventions, the rules that went wrong before | always |
| [references/timeline-and-playback.md](references/timeline-and-playback.md) | Scene / timeline / player structure, step types, extending an animation, playing and grabbing frames over MCP | any animation |
| [references/motion.md](references/motion.md) | Movers (studs, blinds, plugs), installation sequences, valve handles, poses from ports, moving along a pipe centreline, contact and rigid-link solves | building the moves |
| [references/verification.md](references/verification.md) | What to check before playing and before handing over | any animation |

## Worked example

`examples/Piping_install_animation/valve_lockout_animation.py` with
`Header_with_pig_launcher.FCStd`: a lockout on a launcher header. A vent
valve opens, the drain-outlet studs and blind come off, the drain valve
opens, then the closure studs and blind come off. It splits each Quetzal
valve into a body and a handle so the handle can turn (Conventions). It
keeps home placements in the document, and plays through `anim_tools.Player`.

## Workflow

1. **Confirm the session** (`check_freecad_connection`, then the
   quetzal-piping §2 preamble). List every open document with its
   `FileName` and `Modified` flag, and note which one is **active**. If the
   active document is a saved file **with unsaved changes**, your first
   `execute_python` will autosave it, even a read-only call. Stop and tell
   the user. Make a scratch document active first (`view_control
   create_document`) whenever you are unsure.
2. **Pin down the sequence.** What moves, in what order, from what starting
   state (which valves open, which blinds on), what goes transparent so the
   action is visible, where removed parts go, and what the end state is. For
   an installation: the order the spools go in, where they come from
   (laydown, truck, overhead), and whether bolt-up is shown. Ask whether a
   macro and a saved `.FCStd` are wanted. Default to both.
3. **Work in a copy.** `shutil.copyfile` the user's model to a new name
   beside the macro, then `openDocument` the copy. Never animate in the
   user's original: an animation adds objects and properties, and the bridge
   autosaves mid-animation.
4. **Write the macro** in the shape of the example. It solves the geometry
   from the model, then `_timeline()` returns the steps. It provides
   `setup()` (or `build()` for one-time objects), `play()` (which always
   resets first), `stop()` and `reset()`. Exec it in the session and run
   setup without playing, and read its report. To extend an existing
   animation, subclass it and splice its timeline. Don't copy it
   (references/timeline-and-playback.md).
5. **Verify before playing** (references/verification.md). Explain every
   overlap that remains.
6. **Grab frames, then play once in real time.** Pose frames with
   `anim_tools.step_to(steps, i, u)` and `saveImage`, and look at every
   one. Then `play()` once, pumping with `anim_tools.play_blocking` in calls
   of about 50 s, until `p.done()`.
7. **Reset and save.** `reset()`, then `doc.save()`. The `Modified` flag can
   still read `True` for one call after a save. Re-check it in the next call
   before you conclude anything.
8. **Hand over.** Give the files and how to replay (`play()`, `stop()`,
   `reset()`), the numbers (travels, clearances, path-end errors), the
   expected overlaps and why, and which documents the bridge autosaved.

## Conventions

- **Find parts by mark** (`anim_tools.mark(doc, "F6")` matches the label
  `"[F6] ..."`) and spools by their exact `App::Part` label
  (`anim_tools.label`). Take every point and direction from `Ports` /
  `PortDirections` through `getGlobalPlacement()` (`wpos`, `wdir`). Never
  type a coordinate from the model into the macro.
- **Update placements only.** Do not `recompute()` the document per frame.
  The view updates from a Placement change alone. A `Part::Feature` whose
  `Shape` is rebuilt each frame (a rope, a hoist line) is fast enough for a
  few simple solids.
- **Home state lives in the document.** `anim_tools.save_homes(holder,
  objs)` records each mover's placement, visibility and transparency in a
  `PropertyMap` on a holder object, written once at the start state.
  `restore_homes` puts them back. `reset()` then works after the file is
  saved mid-animation and reopened.
- **Valve state:** open is green `(0.10, 0.70, 0.20)` and closed is red
  `(0.85, 0.10, 0.10)`, on `ViewObject.ShapeColor`. There are two ways to
  show the actuator:
  - *Jump:* switch Quetzal's `Actuator` (`Handle` / `Handle-closed`,
    `Handwheel` / `Handwheel-closed`) with `anim_tools.set_valve`. It
    rebuilds the valve (about 0.8 s for a gate valve), so do it in an
    instant step, and only when the value changes. A geared ball valve has no
    closed gearbox and only changes colour.
  - *Turn:* Quetzal fuses the handle into the valve solid, so it cannot
    rotate in place. Hide the valve, and show a body and a handle cut from
    its shape at the top of the body, with the handle placed by an expression
    of an angle property (`valve_lockout_animation.build()`). Tween the
    angle.
- **Transparency** is `ViewObject.Transparency` on each member of a spool
  `App::Part`. The container has none (`anim_tools.set_transparency(part.Group,
  60)`). It is hard to see in a fit-all image, so zoom in before you judge
  it.
- **Removed parts** leave in the reverse of how they went on: studs back off
  along their own axis and hide, then the blind backs off and moves aside.
  Put them back in reverse order.

## Pitfalls that have already cost a round

- **Autosave of the user's active document.** The bridge saves the active
  document before each call if it has a path and unsaved changes. Check
  which document is active and whether it is modified *before* the first
  call. Git can restore a tracked file.
- **Moving or renaming files that FreeCAD has open.** FreeCAD re-saves them
  to the old path. Save any real changes, `closeDocument`, then move.
- **A blocking `time.sleep` loop** freezes the GUI and the MCP bridge for
  the whole sequence, and nothing can stop it. Use the `Player`, which runs
  on a `QTimer`.
- **Keep a reference to the player.** A `QTimer` with no reference is
  garbage-collected and the animation stops. `Player.start()` stores itself
  on `FreeCAD.__anim_player__`.
- **`BoundBox` is loose on curved faces** (0.08 mm short on a pig), and so
  is `optimalBoundingBox()` (up to 1 mm long). For contact and clearance use
  `distToShape`, never a bounding box.
- **Duplicate labels from `mergeProject`.** FreeCAD appends `001` to any
  merged label that already exists, including inside a mark label and on
  containers. Fix them, then assert that no mark and no `App::Part` label
  repeats, because the macro looks parts up by both.
- **A macro that finds a part by an old label** breaks when the user
  relabels it. Prefer marks, and make the label a module constant that a
  subclass can override.
- **Expected overlaps that are not clashes.** A stud set is one rigid solid,
  so its inner nuts overlap the flange for the first 15–30 mm of
  withdrawal. Quetzal does not cut the run-pipe wall under a weldolet or
  sockolet, so anything drawn through the outlet overlaps by its
  cross-section × the wall. Report both with the numbers. Don't treat them
  as clashes.
- **`result`, `__name__` and stale names:** see quetzal-piping §2.2.
  Re-exec the macro into a fresh namespace dict after every edit, and pass
  `__file__` so it can find `anim_tools.py`.
- **Shell quoting:** long Python patch scripts sent through a Bash heredoc
  have broken on quotes. Write the script to the scratchpad and run the
  file.

## Deliverables

- The macro and the `.FCStd` go in `examples/<name>/`, next to each other,
  or in the gitignored `private/` for anything from a real site (see
  `AGENTS.md`). Write the `.py` from code that actually ran, then re-exec it
  and check that its report matches the live build.
- The `.FCStd` is saved **reset to its starting state**.
