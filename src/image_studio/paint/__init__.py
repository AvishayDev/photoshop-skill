"""Procedural painting engine: the agent's own "brush and Photoshop" for creating images from scratch.

No generative model is involved. Every pixel comes from deterministic, seeded drawing operations that an
artist would do by hand in Photoshop or GIMP - gradients, soft brushes, shape paths, pattern fills, noise
textures, clone-stamp texture synthesis, light/shadow passes and colour grading - driven by parameters the
agent derives from studying references (see :mod:`image_studio.patterns`).

Conventions: images are float32 ``(H, W, 4)`` straight-alpha RGBA in 0..1, masks are float32 ``(H, W)``
in 0..1, coordinates are canvas pixels (origin top-left, y down). Light azimuth is where the light comes
FROM: 0 right, 90 front/camera, 180 left, 270 behind.

Modules:
    canvas    colour helpers, compositing, palette ramps
    noise     value-noise fBm, domain warping, Worley cells, perspective texture mapping
    shapes    anti-aliased paths, ellipses, tapered capsules, organic blobs
    brush     dab-based brush strokes, fur/hair strokes, grass blades
    shading   height-from-silhouette, normals, diffuse/rim/specular lighting
    patterns  stripes, spots/rosettes, eyespots, scales, bark
    scene     sky, sun, clouds, mountains, ground, ocean, forest, grass, light rays, haze
    figure    data-driven subjects (parts + materials + patterns + fur + details)
    finish    colour grading, vignette, grain, depth haze
    synthesis patch-based texture synthesis ("clone stamp" quilting) from a reference exemplar
"""

from . import brush, canvas, figure, finish, noise, patterns, scene, shading, shapes, synthesis

__all__ = ["brush", "canvas", "figure", "finish", "noise", "patterns", "scene", "shading", "shapes", "synthesis"]
