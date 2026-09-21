# AI Piping Design

Guidelines for using AI large language models for piping design in CAD programs.

Instructions and worked examples for an **AI agent that builds piping designs** —
spools, runs, trap stations, tie-ins — in CAD, from a natural-language prompt, a
hand-drawn isometric, a commercial drawing, or a photograph of the real thing.

The hard part is not the geometry. It is the judgement around it: reading
dimensions to work points rather than to cut lengths, solving a stated
relationship through the port chain instead of tuning a constant until it looks
right, knowing when a hundred millimetres of disagreement means the joint should
have no pipe in it at all, and verifying every constraint numerically before
claiming the model is done. That knowledge lives in
[`docs/freecad-quetzal-guide.md`](docs/freecad-quetzal-guide.md).

**Scope today:** FreeCAD, driven over MCP, building with the Quetzal workbench.
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

## Pointing this repo at your Quetzal installation

Nothing in this repo vendors Quetzal's dimension tables; they are read live from
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

In FreeCAD, **Macro → Execute** (or paste into the Python console):

```
examples/spool_8in_600_elbow/make_spool_8in_600_elbow.py
```

It builds an 8" 600# spool — WN flange, 36" of Sch-STD pipe, a 90 LR elbow, 24"
more pipe, an SO flange — saves the result beside itself, and prints the §8
sanity checks to the report view. If it raises `QuetzalNotFound`, see the
section above.

## What is here

### `docs/`

[`freecad-quetzal-guide.md`](docs/freecad-quetzal-guide.md) — the guide. Golden
rules, the `pCmd` maker catalog, flanges, ports and `alignTwoPorts`, the
`tablez/` tables, the build-and-verify loop over MCP, and three chapters on
sources: reading an isometric (§9), building from a text prompt (§11), and
building from a field photograph (§12).

### `examples/`

Each folder holds one macro, its source material where there is one, and the
`.FCStd` it produces.

| | |
|---|---|
| `spool_8in_600_elbow/` | The canonical worked example. Start here. |
| `spool_4in_300_inline/` | In-line spool with a 1" 3000# sockolet clocked at 90°, plus gaskets, bolts and blinds. |
| `iso_3in_tee_run/` | From a hand-drawn isometric: 3" 600# flange / elbow / equal tee. |
| `iso_10in_300_branch_run/` | From a hand-drawn isometric: 10" U-run with two 2" weldolet branches, keyed to a BOM. |
| `sketch_4in_150_tee_spool/` | From a phone photo of a pencil sketch: 4" 150# tee spool. |
| `sketch_3in_300_tee_drop_spool/` | From a phone photo of a pencil sketch: 3" 300# tee-drop spool. |
| `launcher_drain_addition/` | The odd one out — it *modifies* an existing model, deleting a blind flange and building a 2" Sch-80 drain run in its place. |

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
- **Macros write only beside themselves.** Nothing in this repo writes into your
  Quetzal installation.

## License

MIT — see [LICENSE](LICENSE).

This repo contains documentation and example macros. It does not include or
modify Quetzal, which is licensed separately under LGPL-3.0-or-later; the macros
import it at runtime from your own installation.
