"""Pipelines: the agent writes a Python file (or JSON spec) of painting actions that builds the image.

    from image_studio.pipeline import Pipeline
    from image_studio.paint import scene

    p = Pipeline("Create a tiger in a forest, realism style", plan=[...10+ steps...], size=(1600, 1000))
    with p.step(5, "paint the sky"):
        p.add("Sky", scene.sky(p.width, p.height, horizon_y=520), group="Environment")
    ...
    p.preview("environment")     # look at it, fix, re-run
    p.finish()                   # layered project + PNG/JPEG + ORA + pipeline report
"""

from .pipeline import Pipeline
from .spec import ACTIONS, run_spec

__all__ = ["ACTIONS", "Pipeline", "run_spec"]
