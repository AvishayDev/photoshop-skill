# Painting playbook (creating images from scratch)

How a matte painter builds an image, mapped to `image_studio.paint` / pipeline calls. Everything is a
separate named layer, painted back to front.

## Layer order

1. **Sky / light source** - `scene.sky` (zenith→horizon colours, `sun` glow), `scene.sun_disc` (screen),
   `scene.clouds` (lit toward `light_from`).
2. **Far environment** - `scene.mountains`, `scene.forest(...)[0]` (far wall), horizon `scene.haze`.
3. **Ground / water plane** - `scene.ground` or `scene.ocean` (both perspective-correct from `horizon_y`).
4. **Mid environment** - forest depth layers, `brush.grass` (mid), dapples (`soft_light`).
5. **Subject** - `p.figure(...)` from a library recipe (`figure/<name>`), lit with the scene's key light.
6. **Integration** - `p.contact_shadow`, `p.cast_shadow` (multiply), `p.rim_light` (clipped, screen),
   `p.reflection` (water), water surface over submerged parts, foreground grass/leaves in front of feet.
7. **Atmosphere & light** - `scene.light_rays` (screen), `scene.haze`, `scene.dapples`.
8. **Finish** - `p.adjust` curves / color_balance (values -1..1!) / vibrance; `finish.vignette` (multiply);
   `finish.grain` (overlay, 0.3-0.6 opacity).

## Consistency rules

- Pick ONE key light (azimuth/elevation/colour) and pass it to every figure, shadow, rim light, foliage
  and forest call. Shadows fall away from the light; rims appear on the light side.
- Horizon = camera eye level. Objects standing on the ground plane get smaller toward the horizon; a
  subject's feet must sit on the ground plane at its `ground_y`.
- Atmospheric perspective: far = paler, lower contrast, shifted toward the fog/sky colour; near = darker,
  more saturated, more contrast. `scene.forest` does this with `fog`.
- Warm light → cool shadows (and vice versa). Use `ambient_color` for the shadow side (sky blue outdoors,
  green under canopy, violet at dusk).
- Ground the subject: contact shadow (tight, dark), something overlapping its base (grass, water surface),
  and a cast shadow or reflection.

## Figures (subjects)

- Reuse `figure/*` recipes; adjust parts/materials for pose or breed and save improvements back.
- New subject: write a spec (see `paint/figure.py` docstring): parts in figure units (torso as a smooth
  `polygon` contour, limbs as `limb` capsules with `emerge` so they grow out of the body, ellipses for
  heads/paws), materials with colours (top→bottom), `belly`, `pattern` (stripes/spots/scales or a
  library ref like `{"ref": "texture/tiger-stripes"}`), `fur`; details (eyes, nose, strokes, ear spots).
  Feathered trains/fans: a `feathers` part (base, tip_path, count, eyespots).
- Use learned measurements: stripe period/coverage from `learn_pattern`, proportions from the learned
  silhouette (`silhouette/*`), palettes from `palette/*`.
- Render the figure alone first on a neutral background and look at it before placing it.

## Parameter ranges that worked

| Element | Parameters |
| --- | --- |
| Forest (1600x1000) | `trunk_width` 70-100, `trees_per_layer` 8-10, `depth_layers` 4, `fog` 0.6-0.75 |
| Ocean | `wave_size` 0.25-0.4, `choppiness` 0.5, `glitter` 0.8-1.0 with low sun |
| Grass | mid `density` 0.02 `length` (8, 30); foreground `density` ~0.012 `length` (14, 46) - keep paws visible |
| Figure | height 30-45% of the frame for a hero subject; `ambient` 0.35-0.5 |
| Reflection (water) | opacity 0.55-0.7, darken 0.2-0.3, ripple_amplitude 3-6 |
| Grade | curves gentle S; color_balance shadows ~[-0.04, 0, 0.05], highlights ~[0.05, 0.02, -0.04] |

## Failure modes seen (and fixes)

- Cut-out/sticker look → lower rim intensity, add edge fur (`fur.edge_hairs`), haze over the subject.
- Plastic foliage → use `scene.foliage` (leaf dabs) rather than blobs; vary leaf size with depth.
- Tiled/striped ground → seamless noise (`noise.tileable_fbm`) and isotropic sampling.
- Feet floating → contact shadow + an occluding water/grass layer at the contact line.
- Blue/yellow blotches after grading → `color_balance` values are -1..1 (validated now).
- Subject parts reading as separate sausages → torso contour + `emerge` on limbs + low `part_relief`.
