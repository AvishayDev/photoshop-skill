# Research protocol

Research is part of the work, not decoration. Adapt the aspects to the request.

1. **Knowledge first.** `search_knowledge` for each subject/environment/material/light/technique and
   read relevant entries. Note what is missing or low-confidence.
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
7. **Summarize**: `get_research_summary` and cite it in the visual specification.

If research tools or network are unavailable, say so, rely on the knowledge base, and lower confidence.
