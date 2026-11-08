# Sign frame: bill of materials and cut list

The frame holds a 108" × 54" sign. All material is 1-1/2" Sch-40 PVC. The model
(`sign_frame.FCStd`) uses 3000# socket-weld fittings (ASME B16.11) to stand in
for the PVC fittings. The centreline dimensions are the same for both. Only the
fitting take-out differs, so the cut list gives both versions.

Source: the sketch `IMG_3096.JPEG`.

## Frame geometry (centreline)

| Item | Derivation | mm | in |
|---|---|---|---|
| Pipe OD, 1-1/2" Sch-40 | `Pipe_SCH-40.csv` | 48.26 | 1.900 |
| Horizontal, post CL to post CL | 108 + 2 × 2 clear + OD | 2893.06 | 113.90 |
| Vertical, top rail CL to bottom rail CL | 54 + 2 × 2 clear + OD | 1521.46 | 59.90 |
| Clear gap, sign edge to pipe OD | 2" on all four sides | 50.80 | 2.00 |

## Bill of materials

| Qty | Description | Marks |
|---|---|---|
| 2 | Elbow 90°, 1-1/2", Sch-40 PVC socket (modelled as 3000# SW) | E1, E2 |
| 2 | Tee, 1-1/2", Sch-40 PVC socket (modelled as 3000# SW) | T1, T2 |
| 6 pcs | Pipe, 1-1/2", Sch-40 PVC, cut to length (see the cut list) | P1–P6 |
| — | Total pipe: 29.6 ft (PVC take-out) or 29.4 ft (3000# take-out) | |
| 3 | Stock to buy: 10 ft sticks (nesting below) | |
| — | PVC primer and solvent cement (not modelled) | |

## Cut list

The cut length runs from socket bottom to socket bottom, so it includes the full
socket engagement at each end. The two legs have open bottom ends. They are
shorter than the sketch's 1'-0", because each is the offcut from a rail stick
(see Nesting).

| Mark | Piece | Qty | CL–CL (in) | Cut, 3000# SW model | Cut, PVC Sch-40 |
|---|---|---|---|---|---|
| P1 | Top rail, E1–E2 | 1 | 113.90 | 2829.1 mm = **9'-3 3/8"** | 2842.3 mm = **9'-3 7/8"** |
| P4 | Bottom rail, T1–T2 | 1 | 113.90 | 2829.1 mm = **9'-3 3/8"** | 2842.3 mm = **9'-3 7/8"** |
| P2 | Left post, T1–E1 | 1 | 59.90 | 1457.5 mm = **4'-9 3/8"** | 1470.7 mm = **4'-9 7/8"** |
| P3 | Right post, T2–E2 | 1 | 59.90 | 1457.5 mm = **4'-9 3/8"** | 1470.7 mm = **4'-9 7/8"** |
| P5 | Left leg, below T1 | 1 | — | 201.6 mm = **7 15/16"** | 201.6 mm = **7 15/16"** |
| P6 | Right leg, below T2 | 1 | — | 201.6 mm = **7 15/16"** | 201.6 mm = **7 15/16"** |

Cut lengths are rounded to the nearest 1/16". In both columns, cut length =
CL–CL − 2 × take-out:

- **3000# SW:** E = 32 mm (1.26"), from `Elbow_3000lb_SW.csv` and
  `Tee_3000lb_SW.csv`.
- **PVC Sch-40:** G = 1.00", centre to socket bottom. Spears gives G = 1" for
  the 1-1/2" Sch-40 tee. For the 90° elbow (406-015), Spears gives
  centre-to-face H = 2-3/8", which with the 1-3/8" ASTM D2466 socket depth
  also leaves 1". **Check G on the fittings you actually buy.** The value
  varies by manufacturer, and each 1/16" of difference changes every rail and
  post by 1/8".

## Nesting

Three 10 ft (120") sticks, using the PVC lengths and a 1/8" saw kerf per cut:

| Stick | Pieces | Used, with kerf | Drop |
|---|---|---|---|
| 1 | P1 top rail + P5 leg | 119.96" | 0.04" |
| 2 | P4 bottom rail + P6 leg | 119.96" | 0.04" |
| 3 | P2 + P3 posts | 115.93" | 4.08" |

Leg length = 120" − rail (111.90") − one kerf (0.125") = 7.975", rounded down
to 7 15/16". Cut each rail first, then trim its offcut to 7 15/16" so the two
legs match. The leg length follows the rail length, and so it follows the PVC
take-out. If the PVC take-out of your fittings changes the rail, recompute the
leg. The spreadsheet does this automatically.

## Assumptions

- The sketch shows the 2" clearance only at the top. The same 2" is applied on
  all four sides.
- Each tee's run is on the post and its branch carries the bottom rail. The
  legs continue straight down out of each tee.
- The legs were shortened from the sketch's 1'-0" to 7 15/16" so the frame
  fits on three 10 ft sticks. That lowers the frame by about 4". The bottom of
  the legs is now 8.94" below the bottom-rail centreline with PVC fittings
  (9.20" in the 3000# model). The model is about 70.3" tall overall.
- The sign appears in the model as a reference solid
  (`[REF] Sign 108x54 (not in BOM)`, 1/4" thick, centred in the opening). It
  is not part of the frame.
