# Sign frame: the prompts that built this example

These are the user's prompts, in order, that produced the files in this
folder. Each one ran in a single Claude Code session, against a live FreeCAD
1.1 session with the Quetzal workbench, over MCP.

The only starting point was the hand sketch, [`IMG_3096.JPEG`](IMG_3096.JPEG).

## 1. Model, BOM and cut list

> Generate a piping model of the sketch of the sign frame in
> @examples/sign_frame . The frame will be constructed of Sch-40 PVC pipe and
> fittings but can be modeled with 3000# socket fittings. Generate a bill of
> materials, and a list of cut pipe lengths.

Before building, the agent asked three questions. The user's answers:

| Question | Answer |
|---|---|
| Which fitting take-out should the cut list use? A 3000# SW fitting's E = 32 mm differs from a PVC fitting's | Both: the 3000# SW model, plus a PVC column |
| Does the "1'-0" long leg pipe" give the pipe cut length, or tee CL to the end of the leg? | Pipe cut length |
| What should be saved to `examples/sign_frame/`? | The FCStd model and a BOM/cut-list file. No Python macro |

Produced: `sign_frame.FCStd` and `sign_frame_BOM.md`.

## 2. Excel version

> Convert the @examples/sign_frame/sign_frame_BOM.md to an Excel file

Produced: `sign_frame_BOM.xlsx`. Every value in it is a formula driven by
the Inputs sheet.

## 3. Fit the frame on three 10 ft sticks

> I think we can make this work with 3 sticks of 10' PVC if we reduce the
> length of the bottom legs from 1' to whatever leftover length we have from
> the top and bottom rails. Make this adjustment

The legs became 7 15/16": a 10 ft stick less one rail (PVC cut length) and
one 1/8" saw kerf, rounded down to 1/16". The model, the spreadsheet and the
markdown BOM were all updated.

## 4. Drawing

> Generate a TechDraw profile drawing showing the assembly and dimensions of
> the frame.

Produced: a TechDraw page in `sign_frame.FCStd`, also exported as
`sign_frame_elevation.pdf`. It has:
- a front elevation at 3/4" = 1'-0", with balloons and centreline dimensions;
- an isometric for reference;
- the BOM and cut list;
- notes.

## 5. This file

> Add a markdown file to this folder with the prompts that got it to this
> point.
