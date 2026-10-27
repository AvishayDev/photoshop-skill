# Editing playbook

## Typical layer structure (top -> bottom), adapt per task

```
Text / graphic overlays            (text, shape layers)
Finishing                          (grain, vignette, bloom - adjustment or procedural layers)
Global grade                       (adjustment layers: curves, color_balance, temperature_tint)
Foreground elements                (leaves, rocks; often blurred for depth)
Light effects                      (god_rays, point/directional light; screen/soft_light)
Subject group
  ├─ Subject corrections           (clipped adjustment layers: match_color, curves, rim light)
  ├─ Subject                       (masked, smart-transformed)
  ├─ Reflection                    (create_reflection)
  └─ Cast + contact shadows        (multiply)
Midground                          (vegetation, terrain)
Distant background + atmosphere    (fog/haze, blurred, low contrast)
Sky / backdrop                     (fill gradient or procedural sky)
Original (locked)                  (when editing a photo)
```

## Order of operations

1. Canvas: size/aspect (`create_project` or `crop_image`/`resize_canvas`).
2. Backdrop and environment from far to near.
3. Subject placement: import -> `remove_background` (mask) -> `transform_layer` (scale/perspective) ->
   mask refinement.
4. Integration: `match_color` -> clipped curves -> shadows -> reflections -> rim/spill light ->
   occluding foreground -> focus/grain match.
5. Global grade and finishing.
6. Text and graphics last (they should not be affected by grading: keep them above adjustment layers).

## Recipes

- **Photo edit, keep original:** `open_document` (Original is locked) -> `duplicate_layer` -> edit the copy.
- **Local adjustment:** `create_selection` (feather) -> `adjust_colors(..., as_adjustment_layer=true,
  use_selection=true)` (the selection becomes the adjustment's mask).
- **Clipped correction for one layer:** `adjust_colors(layer_id=subject, as_adjustment_layer=true)`
  (clipped by default).
- **Depth of field:** blur background layers more than midground; or `apply_filter gradient_blur` on a
  merged background copy.
- **Sky replacement:** new sky layer below the photo copy; mask the photo's sky via `select_by_color`
  (contiguous from a sky point, tolerance 25-45) -> `create_layer_mask(source='selection', invert=true)`;
  match horizon colour with a gradient-masked `temperature_tint`.
- **Object removal:** select object with margin -> `remove_object` -> `clone_stamp` structure ->
  `heal_region` seams -> `inspect_image` for repeated patches.
- **Text:** `create_text_layer` with `max_width` for wrapping; legibility: `add_layer_effect` stroke or
  drop_shadow, or a semi-transparent shape layer behind the text.
- **Native GIMP filters:** `apply_filter(filter='gegl:...', backend='gimp')`; inspect properties with
  `describe_gimp_filter`. Examples: gegl:noise-reduction, gegl:shadows-highlights, gegl:lens-distortion,
  gegl:bilateral-filter, gegl:wind, gegl:oilify.

## Parameter starting points (2000 px wide images; scale proportionally)

| Purpose | Tool / params |
| --- | --- |
| Hair/fur edge | feather_mask 1-2, edit_layer_mask contrast 0.2 |
| Product edge | feather_mask 0.5-1 |
| Contact shadow | add_contact_shadow blur 4-8, opacity 0.7 |
| Sunrise cast shadow | add_cast_shadow elevation 10-25, softness 0.5-0.7, opacity 0.45 |
| Midday cast shadow | elevation 55-75, softness 0.25 |
| Calm water reflection | create_reflection ripple 0-1.5, blur 1, opacity 0.75 |
| Ocean reflection | ripple 4-8, wavelength 12-20, blur 3, fade 0.5, opacity 0.5 |
| Film grain | apply_filter add_noise amount 0.012-0.025 monochrome |
| Gentle S-curve | curves [[0,8],[64,56],[192,202],[255,250]] |
