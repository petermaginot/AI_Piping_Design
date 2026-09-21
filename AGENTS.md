# Instructions for an AI agent working in this repo

**Read [`docs/freecad-quetzal-guide.md`](docs/freecad-quetzal-guide.md)
end-to-end before you build anything.** It is long, and it is the point of this
repo: it captures the rules that separate a model that is right from one that
silently produces wrong geometry. Do not skim it and start building.

The short version, which is no substitute for reading it:

- You build in the user's **live FreeCAD GUI session, over MCP** — not headless,
  not by handing them a script to run. Confirm the session first
  (`check_freecad_connection`, Quetzal loaded).
- Units are millimetres. Nominal sizes are DN labels (8" = `DN200`).
- Read dimensions from Quetzal's `tablez/` CSVs through
  [`quetzal_env.py`](quetzal_env.py). Never hardcode a take-out.
- Build with the `pCmd` makers and `alignTwoPorts`. Never reimplement geometry.
- Object properties are `Quantity`, not `float`. Use `qenv.val()` before any
  arithmetic — this is the most common runtime error in these macros.
- A stated relationship ("aligned in X", "6 inches from the weld") is a
  constraint to solve through the port chain, not a constant to tune.
- **Verify numerically in the session before handing over.** A clean build only
  proves the code ran. §8 lists the checks; §10 is the loop.
- Write a `.py` file only if asked, into `examples/<name>/`, and save any
  `.FCStd` beside it. Never write into the user's Quetzal installation.

`examples/spool_8in_600_elbow/` is the reference for the shape a macro should
take. `reference/spool_prompt_template.md` is what to ask the user for when a
prompt is underspecified.

## Do not commit non-public material

This repo is public. Photographs of installed piping, client drawings, site or
asset tags, and models reconstructed from them do not belong here. If the user
supplies such material to work from, use it in the session and keep it out of
the repo — `private/` is gitignored for exactly this.
