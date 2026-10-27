# Tool reference

Generated from the MCP server by `python scripts/gen_tool_docs.py` - do not edit by hand.

All tools return JSON with `ok`. Errors return `{ok: false, error: {code, message, hint}}` and are flagged as MCP errors. Tools marked **mutating** require an active plan (`submit_plan`).

## Planning & capabilities

### `get_capabilities`

Report which backends are installed (built-in raster engine, GIMP 3, Photoshop), which operations
are available and their known limitations. Call this before planning so the plan never relies on an
unavailable operation. include_gimp_filters lists GEGL operations (starts GIMP, ~5-15 s).

| parameter | type | default |
| --- | --- | --- |
| `include_gimp_filters` | boolean | false |

### `draft_plan`

Suggest a request-specific plan (>= 10 steps) to adapt. It is a starting point: rewrite steps
so they fit the actual request and context, show the numbered plan to the user, then submit_plan.

| parameter | type | default |
| --- | --- | --- |
| `request` | string | required |
| `document_id` | string or null | null |

### `submit_plan`

Register the numbered plan you have shown to the user (>= 10 distinct, meaningful steps covering
understanding, the edits, visual verification, and saving/exporting). Required before any tool that
modifies an image. Replaces a previous active plan.

| parameter | type | default |
| --- | --- | --- |
| `request` | string | required |
| `steps` | array<string> | required |
| `document_id` | string or null | null |

### `get_plan`

Return the active plan (if any) and whether the plan gate is enforced.

### `complete_plan`

Mark the active plan finished after delivering the result. A new request needs a new plan.

| parameter | type | default |
| --- | --- | --- |
| `summary` | string | required |
| `unresolved_issues` | array<string> or null | null |

## Projects & documents

### `create_project` (mutating)

Create a new editable project (document) in the workspace. background: '#rrggbb' fill layer,
or 'transparent'/null for none. Returns document_id and the project folder.

| parameter | type | default |
| --- | --- | --- |
| `name` | string | required |
| `width` | integer | required |
| `height` | integer | required |
| `background` | string or null | "#ffffff" |
| `resolution_dpi` | number | 72.0 |

### `open_document` (mutating)

Open an image (PNG/JPEG/WebP/TIFF/BMP/GIF) as a new project with a LOCKED 'Original' layer,
a layered file (.ora always; .xcf/.psd via GIMP 3), or an existing project folder to continue editing.

| parameter | type | default |
| --- | --- | --- |
| `path` | string | required |
| `name` | string or null | null |

### `list_projects`

List projects in the workspace with their document ids.

### `get_document_info`

Canvas size, color mode, revision, layer tree (top to bottom), checkpoints, assets and metadata.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |

### `get_project_manifest`

Paths of the project, exports, previews, research records, plans and assets with licenses.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |

### `get_history`

Recent operations with parameters, affected layers, backend and warnings.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `limit` | integer | 30 |

### `save_document`

Save the project. format: project (always saved anyway) | ora (OpenRaster, always available) |
xcf (native GIMP file, needs GIMP 3) | psd (needs local Photoshop). path is relative to the project
folder unless absolute inside an allowed output directory.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `format` | string | "project" |
| `path` | string or null | null |

### `create_checkpoint`

Pin the current state under a name so it can be restored later (cheap: no pixels are copied).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `name` | string | required |
| `note` | string or null | null |

### `list_checkpoints`

List named checkpoints.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |

### `restore_checkpoint` (mutating)

Restore a checkpoint (by id or name). Recorded as a new revision, so it can itself be undone.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `checkpoint` | string | required |

### `undo` (mutating)

Return to the state from `steps` operations ago (recorded as a new revision).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `steps` | integer | 1 |

### `crop_image` (mutating)

Crop the canvas to a rectangle. Non-destructive: layer pixels outside the canvas are kept.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `x` | integer | required |
| `y` | integer | required |
| `width` | integer | required |
| `height` | integer | required |

### `resize_image` (mutating)

Scale the whole document (all layers and masks). Give width and/or height (aspect kept if one is
omitted) or scale. interpolation: nearest | linear | cubic | lanczos | area.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `width` | integer or null | null |
| `height` | integer or null | null |
| `scale` | number or null | null |
| `interpolation` | string | "lanczos" |

### `resize_canvas` (mutating)

Change canvas size without scaling content. anchor: center, top_left, top, top_right, left, right,
bottom_left, bottom, bottom_right.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `width` | integer | required |
| `height` | integer | required |
| `anchor` | string | "center" |

## Layers & transforms

### `align_layers` (mutating)

Align layers' visible content: left | center | right | top | middle | bottom, relative to canvas |
selection | first (the first layer in layer_ids).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_ids` | array<string> | required |
| `alignment` | string | required |
| `relative_to` | string | "canvas" |

### `blend_layers` (mutating)

Set how a layer blends with the layers below; with merge=true also merge it down (destructive).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `top_layer_id` | string | required |
| `blend_mode` | string | "normal" |
| `opacity` | number | 1.0 |
| `merge` | boolean | false |

### `create_group` (mutating)

Create a layer group, optionally moving sibling layers into it (order preserved).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `name` | string | required |
| `layer_ids` | array<string> or null | null |
| `blend_mode` | string | "pass_through" |

### `create_layer` (mutating)

New canvas-sized raster layer, transparent or filled with fill_color. Placed above layer `above`,
at position='bottom', inside group parent_id, or on top by default.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `name` | string | "Layer" |
| `fill_color` | string or null | null |
| `above` | string or null | null |
| `position` | string or null | null |
| `parent_id` | string or null | null |
| `opacity` | number | 1.0 |
| `blend_mode` | string | "normal" |

### `delete_layer` (mutating)

Delete a layer (and a group's children). Recoverable with undo/restore_checkpoint.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `duplicate_layer` (mutating)

Duplicate a layer (or group) directly above itself; the copy is unlocked for editing.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `name` | string or null | null |

### `flatten_image` (mutating)

Flatten everything into one layer. Only when the user explicitly asks; exports never need it.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `background` | string or null | "#ffffff" |

### `flip_layer` (mutating)

Mirror a layer horizontally or vertically about its center.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `direction` | string | "horizontal" |

### `get_layer_info`

Detailed layer info: opaque bounds (local and document), coverage, mean color, text/shape/fill
properties, effects, source asset and license.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `import_image_as_layer` (mutating)

Import a local image file or a fetched research reference (reference_id) as a new layer. The
original is copied to assets/ and recorded with provenance. fit: none | contain | cover | width |
height; scaled imports stay 'smart' (re-rendered from the original on later transforms). References
whose license forbids compositing are refused unless license_acknowledged=true. x/y default to centered.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `path` | string or null | null |
| `reference_id` | string or null | null |
| `name` | string or null | null |
| `x` | integer or null | null |
| `y` | integer or null | null |
| `fit` | string | "none" |
| `scale` | number or null | null |
| `above` | string or null | null |
| `license_acknowledged` | boolean | false |

### `list_layers`

Layer tree top-to-bottom with ids, kinds, bounds, visibility, opacity, blend modes, masks, depth.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |

### `merge_down` (mutating)

Merge a layer into the one below (destructive; prefer keeping layers separate).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `name` | string or null | null |

### `move_layer` (mutating)

Reorder: position = up | down | top | bottom | above | below (needs reference_layer_id) |
into_group (needs group_id) | out_of_group. To change x/y use set_layer_properties or transform_layer.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `position` | string | "up" |
| `reference_layer_id` | string or null | null |
| `group_id` | string or null | null |

### `rasterize_layer` (mutating)

Turn a text/shape/fill/smart layer into plain pixels (needed before pixel retouching).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `rename_layer` (mutating)

Rename a layer. Use meaningful names (e.g. 'Tiger', 'Tiger · contact shadow').

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `name` | string | required |

### `rotate_layer` (mutating)

Rotate a layer by `angle` degrees clockwise about the pivot.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `angle` | number | required |
| `pivot` | string or array<number> | "center" |

### `set_blend_mode` (mutating)

Set a layer's blend mode (see set_layer_properties for the list).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `blend_mode` | string | required |

### `set_layer_opacity` (mutating)

Layer opacity in 0..1.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `opacity` | number | required |

### `set_layer_properties` (mutating)

Set several properties at once. blend_mode: normal multiply screen overlay soft_light hard_light
darken lighten color_dodge color_burn linear_dodge linear_burn difference exclusion subtract divide hue
saturation color luminosity (pass_through for groups). clipped=true clips the layer to the one below.
x/y set the layer's top-left position in document pixels.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `name` | string or null | null |
| `visible` | boolean or null | null |
| `opacity` | number or null | null |
| `blend_mode` | string or null | null |
| `clipped` | boolean or null | null |
| `locked_pixels` | boolean or null | null |
| `x` | integer or null | null |
| `y` | integer or null | null |

### `set_layer_visibility` (mutating)

Show or hide a layer.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `visible` | boolean | required |

### `transform_layer` (mutating)

Move/scale/rotate (degrees, clockwise)/shear/flip about a pivot ('center', 'bottom', 'top_left', ...
or [x, y]), or map the layer onto 4 perspective corners [[TL],[TR],[BR],[BL]] in document pixels.
Works on groups (applied to every child). Re-renders from the original pixels to avoid quality loss.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `translate_x` | number | 0.0 |
| `translate_y` | number | 0.0 |
| `scale_x` | number | 1.0 |
| `scale_y` | number or null | null |
| `rotate` | number | 0.0 |
| `shear_x` | number | 0.0 |
| `shear_y` | number | 0.0 |
| `flip_horizontal` | boolean | false |
| `flip_vertical` | boolean | false |
| `pivot` | string or array<number> | "center" |
| `perspective` | array<array<number>> or null | null |
| `interpolation` | string | "cubic" |

## Selections & masks

### `create_selection` (mutating)

Create/combine the document selection. shape: all | none | rectangle | ellipse | polygon (points).
mode: replace | add | subtract | intersect. feather in px. Selections drive masks, local adjustments,
remove_object and fills.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `shape` | string | "rectangle" |
| `x` | number | 0 |
| `y` | number | 0 |
| `width` | number | 0 |
| `height` | number | 0 |
| `points` | array<array<number>> or null | null |
| `mode` | string | "replace" |
| `feather` | number | 0.0 |

### `select_by_color` (mutating)

Select pixels of a layer near a color (or the color under `point`). contiguous=true acts like a
magic wand from `point`. tolerance is RGB distance 0..441 (32 is moderate).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `color` | string or null | null |
| `point` | array<number> or null | null |
| `tolerance` | number | 32.0 |
| `contiguous` | boolean | false |
| `mode` | string | "replace" |
| `feather` | number | 0.0 |

### `select_layer_alpha` (mutating)

Select the visible pixels of a layer (alpha times mask).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `mode` | string | "replace" |

### `modify_selection` (mutating)

invert | grow (px) | shrink (px) | feather (px) | border (px) | clear.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `operation` | string | required |
| `amount` | number | 0.0 |

### `create_layer_mask` (mutating)

Add a non-destructive mask (white = visible). source: white | black | selection | alpha | luminance |
layer_luminance (of source_layer_id) | linear_gradient (white at start -> black at end) |
radial_gradient (white center). Works on pixel layers, groups and adjustment layers.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `source` | string | "white" |
| `start` | array<number> or null | null |
| `end` | array<number> or null | null |
| `center` | array<number> or null | null |
| `radius` | number or null | null |
| `source_layer_id` | string or null | null |
| `invert` | boolean | false |
| `replace` | boolean | false |

### `edit_layer_mask` (mutating)

Edit a mask: paint (strokes; value 1 reveals, 0 hides; soft brush) | fill_selection | fill_all |
gradient (linear start/end or radial center/radius; combine multiply|replace|max|min) | grow | shrink
(amount px) | blur (amount px) | contrast (amount 0..1, hardens soft edges) | threshold (amount 0..1).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `operation` | string | required |
| `value` | number | 1.0 |
| `strokes` | array<array<array<number>>> or null | null |
| `brush_size` | number | 40.0 |
| `hardness` | number | 0.5 |
| `amount` | number | 0.0 |
| `start` | array<number> or null | null |
| `end` | array<number> or null | null |
| `center` | array<number> or null | null |
| `radius` | number or null | null |
| `combine` | string | "multiply" |

### `invert_mask` (mutating)

Invert a layer mask (hidden areas become visible and vice versa).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `feather_mask` (mutating)

Soften mask edges by `radius` px (1-3 px for cut-outs; larger for blends).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `radius` | number | required |

### `set_mask_enabled` (mutating)

Temporarily disable a mask (to compare) or re-enable it.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `enabled` | boolean | required |

### `apply_mask` (mutating)

Bake the mask into the layer's alpha (destructive; usually unnecessary).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `delete_mask` (mutating)

Remove a layer mask without applying it.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

## Retouching, filters & color

### `apply_filter` (mutating)

Apply a filter to a layer (target='pixels') or to its mask (target='mask'), optionally only inside the selection. Built-in filters: gaussian_blur(radius), box_blur(radius), motion_blur(distance, angle), lens_blur(radius, highlight_boost), unsharp_mask(radius, amount, threshold), high_pass(radius), add_noise(amount, monochrome, seed, grain_size), denoise(strength), median(radius), emboss(strength, angle), edge_detect(low, high), vignette(amount, radius, softness), pixelate(cell), chromatic_aberration(shift), gradient_blur(radius, focus_y, focus_band, falloff, angle), bloom(threshold, radius, intensity), ripple(amplitude, wavelength, phase, direction). With backend='gimp' any available GEGL operation can be used, e.g. filter='gegl:noise-reduction' params={'iterations': 3} (GEGL property names; see get_capabilities(include_gimp_filters=true) and describe_gimp_filter).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `filter` | string | required |
| `params` | object or null | null |
| `backend` | string | "auto" |
| `use_selection` | boolean | false |
| `target` | string | "pixels" |

### `describe_gimp_filter`

List the properties (name, type, range, default) of a GEGL operation in the installed GIMP 3.

| parameter | type | default |
| --- | --- | --- |
| `operation` | string | required |

### `adjust_colors` (mutating)

Color/tone adjustment. Prefer as_adjustment_layer=true (non-destructive, editable later, clipped to layer_id unless clipped=false; omit layer_id for a global grade on top). Otherwise edits layer_id's pixels. Adjustments and parameters: brightness_contrast(brightness, contrast), levels(in_black, in_white, gamma, out_black, out_white, channel), curves(points, red, green, blue), hue_saturation(hue, saturation, lightness, colorize), color_balance(shadows, midtones, highlights, preserve_luminosity), exposure(ev, offset, gamma), vibrance(amount), temperature_tint(temperature, tint), photo_filter(color, density, preserve_luminosity), channel_mixer(red, green, blue, monochrome), black_white(red, green, blue, tint, tint_strength), invert(), posterize(levels_count), threshold(level), color_transfer(src_mean, src_std, dst_mean, dst_std, strength, preserve_luminance). Ranges: brightness/contrast/saturation/lightness/vibrance/temperature/tint -1..1, hue -180..180 deg, exposure ev -10..10, levels/curves values 0..255, color_balance triplets [cyan-red, magenta-green, yellow-blue] in -1..1.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string or null | required |
| `adjustment` | string | required |
| `params` | object or null | null |
| `use_selection` | boolean | false |
| `as_adjustment_layer` | boolean | false |
| `clipped` | boolean | true |
| `name` | string or null | null |

### `adjust_curves` (mutating)

Tone curves with [input, output] control points in 0..255 (monotone cubic). E.g. gentle S-curve:
points=[[0,0],[64,54],[192,205],[255,255]]. Per-channel curves for color grading.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string or null | required |
| `points` | array<array<number>> or null | null |
| `red` | array<array<number>> or null | null |
| `green` | array<array<number>> or null | null |
| `blue` | array<array<number>> or null | null |
| `as_adjustment_layer` | boolean | true |

### `update_adjustment_layer` (mutating)

Change parameters of an existing adjustment layer (merged with its current params).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `params` | object | required |

### `match_color` (mutating)

Match a composited layer's color statistics (Lab mean/std) to the scene: reference = below (the
composite around the layer) | region (with region) | another layer id. Creates a clipped adjustment
layer by default.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `reference` | string | "below" |
| `region` | array<number> or null | null |
| `strength` | number | 0.7 |
| `preserve_luminance` | boolean | false |
| `as_adjustment_layer` | boolean | true |

### `blur_layer` (mutating)

Blur: gaussian | box | motion (angle in degrees) | lens (bokeh disk). For depth of field use
apply_filter('gradient_blur') or blur background layers more than foreground ones.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `radius` | number | 4.0 |
| `method` | string | "gaussian" |
| `angle` | number | 0.0 |
| `use_selection` | boolean | false |

### `sharpen_layer` (mutating)

Unsharp-mask sharpening (amount 0..5, radius px, threshold 0..255).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `amount` | number | 0.8 |
| `radius` | number | 1.5 |
| `threshold` | number | 2.0 |
| `use_selection` | boolean | false |

### `clone_stamp` (mutating)

Clone stamp: paints pixels sampled at an offset. source_point corresponds to the FIRST point of the
first stroke; aligned=true keeps that offset for all strokes, false restarts at source_point for each
stroke. sample = layer | merged (all visible layers) | <layer_id>. Use for retouching and extending
existing texture, NOT for inventing new objects. backend='gimp' uses GIMP's native clone tool.
Vary the source between strokes and keep opacity < 1 for organic texture to avoid visible repeats.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `source_point` | array<number> | required |
| `strokes` | array<array<array<number>>> | required |
| `brush_size` | number | 30.0 |
| `hardness` | number | 0.6 |
| `opacity` | number | 1.0 |
| `aligned` | boolean | true |
| `sample` | string | "layer" |
| `backend` | string | "auto" |
| `use_selection` | boolean | false |

### `heal_region` (mutating)

Healing brush. With source_point: copies texture from the source and adapts its color/light to the
destination (Poisson blending; GIMP heal with backend='gimp'). Without source_point: spot healing that
reconstructs the stroked area from its surroundings.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `strokes` | array<array<array<number>>> | required |
| `source_point` | array<number> or null | null |
| `brush_size` | number | 30.0 |
| `hardness` | number | 0.5 |
| `backend` | string | "auto" |

### `remove_object` (mutating)

Remove an object by inpainting the region (selection | rect | polygon) from its surroundings
(method telea | navier_stokes). Good for small/medium objects; inspect the result and refine large or
structured areas with clone_stamp / heal_region.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `region` | string | "selection" |
| `rect` | array<number> or null | null |
| `polygon` | array<array<number>> or null | null |
| `method` | string | "telea" |
| `dilate` | integer | 4 |

### `remove_background` (mutating)

Hide the background with a LAYER MASK (pixels untouched). method: grabcut (rect around the subject,
optional foreground/background seed points; good default) | color_key (solid backdrops: color,
tolerance) | rembg (if installed). Inspect the mask edge afterwards and refine with edit_layer_mask.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `method` | string | "grabcut" |
| `rect` | array<number> or null | null |
| `foreground_points` | array<array<number>> or null | null |
| `background_points` | array<array<number>> or null | null |
| `color` | string or null | null |
| `tolerance` | number | 40.0 |
| `edge_feather` | number | 1.0 |

## Content & compositing

### `create_text_layer` (mutating)

Editable text layer; x, y = top-left. font is a family/style name ('DejaVu Sans Bold') or a .ttf
path. max_width wraps lines. Edit later with update_text_layer.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `text` | string | required |
| `x` | integer | 0 |
| `y` | integer | 0 |
| `font` | string | "DejaVu Sans" |
| `size` | number | 48.0 |
| `color` | string | "#ffffff" |
| `align` | string | "left" |
| `max_width` | integer or null | null |
| `line_spacing` | number | 1.2 |
| `stroke_width` | integer | 0 |
| `stroke_color` | string | "#000000" |
| `name` | string or null | null |

### `update_text_layer` (mutating)

Change text-layer properties; the layer is re-rendered (and keeps its transform).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `text` | string or null | null |
| `font` | string or null | null |
| `size` | number or null | null |
| `color` | string or null | null |
| `align` | string or null | null |
| `max_width` | integer or null | null |
| `line_spacing` | number or null | null |
| `stroke_width` | integer or null | null |
| `stroke_color` | string or null | null |

### `create_shape_layer` (mutating)

Anti-aliased shape layer: rectangle | rounded_rectangle | ellipse | polygon | line (points in
document coords). fill/stroke colors may include alpha ('#rrggbbaa').

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `shape` | string | "rectangle" |
| `x` | number | 0 |
| `y` | number | 0 |
| `width` | number | 100 |
| `height` | number | 100 |
| `points` | array<array<number>> or null | null |
| `fill` | string or null | "#ffffff" |
| `stroke` | string or null | null |
| `stroke_width` | number | 0.0 |
| `corner_radius` | number | 0.0 |
| `name` | string or null | null |

### `create_fill_layer` (mutating)

Canvas-sized fill: solid | linear_gradient (angle deg, 90 = top->bottom) | radial_gradient (center
normalized [x,y], radius fraction). stops: [[0.0, '#hex'], [1.0, '#hex']]. position='bottom' puts it
under everything (backgrounds, skies).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `type` | string | "solid" |
| `color` | string | "#808080" |
| `stops` | array<array<any>> or null | null |
| `angle` | number | 90.0 |
| `center` | array<number> or null | null |
| `radius` | number | 0.75 |
| `name` | string or null | null |
| `opacity` | number | 1.0 |
| `blend_mode` | string | "normal" |
| `position` | string or null | null |

### `create_procedural_layer` (mutating)

Seeded procedural texture layer, kinds: clouds, fog, grain, bokeh, sky, water. Params: clouds(scale, octaves, color_dark, color_light, seed), fog(density, scale, color, vertical_falloff bottom|top|none, seed), grain(amount, seed; use blend_mode overlay/soft_light at low opacity), bokeh(count, min_radius, max_radius, color, softness, seed), sky(top, horizon, horizon_position), water(deep, shallow, scale, seed).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `kind` | string | required |
| `params` | object or null | null |
| `name` | string or null | null |
| `opacity` | number | 1.0 |
| `blend_mode` | string | "normal" |

### `add_layer_effect` (mutating)

Non-destructive layer style rendered at composite time. Effects and defaults: drop_shadow: {'color': '#000000', 'opacity': 0.55, 'direction_deg': 45.0, 'distance': 12.0, 'size': 14.0, 'spread': 0.0, 'blend_mode': 'multiply'}; outer_glow: {'color': '#fff3c4', 'opacity': 0.6, 'size': 18.0, 'spread': 0.1, 'blend_mode': 'screen'}; stroke: {'color': '#000000', 'opacity': 1.0, 'width': 3.0, 'blend_mode': 'normal'}. direction_deg is where the shadow falls (0 right, 90 down).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `effect` | string | required |
| `params` | object or null | null |

### `add_drop_shadow` (mutating)

Drop shadow layer style (graphic design). For subjects standing in a scene use add_cast_shadow and
add_contact_shadow instead, which follow the scene's light and ground plane.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `direction_deg` | number | 45.0 |
| `distance` | number | 12.0 |
| `size` | number | 14.0 |
| `opacity` | number | 0.55 |
| `color` | string | "#000000" |
| `spread` | number | 0.0 |

### `remove_layer_effect` (mutating)

Remove a layer style by its effect id.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `effect_id` | string | required |

### `add_cast_shadow` (mutating)

Project the subject's silhouette onto a flat ground as a separate multiply layer below it. The
penumbra softens and fades with distance from the contact point. light_azimuth = where the light
comes FROM (0 right, 90 front/camera, 180 left, 270 behind; 225 = upper-left behind). Low
light_elevation = long shadows. ground_y = document y of the contact line.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `light_azimuth` | number | 225.0 |
| `light_elevation` | number | 35.0 |
| `ground_y` | number or null | null |
| `softness` | number | 0.5 |
| `opacity` | number | 0.55 |
| `color` | string | "#000000" |

### `add_contact_shadow` (mutating)

Dark occlusion where the subject touches the ground (feet, paws, base). Essential for grounding.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `ground_y` | number or null | null |
| `blur` | number | 6.0 |
| `spread` | number | 0.12 |
| `opacity` | number | 0.75 |

### `create_reflection` (mutating)

Water/gloss reflection mirrored about the waterline axis_y (document y; default: subject bottom), with
Fresnel darkening, water tint, wave distortion (ripple_*), vertical blur and distance fade. For calm
water use small ripples; for choppy water larger amplitude and shorter fade.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |
| `axis_y` | number or null | null |
| `opacity` | number | 0.6 |
| `fade` | number | 0.7 |
| `blur` | number | 2.0 |
| `ripple_amplitude` | number | 3.0 |
| `ripple_wavelength` | number | 18.0 |
| `squash` | number | 1.0 |
| `tint` | string or null | "#1d4e6b" |
| `tint_strength` | number | 0.25 |
| `darken` | number | 0.15 |
| `seed` | integer | 0 |

### `add_lighting_effect` (mutating)

Light on its own layer: point (glow at normalized x,y; screen) | directional (wash from angle;
soft_light) | god_rays (crepuscular rays from x,y through bright gaps, e.g. sun through trees) | rim
(edge light on layer_id from light_azimuth, clipped). Adjust intensity/opacity to taste.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `kind` | string | "point" |
| `x` | number | 0.5 |
| `y` | number | 0.2 |
| `color` | string | "#ffd9a0" |
| `intensity` | number | 0.6 |
| `radius` | number | 0.5 |
| `angle` | number | 45.0 |
| `softness` | number | 0.6 |
| `blend_mode` | string or null | null |
| `layer_id` | string or null | null |
| `light_azimuth` | number | 225.0 |
| `width` | number | 4.0 |
| `rays_length` | number | 0.35 |
| `threshold` | number | 0.65 |

### `generate_image_layer` (mutating)

Generate pixels with an OPTIONAL local generative provider (ComfyUI) into a new layer with full
provenance (model, seed). Fails with a clear message if no provider is configured; then fall back to
compositing licensed assets and procedural layers, and tell the user about the limitation.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `prompt` | string | required |
| `negative_prompt` | string | "" |
| `width` | integer or null | null |
| `height` | integer or null | null |
| `seed` | integer or null | null |
| `provider` | string | "comfyui" |
| `steps` | integer | 25 |
| `cfg` | number | 6.5 |
| `name` | string or null | null |
| `x` | integer | 0 |
| `y` | integer | 0 |
| `mask_from_selection` | boolean | false |

## Preview, inspection & output

### `render_preview`

Render the current composite (or one layer solo, or a region at full resolution for 100% crops)
to previews/. Then LOOK at it with view_image (or by opening the file) and inspect for defects.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `max_size` | integer | 1024 |
| `layer_id` | string or null | null |
| `region` | array<number> or null | null |
| `background` | string | "checkerboard" |
| `hide_layers` | array<string> or null | null |

### `view_image`

Return an image file (preview, export, reference, contact sheet) as image content so you can see
it. Downscaled to max_size. Use after every render_preview.

| parameter | type | default |
| --- | --- | --- |
| `path` | string | required |
| `max_size` | integer | 1024 |

### `inspect_image`

Objective measurements of the current composite (or an image file): tonal range, clipping,
contrast, saturation, color cast, sharpness, noise, dominant palette, global light gradient, and
heuristic defect flags (clipping, flatness, casts, repeated clone patches). Complements - never
replaces - looking at the preview yourself.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string or null | null |
| `path` | string or null | null |
| `region` | array<number> or null | null |

### `compare_images`

Compare two images: two files, or two revisions of a document (revision_b defaults to current).
Returns SSIM, mean difference, changed fraction/bounds and a difference heatmap path.

| parameter | type | default |
| --- | --- | --- |
| `path_a` | string or null | null |
| `path_b` | string or null | null |
| `document_id` | string or null | null |
| `revision_a` | integer or null | null |
| `revision_b` | integer or null | null |

### `analyze_layer_integration`

Check how well a composited subject layer fits its surroundings: brightness, color temperature,
contrast, sharpness and grain vs. the backdrop around it, plus hard edges and halos. Returns concrete
findings with suggested fixes.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `layer_id` | string | required |

### `export_image`

Export a flattened copy (the project stays layered): png | jpeg | webp | tiff. Optional resize.
JPEG gets a white background unless `background` is given. Verifies the written file (opens it,
checks format and size) and writes a .credits.json sidecar with sources and licenses.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `path` | string or null | null |
| `format` | string | "png" |
| `quality` | integer | 92 |
| `width` | integer or null | null |
| `height` | integer or null | null |
| `background` | string or null | null |

### `export_png`

Export PNG (keeps transparency) with verification and credits sidecar.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `path` | string or null | null |
| `width` | integer or null | null |
| `height` | integer or null | null |

### `export_jpeg`

Export JPEG (quality 1..100) with verification and credits sidecar.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `path` | string or null | null |
| `quality` | integer | 92 |
| `width` | integer or null | null |
| `height` | integer or null | null |

### `export_webp`

Export WebP with verification and credits sidecar.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `path` | string or null | null |
| `quality` | integer | 90 |
| `width` | integer or null | null |
| `height` | integer or null | null |

## Research & knowledge

### `search_knowledge`

Search the persistent, version-controlled visual knowledge base (subjects, environments, materials,
lighting, techniques) BEFORE doing new research. Reuse what is relevant; research what is missing.

| parameter | type | default |
| --- | --- | --- |
| `query` | string | required |
| `limit` | integer | 8 |
| `category` | string or null | null |

### `read_knowledge`

Read a knowledge entry by path (e.g. 'subjects/animals/tiger'): front matter, sections, sources.

| parameter | type | default |
| --- | --- | --- |
| `path` | string | required |

### `save_knowledge`

Create or extend a knowledge entry with GENUINELY REUSABLE lessons (not task noise). sections maps
headings ('Visual observations', 'Editing recipe', 'Failure modes', 'Parameters', 'Limitations',
'Examples') to concise markdown in your own words. sources: [{url, title, license, supports: [...]}].
Unsupported claims must use confidence 'low'. Never paste copyrighted articles or embed images.
The entry is a file in the repository - remind the user to commit it.

| parameter | type | default |
| --- | --- | --- |
| `path` | string | required |
| `sections` | object | required |
| `title` | string or null | null |
| `category` | string or null | null |
| `tags` | array<string> or null | null |
| `aliases` | array<string> or null | null |
| `confidence` | string or null | null |
| `sources` | array<object> or null | null |
| `related` | array<string> or null | null |
| `mode` | string | "append" |

### `search_references`

Search free reference-image providers (wikimedia_commons, openverse, local folders) with license
metadata and a reuse assessment for each hit. Use several specific queries per aspect (anatomy,
texture, lighting, environment interaction). Results are candidates: fetch and LOOK at them.

| parameter | type | default |
| --- | --- | --- |
| `query` | string | required |
| `providers` | array<string> or null | null |
| `limit` | integer | 8 |
| `reusable_only` | boolean | false |
| `commercial` | boolean | false |

### `get_reference_metadata`

Full metadata (source page, author, license, description) for a search hit ('provider:id').

| parameter | type | default |
| --- | --- | --- |
| `reference_key` | string | required |

### `fetch_reference`

Download a reference into the project's references/ with a provenance record. purpose='study'
(size='thumbnail'; for learning visual characteristics) or 'composite' (size='large' ~2048 px, or
'full' original; only if the license allows modification - the image becomes part of the artwork
and needs attribution).

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `reference_key` | string | required |
| `size` | string | "thumbnail" |
| `purpose` | string | "study" |

### `analyze_visual_references`

Measure fetched references (palette, tonal range, warmth, sharpness, light gradient) and build a
contact sheet image. View the contact sheet, then record_observation for each useful finding.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `reference_ids` | array<string> | required |

### `record_observation`

Record what you learned from references (aspect e.g. 'anatomy', 'stripe pattern', 'light through
canopy'), citing the reference ids that support it. Observations without references are marked
unsupported. Note uncertainty or conflicting evidence explicitly.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |
| `aspect` | string | required |
| `observation` | string | required |
| `reference_ids` | array<string> | required |
| `confidence` | string | "medium" |
| `subject` | string or null | null |

### `get_research_summary`

All references (with licenses/roles) and observations for this project, grouped by aspect.

| parameter | type | default |
| --- | --- | --- |
| `document_id` | string | required |

