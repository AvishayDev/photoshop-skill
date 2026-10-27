---
title: Peacock (Indian peafowl, male)
category: subjects/birds
tags:
- peacock
- peafowl
- bird
- feathers
- iridescence
- train
- eyespot
aliases:
- Pavo cristatus
- peafowl
- peahen
confidence: medium
reviewed: '2026-10-27'
sources:
- url: https://en.wikipedia.org/wiki/Indian_peafowl
  title: Indian peafowl (Wikipedia), section Description
  license: CC BY-SA 4.0
  supports:
  - size
  - train
  - eyespot structure
  - crest
  - neck colour
  - structural colour
  - posture
  - legs
- url: https://commons.wikimedia.org/wiki/File:Peacock_standing_locking_stunning.jpg
  title: Male peacock without train
  license: CC BY-SA 4.0
  supports:
  - male without train
related:
- materials/feathers
- environments/ocean
- lighting/water-reflections
---

## Visual observations

- **Size and silhouette:** body about 1.0-1.2 m bill to tail; with a full train ~2.0-2.3 m. Small head,
  long slender neck, compact body, long legs; the train (elongated upper tail coverts, not the tail
  itself) trails on the ground when closed and rises into an arched fan in display.
- **Eyespots (ocelli):** purplish-black heart-shaped centre, a blue ring, a copper/bronze rim, then
  alternating green and bronze bands. Some outer train feathers have no eyespot and end in a dark
  crescent-like tip. Eyespot size decreases toward the base of the train.
- **Head:** metallic blue crown; fan-shaped crest of bare black shafts tipped with small blue-green
  "flags"; white bare-skin stripe above the eye and white crescent below it.
- **Neck/body:** saturated metallic blue neck and breast with a scaly texture; green, bronze-scaled
  back; chestnut primaries visible when the wings are spread; brown legs with a spur.
- **Colour mechanism:** train colours are **structural** (microstructure interference), not pigment,
  so hue shifts with viewing and light angle: greens turn bronze/gold, blues turn violet. In shadow,
  the iridescence collapses to dark brown/olive.
- **Female (peahen):** smaller, brown with pale mottling, metallic green lower neck, no train.
- Not every male carries a full train: a male photographed without one (moulted after breeding or immature - the photo alone cannot tell) shows chestnut primaries and a short brown tail. Check which state the request implies.

## Editing recipe

1. Separate subject into layers if possible: body, train, legs - the train needs its own lighting.
2. Iridescence: duplicate the train layer, shift hue (+15-30 deg) on the copy, and reveal it through
   a mask on the areas facing the light (`create_layer_mask` linear_gradient from the light side).
3. In an ocean scene the bird stands in shallow water: legs disappear into the surface; add a
   waterline mask on the legs, ripple rings around them, and a broken reflection
   (`create_reflection`, ripple_amplitude 3-6).
4. A trailing train in water would get wet and dark; a raised display train stays dry and bright.
   Decide which, and keep it physically consistent.

## Failure modes

- Flat, uniformly saturated train with no angle-dependent colour shift.
- Eyespots evenly sized/spaced like a pattern fill (real eyespots overlap and shrink toward the body).
- Calling the train the "tail" and placing it under the wings incorrectly.
- Reflection that is a perfect mirror on choppy ocean water.
- GrabCut confuses the green train with green grass/foliage; add background seed points along the train's lower edge and paint/polygon-mask leftovers, then check the cut-out on magenta.

## Limitations

- Eyespot counts vary between birds; the cited source gives no exact count.
- Painting a convincing peacock from scratch is beyond compositing tools; use a licensed photo or a
  local generative model, then integrate.
