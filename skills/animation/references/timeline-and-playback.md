# Timeline and playback

Part of the `animation` skill. The helpers named here are in
`anim_tools.py` at the repo root.

## Structure

```python
import anim_tools as at
sc = Scene(doc)              # find parts, record homes, solve all geometry once
steps = _timeline(sc)        # [(seconds, fn(u)), ...]
p = at.Player(steps).start() # QTimer at 30 fps; 0 s steps are instant actions
```

- **`Scene`** does every lookup and every solve up front: parts by mark,
  ports, directions, travels, stop points, paths. It records home state with
  `save_homes`. Nothing in a step searches the document or solves anything,
  so a frame costs only placement updates.
- **`_timeline(sc)`** builds the steps with `at.Timeline()`:
  - `hold(sec)`: nothing changes;
  - `instant(fn)`: `fn()` once (a visibility switch, a transparency change,
    an `Actuator` switch);
  - `tween(sec, fn)`: `fn(ease(u))` every frame, for anything continuous (a
    handle angle, a pose along a path);
  - `move(obj, delta, sec, start)`: a straight eased translation from a
    fixed start Placement.
- **Every step must be a pure function of `u`** and of values fixed when the
  timeline was built. Pass the start placement explicitly (usually
  `at.home(holder, obj)`, or the end of the previous move). Never read
  `obj.Placement` inside a step to find where to start. Then any step can be
  replayed out of order, which is how frames are grabbed.
- **Module API:** `setup()` (or `build()` for one-time objects such as split
  valve handles), `play()`, `stop()`, `reset()`. `play()` always calls
  `stop_all()` and `reset()` first. `reset()` calls `restore_homes`, then
  puts every valve back in its starting state.

## Extending an animation

To add to an animation that already works, leave it unchanged and build on
it:

- **Load the earlier macro as a module** (`importlib` by relative path) and
  subclass its `Scene`. Look up the new parts in `__init__` *before* calling
  the base `__init__`, if the base records home placements through a method
  (`_movers()`) that the subclass extends. Solve anything that needs the
  base's results after it.
- **Override hooks, not bodies.** Call the base method and then adjust its
  result: a path's last piece, a pose offset, the list of movers or faded
  parts, `reset()`.
- **Splice the timeline.** Call the base `_timeline(sc)`, then assert the
  shape you depend on (for example, "the first step is a 1 s hold").
  Insert with slices, doing the later insert first so the indices hold:
  `steps[-2:-2] = mid`, then `steps[1:1] = pre`.
- If the base reads a module constant at call time (an end label, a speed),
  set it on the base module before you construct the scene.

## Playback over MCP

The timer runs on the GUI thread, and so does `execute_python`. While a
call runs, the timer does not tick. So:

- **For frames, step the timeline yourself.** `at.step_to(steps, i, u)`
  runs every step before `i` to its end, then step `i` at `u`. It is the
  same code the player runs, it is deterministic, and a few-minute timeline
  is posed in a fraction of a second. Before picking frames, list the steps
  with their index, seconds and `fn.__qualname__`.
- **Play in real time once**, to prove the player runs to the end:
  `p = play()`, then `at.play_blocking(p, 50)` in successive calls until
  `p.done()`. Keep each call under about 50 s. A few-minute timeline needs
  three or four calls.
- To log the order of events (valve changes, say), wrap the scene's
  setter for that run and print the log afterwards.

## Framing and images

- Frame the shot by selecting the parts of interest and sending
  `Std_ViewSelection`. Selecting an `App::Part` can frame the whole document,
  so select its members instead. A fit-all view of a scene with a crane or a
  long run shows nothing useful.
- Set the view direction to look at the action
  (`Gui.ActiveDocument.ActiveView.setViewDirection`). For a close-up inside
  transparent piping, hide the piping for that shot only.
- `saveImage(path, 1200, 750, "Current")` into the scratchpad, then `Read`
  each image and look at it. A clean run of the code does not prove the
  frame shows what was asked.
- The bridge autosaves the working copy on later calls, mid-animation. Finish
  with `stop()`, `reset()`, `save()`.
