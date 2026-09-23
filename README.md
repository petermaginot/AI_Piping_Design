# AI Piping Design

Guidelines for using AI large language models for piping design in CAD programs.

This repo contains instructions and worked examples for an AI agent that builds piping designs in CAD software. The AI agent can be directed from a written prompt, a hand-drawn isometric sketch, a pre-existing drawing, or a photograph of the real thing. Examples here
use FreeCAD, a free open-source CAD program, with the Quetzal piping design workbench, but
the techniquies could also be applied to AutoCAD or any other commercial piping design software
that allows the use of macros or the model context protocol to allow the AI to direct the software.

Large language models are surprisingly capable of interpreting drawings and pictures to figure out the geometry
of the piping arrangement you're trying to model but they need some guidelines so to interpret things correctly.
For example, they need to be told to read dimensions to work points rather than to cut lengths, need to know when
fittings are chained back-to-back rather than having tiny pipe pup slivers that don't meet minimum weld spacing
when they misinterpret the dimensions by an inch or so, and need to be told to re-check after building to make sure the modeled dimensions match the given dimensions. The modelling guidelines are located at 
[`docs/freecad-quetzal-guide.md`](docs/freecad-quetzal-guide.md).

It is also helpful if you give it specifications for the system you are trying to model. See the [Spool prompt template](reference/spool_prompt_template.md), where you can specify pipe schedules, flange classes, etc. for a given model. Also you can include general guidelines for the type of system you are modeling, for instance the [the Pig Trap Guidelines](/reference/pig_trap_guidelines.md) describing the general components required for a pig launcher or receiver. You can add specifications or guidelines for any sort of system you're looking to model.

Once the model exists, the agent can also turn it into a fabrication drawing with FreeCAD's TechDraw workbench —
views, a bill of material, balloons, and dimensions to work points — following
[`docs/freecad-techdraw-guide.md`](docs/freecad-techdraw-guide.md). For flat 2D artwork such as seals, stamps and
title block drawings, there is a companion guide for the Draft workbench at
[`docs/freecad-draft-guide.md`](docs/freecad-draft-guide.md).

Note that for complex arrangements, the AI model rarely gets everything correct on the first try. A bit of back and forth
to nudge it in the correct direction is to be expected. The more detail you can include on your prompting documents, the better.
When prompting with photographs, multiple angles are helpful. Annotating the photos to call out specific components and dimensions is also helpful.

Right now, this repo supports FreeCAD, driven over MCP and the following workbenches:
-Quetzal workbench for modelling piping systems
-TechDraw for generating construction drawings of modeled piping systems
-Draft for 2D artwork and drawing supplements, like title blocks, engineering stamps, etc.
The methodology is not FreeCAD-specific and the intent is to generalize it to
other piping CAD packages, but nothing here is abstracted for that yet.

## Prerequisites

| | |
|---|---|
| [FreeCAD](https://www.freecad.org/) | 0.21 or later, with a **GUI session** — see the note below |
| [Quetzal workbench](https://github.com/oddtopus/quetzal) | supplies `pCmd` and the `tablez/` dimension tables |
| [blwfish/freecad-mcp](https://github.com/blwfish/freecad-mcp) | lets the agent drive that live session |

Quetzal's `execute()` methods write to `fp.ViewObject`, so `Pipe`, `Flange` and
friends only build geometry when a GUI ViewObject exists. Headless `freecadcmd`
fails with `'NoneType' object has no attribute 'Deviation'`. Everything here
targets a running GUI session — via MCP for the agent, via **Macro → Execute**
for you.

TechDraw and Draft are included in the standard FreeCAD installation, so they need no separate install. TechDraw
also needs the GUI: its view providers only exist there, so views never project
under `freecadcmd`. The TechDraw and Draft guides were checked against FreeCAD 1.1.

## Pointing this repo at your Quetzal installation

Nothing in this repo supplies Quetzal's dimension tables; they are read live from
wherever Quetzal is installed. [`quetzal_env.py`](quetzal_env.py) finds it, in
this order:

1. the `QUETZAL_DIR` environment variable;
2. a `.quetzal_path` file at the repo root, containing one path;
3. `FreeCAD.getUserAppDataDir()/Mod/{quetzal,Quetzal}`;
4. `FreeCAD.getResourceDir()/Mod/{quetzal,Quetzal}`.

If Quetzal is installed through the Addon Manager, (3) finds it and there is
nothing to configure. If you are working against a git checkout instead, set one
of the first two. On Windows, prefer `.quetzal_path`: FreeCAD launched from the
Start menu does not inherit an environment variable you set in a shell.

```sh
echo "C:/Users/you/Documents/repo/quetzal" > .quetzal_path
```

`.quetzal_path` is gitignored — it is yours, not the repo's.

## Quickstart

With FreeCAD running, run Claude in your IDE (I use VSCode) with this repo opened. You can then either narrate what you
want it to model, or supply a drawing or photographs to model. 

To recreate the photo example, prompt:

**Create a FreeCAD model of the piping arrangement shown in the photos in @examples/photo_example  . Reference @docs/freecad-quetzal-guide.md . All pipes are 3/4" and 1/2" nominal diameter Schedule 40. All tees and elbows in the photos are 150# socket fittings. Model all fittings as 3000# socket fittings. Note that the photograph's fittings won't exactly match the dimension of the Quetzal model. This may require adjusting the length of individual pipes so that the fitting work points match the dimensions given in the photograph with the tape measure. Tape measure lengths are given in inches.**

After a few minutes, the model responded with a few questions (whether to guess non-specified dimensions or request them, what output was desired, where the measuring tape was referenced from). It mis-judged the roll angle of one of the tees, but the following additional prompt corrected it:

**A correction - the 3/4" socket straight tee [F5] should have its branch pointed in the -Z direction, with the socket ell [F6] having one port oriented with the [F5] fitting and the other pointing in the -Y direction.**

To make a drawing of a finished model, open it in FreeCAD and prompt something like:

**Make a TechDraw drawing of the open spool, with an isometric, front and top view, a BOM and balloons. Reference @docs/freecad-techdraw-guide.md .**

## What is here

### `docs/`

- [`freecad-quetzal-guide.md`](docs/freecad-quetzal-guide.md) — the modelling
  guide, and the core of the repo. Golden rules, the `pCmd` maker catalog,
  flanges, ports and `alignTwoPorts`, the `tablez/` tables, the build-and-verify
  loop over MCP, and three chapters on sources: reading an isometric (§9),
  building from a text prompt (§11), and building from a field photograph (§12).
- [`freecad-techdraw-guide.md`](docs/freecad-techdraw-guide.md) — turning a
  finished spool into a drawing. The welded-only `App::Part` container (which is
  also the performance control), making views actually project, the view
  coordinate frame, the BOM spreadsheet and its text-parsing trap, balloons,
  dimensioning to work points with `AutoCorrectRefs` off, and verifying the page
  numerically.
- [`freecad-draft-guide.md`](docs/freecad-draft-guide.md) — flat 2D artwork with
  the Draft workbench. The build-script / `importlib.reload` loop, `MakeFace`
  defaults, ShapeString text and text on an arc, baking arrays, measuring a
  reference image, and fixing and verifying SVG export.

### `examples/`

Each folder holds one macro, its source material where there is one, and the
`.FCStd` it produces. `photo_example/` is the exception: it is source material
only, because that session asked for the live model and nothing on disk.

| | |
|---|---|
| `spool_8in_600_elbow/` | A worked example. Start here. |
| `spool_4in_300_inline/` | In-line spool with a 1" 3000# sockolet clocked at 90°, plus gaskets, bolts and blinds. |
| `iso_3in_tee_run/` | From a hand-drawn isometric: 3" 600# flange / elbow / equal tee. |
| `iso_10in_300_branch_run/` | From a hand-drawn isometric: 10" U-run with two 2" weldolet branches, keyed to a BOM. |
| `sketch_4in_150_tee_spool/` | From a phone photo of a pencil sketch: 4" 150# tee spool. |
| `sketch_3in_300_tee_drop_spool/` | From a phone photo of a pencil sketch: 3" 300# tee-drop spool. |
| `photo_example/` | From annotated field photos of the real thing: 1/2" and 3/4" Sch-40 run with two socket tees, three socket ells, a union and a reducing coupling, stationed off a tape measure. Source material only — the Quickstart prompt rebuilds it live. |
| `launcher_drain_addition/` | The odd one out — it *modifies* an existing model, deleting a blind flange and building a 2" Sch-80 drain run in its place. |
| `TechDraw_example/` | A TechDraw drawing of a DN150 spool (`Simple_spool.FCStd`): isometric, front and top views, a BOM, balloons and work-point dimensions. The worked example for the TechDraw guide. |

### `reference/`

| | |
|---|---|
| `spool_prompt_template.md` | Fill-in template for specifying a spool, so the agent has to ask less. |
| `pig_trap_guidelines.md` | Domain reference: pressure class, major/minor barrel sizing, kicker and equalization lines, closures, pull ports. |
| `Trap_diagram.svg` | The canonical pig trap layout, referenced by the guidelines. |

### `quetzal_env.py`

Finds the Quetzal installation, imports `pCmd`, and reads `tablez/` rows. Every
macro goes through it rather than carrying its own copy of the lookup.

## Conventions

- **Units are millimetres.** Imperial input is converted: `inches * 25.4`.
- **Nominal sizes are DN labels**, even for imperial NPS — 8" is `DN200`. The
  `PSize` column in the tables is the key.
- **Dimensions come from `tablez/`, never from a number typed into the macro.**
- **Drawings print in the user's unit schema.** A TechDraw dimension or BOM
  quantity reads in inches or millimetres depending on FreeCAD's preferences;
  nominal sizes are shown as names (`6"` or `DN150`), never converted.
- **Macros write only beside themselves.** Nothing in this repo writes into your
  Quetzal installation.

## License

MIT — see [LICENSE](LICENSE).

This repo contains documentation and example macros. It does not include or
modify Quetzal, which is licensed separately under LGPL-3.0-or-later; the macros
import it at runtime from your own installation.
