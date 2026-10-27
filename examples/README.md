# Examples

- `peacock_in_the_ocean.py` — a complete agent-style session over the MCP stdio protocol: capabilities,
  knowledge lookup, a 19-step plan, live research (Wikimedia Commons, Openverse), license-checked assets,
  compositing (GrabCut mask, colour matching, rim light, waterline, ripples, reflection, cast shadow),
  inspection, a correction round driven by what the first preview showed, ORA/XCF/PNG/JPEG delivery with
  credits, and a knowledge-base update. Needs network access.

```bash
python examples/peacock_in_the_ocean.py
# -> projects/peacock-in-the-ocean/exports/
```

The script prints the paths of the pass-1 preview and the final export so you can compare them.
