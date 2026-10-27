"""Request: "Create a tiger in a forest, realism style."

A pipeline written the way the image-studio skill asks Claude to work: a 10+ step plan, knowledge and
pattern-library lookups, references studied and measured (texture/tiger-stripes, silhouette and palette
were learned from a CC0 photo), then the image is PAINTED from scratch with procedural tools - no
photo is composited and no generative model is used.

Run:   python pipelines/tiger_in_forest.py
Output: projects/tiger-in-a-forest*/exports/ (PNG, JPEG, layered ORA) + previews/ + pipeline.json
"""

from image_studio.paint import brush, finish, scene
from image_studio.patterns import PatternLibrary
from image_studio.pipeline import Pipeline

W, H = 1600, 1000
HORIZON = 520            # eye level ~ a crouching photographer: the tiger's back sits near the horizon
GROUND = 880             # where the tiger's paws touch the forest floor
SUN = (260, -120)        # sun high on the upper left, behind the canopy
LIGHT_AZ, LIGHT_EL = 150, 45     # light comes from the front-left and above (lights the tiger's face)
FOG = "#c4cbb0"
LEAVES = ["#0f1f0c", "#24411a", "#4a7128", "#9bb95a"]

library = PatternLibrary()
tiger = library.get("figure/tiger-walking").params        # reused recipe (learned stripes inside)

p = Pipeline(
    "Create a tiger in a forest, realism style",
    plan=[
        "Search the knowledge base and pattern library for tiger, fur, stripes, forest and natural light",
        "Research tiger references: side-view silhouette, stripe layout, white markings, ear spots, tail tip",
        "Learn tiger patterns from a CC0 reference photo: stripe period and coverage, palette and outline",
        "Research forest structure: depth layers, trunk spacing, canopy, undergrowth and atmospheric haze",
        "Define the composition: 16:10 frame, tiger walking left on the lower third, eye level near its back",
        "Paint the light through the canopy: warm glow upper left and hazy far forest wall",
        "Build the forest in four depth layers, paler and smaller with distance, lit from the front-left",
        "Paint the forest floor with perspective texture, a worn path and grass blades",
        "Generate the tiger from the learned figure recipe and stripe pattern, lit from the front-left",
        "Blend the tiger into the scene light: contact shadow, cast shadow and dappled sun flecks",
        "Add god rays and depth haze so the subject separates from the background",
        "Integrate the paws with foreground grass in front of the tiger",
        "Apply a unifying colour grade, vignette and film grain with adjustment layers",
        "Render previews, inspect the image for defects and verify scale, light direction and edges",
        "Export PNG and JPEG plus the layered ORA project and report limitations",
    ],
    size=(W, H), name="Tiger in a forest", seed=7)

with p.step(1, "knowledge/subjects/animals/tiger.md, materials/fur.md, environments/forest.md"):
    p.note("Reused: figure/tiger-walking, texture/tiger-stripes, palette/tiger-coat (pattern library)")
with p.step(2):
    p.note("Stripes mostly vertical on the torso, horizontal on legs/forehead; white muzzle, chest, belly; "
           "white spot on the back of each ear; ringed tail with a black tip (animalia.bio, a-z-animals.com)")
with p.step(3):
    p.note("Measured on a CC0 photo: dark marks ~38% of the coat, stripe period ~0.11 x body height")
with p.step(4):
    p.note("Forest: dense far wall in haze, mid trunks paler and narrower, near trunks dark and large; canopy "
           "closes the top of the frame; light reaches the floor in shafts and flecks")
with p.step(5):
    p.note(f"Horizon y={HORIZON}, ground contact y={GROUND}, sun at {SUN} (azimuth {LIGHT_AZ}, elevation {LIGHT_EL})")

with p.step(6):
    p.add("Sky glow", scene.sky(W, H, horizon_y=HORIZON, colors=["#b8c7a0", "#e3e2bd", "#f2e7c2"],
                                sun=SUN, sun_color="#fff3cf", sun_glow=0.8, glow_radius=0.5), group="Environment")

with p.step(7):
    layers = scene.forest(W, H, horizon_y=HORIZON, depth_layers=4, trees_per_layer=9, trunk_width=90,
                          foliage_colors=LEAVES, fog_color=FOG, fog=0.72, light_azimuth=LIGHT_AZ, seed=p.seed)
    for name, lay in layers[:-1]:                     # far wall .. mid layers behind the floor detail
        p.add(f"Forest {name}", lay, group="Environment")

with p.step(8):
    p.add("Forest floor", scene.ground(W, H, horizon_y=HORIZON, near="#3b2d1c", far="#857d5e", texture=0.55,
                                       period=0.9, detail_colors=["#2a2014", "#5b4a2e", "#7d6a42", "#4c5626"],
                                       seed=p.seed), group="Environment")
    path = p.blank()
    brush.stroke(path, [(620, HORIZON + 30), (760, 640), (700, 760), (520, 1000)], "#8c7a58", size=120,
                 size_end=520, hardness=0.1, opacity=0.55)
    p.add("Worn path", path, group="Environment", blend="soft_light")
    p.add("Forest floor dapples", scene.dapples(W, H, size=70, coverage=0.3, stretch=3, region=[0, HORIZON + 40, W, H],
                                                seed=p.seed), group="Environment", blend="soft_light", opacity=0.6)
    p.add("Mid grass", brush.grass(W, H, top=HORIZON + 40, bottom=GROUND - 40, density=0.02, length=(8, 30),
                                   colors=["#273a14", "#4d6a22", "#8fa64a"], thickness=1.6, seed=p.seed),
          group="Environment")
    near_name, near = layers[-1]
    p.add(f"Forest {near_name}", near, group="Environment")
    p.preview("environment")

with p.step(9):
    p.figure("Tiger", tiger, height=350, x=430, ground_y=GROUND, facing="left", light_azimuth=LIGHT_AZ,
             light_elevation=LIGHT_EL, key_color="#fff0d2", ambient_color="#9fae8a", ambient=0.4, group="Tiger")

with p.step(10):
    p.contact_shadow("Tiger contact shadow", "Tiger", ground_y=GROUND - 4, blur=7, opacity=0.75, group="Tiger")
    p.cast_shadow("Tiger cast shadow", "Tiger", azimuth=LIGHT_AZ, elevation=LIGHT_EL, ground_y=GROUND - 6,
                  opacity=0.38, softness=0.7, group="Tiger")
    p.rim_light("Tiger rim light", "Tiger", azimuth=LIGHT_AZ, width=3, color="#ffe6b8", intensity=0.45)

with p.step(11):
    p.add("God rays", scene.light_rays(W, H, origin=SUN, angle=62, spread=34, count=10, intensity=0.42,
                                       length=1.6, color="#fff1c4", seed=p.seed), blend="screen")
    p.add("Depth haze", scene.haze(W, H, horizon_y=HORIZON + 10, color=FOG, strength=0.55, band=0.12, seed=p.seed),
          opacity=0.85)

with p.step(12):
    p.add("Foreground grass", brush.grass(W, H, top=GROUND - 8, bottom=H + 40, density=0.012, length=(14, 46),
                                          colors=["#1e2e0f", "#3f5a1c", "#7f9a3c"], thickness=2.4, seed=p.seed + 1,
                                          perspective=False))

with p.step(13):
    p.adjust("Grade · curves", "curves", {"points": [[0, 8], [64, 56], [128, 128], [200, 210], [255, 248]]})
    p.adjust("Grade · warm highlights, cool shadows", "color_balance",
             {"shadows": [-0.04, 0.0, 0.05], "highlights": [0.05, 0.02, -0.04]})
    p.adjust("Grade · vibrance", "vibrance", {"amount": 0.15})
    p.add("Vignette", finish.vignette(W, H, amount=0.45, radius=0.7), blend="multiply")
    p.add("Film grain", finish.grain(W, H, amount=0.05, seed=p.seed), blend="overlay", opacity=0.6)

with p.step(14):
    p.preview("graded")
    p.note("Inspect: tiger scale vs trunks, paws grounded, light from the front-left on face and shoulder, "
           "shadow falling back-right, stripes readable, no hard cut-out edge")

with p.step(15):
    report = p.finish(formats=("png", "jpeg"))
