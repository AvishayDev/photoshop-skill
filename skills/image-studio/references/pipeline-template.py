"""Request: "<the user's request, verbatim>"

Copy to pipelines/<slug>.py, fill in, run with `python pipelines/<slug>.py`, then LOOK at every preview.
"""

from image_studio.paint import brush, finish, scene  # noqa: F401  (patterns, shapes, figure, noise too)
from image_studio.patterns import PatternLibrary
from image_studio.pipeline import Pipeline

W, H = 1600, 1000
HORIZON = 520                  # camera eye level
GROUND = 880                   # where the subject touches the ground
LIGHT_AZ, LIGHT_EL = 150, 40   # where the key light comes FROM (0 right, 90 front, 180 left, 270 behind)

lib = PatternLibrary()
subject = lib.get("figure/<name>").params          # reuse; or write a new figure spec here

p = Pipeline("<request>", plan=[
    "<10+ easy, clear, request-specific steps: research, learn patterns, paint environment, "
    "generate subject, blend light/shadow/reflection, final touches, inspect, export>",
], size=(W, H), name="<project name>", seed=1)

with p.step(1):
    p.note("what was reused from the library / knowledge base")
# research + learning steps: record what you learned and saved (p.note)

with p.step(5):
    p.add("Sky", scene.sky(W, H, horizon_y=HORIZON, sun=(1200, 300)), group="Environment")
    p.preview("environment")

with p.step(8):
    p.figure("Subject", subject, height=340, x=500, ground_y=GROUND, facing="left",
             light_azimuth=LIGHT_AZ, light_elevation=LIGHT_EL)
    p.contact_shadow("Subject contact shadow", "Subject")
    p.cast_shadow("Subject cast shadow", "Subject", azimuth=LIGHT_AZ, elevation=LIGHT_EL, opacity=0.4)

with p.step(10):
    p.adjust("Grade · curves", "curves", {"points": [[0, 8], [64, 58], [192, 205], [255, 250]]})
    p.add("Vignette", finish.vignette(W, H), blend="multiply")
    p.preview("graded")

with p.step(11):
    p.finish()
