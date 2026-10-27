# Research protocol

Research is part of the work, not decoration. Adapt the aspects to the request.

1. **Library and knowledge first.** `search_patterns` (figure recipes, textures, palettes, silhouettes,
   scenes, lights) and `search_knowledge` for each subject/environment/material/light/technique; read
   the hits. Note what is missing or low-confidence - only research that.
2. **Decompose into aspects.** Examples for "tiger in a forest at sunrise":
   - Subject: proportions, head/ear/eye shape, stripe layout and variation, fur direction and texture,
     paw placement and posture, silhouette from the chosen camera angle, appearance under low warm
     light, contact and cast shadows.
   - Environment: vegetation layers, bark/leaf/ground textures, light and dark distribution, depth and
     haze, colour variation, light through trees, background blur.
   - Interaction: scale vs. trees and grass, key/ambient/reflected light, occlusion by plants, colour
     spill, matching sharpness/grain/depth of field.
   For "peacock in the ocean": feather structure and iridescence, eyespot structure, wave patterns,
   surface reflections, horizon placement, haze, water translucency, how legs meet water.
3. **Search specifically.** Multiple short queries per aspect ("tiger walking side view", "tiger
   face close up", "forest sunrise light rays", "peacock train eyespot macro"). Prefer
   `reusable_only=true` when you might composite. Use different providers.
4. **Fetch and look.** `fetch_reference` (thumbnails, purpose='study') for 3-8 references covering
   *different* properties; `analyze_visual_references` for objective palette/tone data and a contact
   sheet; `view_image` the contact sheet and individual references.
5. **Record observations** with `record_observation(aspect, observation, reference_ids, confidence)`.
   Mention disagreement between references and uncertainty explicitly. Do not invent details you did
   not see.
6. **Translate into a strategy**: an original composition and concrete edit parameters. References
   teach appearance; they are not the artwork. Only composite assets whose license allows it
   (CC0/PD/CC BY/CC BY-SA; check NC for commercial use) and keep attribution.
7. **Learn patterns (measure, don't guess).** Run `learn_pattern` on the best references: palette,
   marks (stripes/spots/plain, coverage, elongation), dominant period and direction, light direction, and
   with `rect` (+ `fg_points` for shadowed limbs) the silhouette contour. Compare the numbers with what you
   see; discard wrong measurements (e.g. a mask that missed the legs).
8. **Save what is reusable** with `save_pattern`: `texture/<subject>-<pattern>`, `palette/<subject>`,
   `silhouette/<subject>-<pose>`, `figure/<subject>-<pose>` (after you built and checked the recipe),
   `scene/...`, `light/...`. Cite sources (url, title, license) and keep confidence honest.
9. **Facts from the web.** Use web search/fetch for descriptive facts (markings, proportions, behaviour
   in light) and cite the pages in pattern/knowledge sources.
10. **Summarize**: `get_research_summary` and cite it in the visual specification.

If research tools or network are unavailable (providers can rate-limit), say so, rely on the pattern
library and knowledge base, and lower confidence.
