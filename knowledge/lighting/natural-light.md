---
title: Natural light (sun, sky, golden hour, overcast)
category: lighting
tags: [light, sunlight, sunrise, sunset, golden hour, overcast, shadow, colour temperature, ambient]
aliases: [daylight, sunlight]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Golden_hour_(photography)
    title: Golden hour (photography) (Wikipedia)
    license: CC BY-SA 4.0
    supports: [warm low sun, long soft shadows]
  - url: https://en.wikipedia.org/wiki/Color_temperature
    title: Color temperature (Wikipedia)
    license: CC BY-SA 4.0
    supports: [warm vs cool light]
related: [environments/forest, environments/ocean, techniques/color-matching]
---
## Visual observations

- **Two light sources outdoors:** the sun (small, directional, warm at low angles) and the sky (large,
  diffuse, bluish). Lit sides take the sun's colour; shadow sides take the sky's colour -> warm
  highlights with cool shadows at golden hour.
- **Low sun (sunrise/sunset):** long shadows, warm/orange key light, strong rim light on backlit
  subjects, atmospheric haze glowing near the sun.
- **Midday:** short, hard, dark shadows directly below subjects; high contrast; neutral light.
- **Overcast:** very soft or no cast shadows, but strong contact shadows/ambient occlusion where objects
  touch; low contrast; cool neutral colours.
- **Consistency rule:** every element must share the same light direction, hardness and colour.
  Shadow direction is the most visible cue.

## Editing recipe

- Decide the key light direction first and record it (azimuth/elevation) in the visual spec; reuse it
  for `add_cast_shadow`, `add_lighting_effect` rim/directional and highlight placement.
- Golden hour grade: `temperature_tint` +0.2..+0.4, split tone shadows toward teal with
  `color_balance` shadows [-0.1, 0, 0.15], highlights [0.15, 0, -0.1].
- Overcast: skip cast shadows, keep contact shadows; reduce contrast with curves.

## Failure modes

- Shadows pointing in different directions; warm subject in a blue-hour scene; hard shadows under a
  grey sky.
