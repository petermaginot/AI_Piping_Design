## Line spec

Size:      2" NPS
Schedule:  Sch-80
Class:     600# SO flanges, 3000# socket-weld fittings for elbows and the union

## Component chain            (in order, end A -> end B)

See [Piping_sketch.png](Piping_sketch.png).

## Existing model

The macro does not build a document from scratch — it **modifies**
`6x8_launcher.FCStd` in this folder: it deletes the DN50 600# blind flange
`Flange013` that blanks the outboard face of the drain ball valve `Valve006`,
and builds the drain run in its place.

Open `6x8_launcher.FCStd` before running the macro, or let the macro open it
from this folder.

## Output

Document: 6x8_launcher   (the existing model, modified in place)
Save:     no             — Save-As to `6x8_launcher_drain.FCStd` yourself if
                           you want to keep the result
