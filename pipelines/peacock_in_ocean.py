"""Request: "Create a peacock in the ocean."

The plan below is the 18-step breakdown from the project brief, executed as a painting pipeline.
The peacock is generated from the learned figure recipe (figure/peacock-standing) and eyespot
pattern (texture/peacock-eyespot); the ocean is painted with perspective waves, Fresnel sky
reflection and a sun-glitter path. No photo is composited and no generative model is used.

Run:   python pipelines/peacock_in_ocean.py
Output: projects/peacock-in-the-ocean*/exports/ + previews/ + pipeline.json
"""

import numpy as np

from image_studio.paint import brush, finish, scene
from image_studio.patterns import PatternLibrary
from image_studio.pipeline import Pipeline

W, H = 1600, 1000
HORIZON = 470
SUN = (1180, 445)               # low sun just above the horizon, right of frame centre
WATERLINE = 860                 # the peacock stands in shallow water; its feet are hidden at this line
LIGHT_AZ, LIGHT_EL = 335, 12    # sun from the right and slightly behind the bird -> warm rim, cool front
SKY = ["#1f2f5c", "#5b5a86", "#d98a6a", "#f6c27a"]

peacock = PatternLibrary().get("figure/peacock-standing").params

p = Pipeline(
    "Create a peacock in the ocean",
    plan=[
        "Search for peacock images and read the knowledge base and pattern library entries for peafowl",
        "Search the peacock borders in the images: silhouette of a standing male with a closed train",
        "Understand the peacock pattern: iridescent neck scales, barred wings and train eyespots",
        "Understand peacock lighting from other light directions: backlit rims and iridescent colour shifts",
        "Search for ocean images at sunset and record horizon, wave and colour observations",
        "Search ocean borders in the images: horizon line, shallow water edge and surf",
        "Search for objects in oceans: rocks, birds and waders standing in shallow water",
        "Understand patterns of objects in the ocean: submerged feet, ripple rings and broken reflections",
        "Understand lighting, shadow and reflection of objects in the ocean with a low sun",
        "Understand sun lighting of the ocean: glitter path, Fresnel sky reflection and horizon haze",
        "Generate the new ocean scene from the learned patterns: sunset sky, clouds, sun and waves",
        "Generate the new peacock from the extracted patterns using the figure recipe",
        "Set the peacock in the ocean standing in shallow water on the left third",
        "Blend the peacock lighting into the ocean lighting with a warm rim light and cool fill",
        "Blend the peacock shadows into the ocean: contact darkening and waterline ripples",
        "Blend the peacock ocean reflections: mirrored, tinted and broken by ripples",
        "Apply final touches to blend everything together: grade, haze, vignette and grain; inspect previews",
        "Return the final image: export PNG, JPEG and layered ORA and report limitations",
    ],
    size=(W, H), name="Peacock in the ocean", seed=11)

with p.step(1):
    p.note("Reused library entries: figure/peacock-standing, texture/peacock-eyespot, palette/peacock")
with p.step(2):
    p.note("Standing male: small head with fan crest, long blue neck, train of coverts trailing ~2.3x height")
with p.step(3):
    p.note("Neck/breast cobalt with scale texture; wing coverts barred buff/black; ~100-175 train eyespots")
with p.step(4):
    p.note("Backlit by a low sun: bright warm rims on the sun side, blue neck darkens to deep cobalt")
with p.step(5):
    p.note("Sunset sea: deep blue-violet zenith, orange band at the horizon, darker water toward the camera")
with p.step(6):
    p.note(f"Horizon kept level at y={HORIZON}; no land; shallow water where the bird stands")
with p.step(7):
    p.note("Waders in shallow water: legs disappear at the surface, rings of ripples around them")
with p.step(8):
    p.note("Reflections of standing objects are vertical, darker than the object, broken by ripples")
with p.step(9):
    p.note("Low sun: long faint shadows toward the camera are invisible on water; reflection dominates")
with p.step(10):
    p.note("Glitter path widens toward the camera under the sun; water near the horizon mirrors the sky")

with p.step(11):
    p.add("Sky", scene.sky(W, H, horizon_y=HORIZON, colors=SKY, positions=[0, 0.45, 0.82, 1.0], sun=SUN,
                           sun_color="#ffd9a0", sun_glow=0.75, glow_radius=0.45), group="Ocean scene")
    p.add("Clouds", scene.clouds(W, H, top=120, bottom=HORIZON - 30, coverage=0.4, period=380, color="#f3b08a",
                                 shadow="#4e4a72", light_from=SUN, stretch=4.0, seed=p.seed),
          group="Ocean scene", opacity=0.9)
    p.add("Sun", scene.sun_disc(W, H, x=SUN[0], y=SUN[1], radius=24, color="#fff4dc", halo=4), group="Ocean scene",
          blend="screen")
    p.add("Ocean", scene.ocean(W, H, horizon_y=HORIZON, deep="#14294a", shallow="#2a5a74", sky_color="#7a6f93",
                               horizon_color="#f0b27a", sun_x=SUN[0], sun_color="#ffd7a0", glitter=0.9,
                               wave_size=0.3, choppiness=0.55, seed=p.seed), group="Ocean scene")
    p.add("Horizon haze", scene.haze(W, H, horizon_y=HORIZON, color="#f2b98a", strength=0.45, band=0.035,
                                     noise=0.2, seed=p.seed), group="Ocean scene")
    p.preview("ocean")

with p.step(12):
    p.figure("Peacock", peacock, height=430, x=170, ground_y=WATERLINE + 45, facing="left",
             light_azimuth=LIGHT_AZ, light_elevation=LIGHT_EL, key_color="#ffd6a0", ambient_color="#6f7fb0",
             ambient=0.5, group="Peacock")

with p.step(13):
    # hide the feet below the waterline: the water surface layer is painted over the legs
    water_front = p.blank()
    ys = np.arange(H)[:, None]
    ocean_now = p.layer("Ocean")
    band = (ys >= WATERLINE).astype(np.float32) * np.ones((1, W), np.float32)
    water_front[..., :3] = ocean_now[..., :3]
    # fade in over a few pixels so the train sinks into the water instead of being cut
    soft = np.clip((ys - WATERLINE) / 6.0, 0, 1) * np.ones((1, W), np.float32)
    water_front[..., 3] = band * soft * 0.92
    p.add("Water surface over feet", water_front, group="Peacock")

with p.step(14):
    p.rim_light("Peacock rim light", "Peacock", azimuth=LIGHT_AZ, width=4, color="#ffcf8a", intensity=0.8)

with p.step(15):
    rings = p.blank()
    for i, (rx, ry) in enumerate([(30, 6), (55, 10), (85, 15)]):
        for cx in (432, 478):          # the two legs (figure x + leg x * height)
            pts = [(cx + np.cos(a) * rx, WATERLINE + 4 + np.sin(a) * ry) for a in np.linspace(0, 2 * np.pi, 40)]
            brush.stroke(rings, pts, "#ffe2b8", size=2.2 - i * 0.4, hardness=0.6, opacity=0.6 - i * 0.15,
                         smooth=False)
    p.add("Waterline ripples", rings, group="Peacock", blend="screen")

with p.step(16):
    p.reflection("Peacock reflection", "Peacock", axis_y=WATERLINE + 2, opacity=0.7, fade=0.6, blur=2.0,
                 ripple_amplitude=5, ripple_wavelength=14, tint="#1d3b66", tint_strength=0.3, darken=0.2,
                 group="Peacock")

with p.step(17):
    p.adjust("Grade · curves", "curves", {"points": [[0, 10], [70, 62], [140, 145], [210, 220], [255, 250]]})
    p.adjust("Grade · warm highlights", "color_balance", {"highlights": [0.05, 0.02, -0.04],
                                                         "shadows": [-0.03, 0.0, 0.05]})
    p.add("Vignette", finish.vignette(W, H, amount=0.4, radius=0.72), blend="multiply")
    p.add("Film grain", finish.grain(W, H, amount=0.035, seed=p.seed), blend="overlay", opacity=0.5)
    p.preview("graded")

with p.step(18):
    report = p.finish(formats=("png", "jpeg"))
