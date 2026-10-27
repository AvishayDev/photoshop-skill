# Visual research

Research is a first-class step: before creating or substantially editing an image that depends on
real-world appearance, the agent consults the knowledge base, then studies multiple references.

## Providers

| Provider | API | Key needed | Notes |
| --- | --- | --- | --- |
| `wikimedia_commons` | MediaWiki Action API (`commons.wikimedia.org/w/api.php`, `generator=search` in the File namespace, `prop=imageinfo` + `extmetadata`) | no | Structured license, author, credit and attribution-required fields. Follows the Wikimedia User-Agent policy and API etiquette (descriptive UA with contact URL, serial requests, `maxlag`, backoff on 429/503). Wikimedia throttles bulk/bot downloads; prefer `size='large'` renditions over full originals. |
| `openverse` | `api.openverse.org/v1/images/` | no (optional token via `IMAGE_STUDIO_OPENVERSE_TOKEN`) | Aggregates openly licensed images from Flickr, museums and more; anonymous access has lower rate limits. |
| `local` | filesystem | no | Folders in `IMAGE_STUDIO_REFERENCE_DIRS`; user-owned material. |

No provider is scraped; both web providers are official, documented APIs. Results are cached for 24 h
in `.image_studio_cache/` (git-ignored). Network failures and rate limits are reported per provider
without hiding results from the others.

Add a provider: implement `research.providers.base.ReferenceProvider` (`search`, `get`) returning
`ReferenceCandidate` objects with `LicenseInfo`, and register it in `ResearchService`.

## Workflow (tools)

1. `search_knowledge` -> `read_knowledge`
2. `search_references(query, reusable_only=..., commercial=...)` - several specific queries per aspect
3. `fetch_reference(document_id, reference_key)` - thumbnail for study (stored in `references/` with a
   JSON provenance record: source page, author, license, reuse assessment, sha256, retrieval time)
4. `analyze_visual_references` - palette, tonal range, warmth, sharpness, light gradient, contact sheet
5. `view_image` - the agent looks at the images (search snippets are not enough)
6. `record_observation(aspect, observation, reference_ids, confidence)` - observations cite evidence;
   uncited ones are stored as *unsupported* with low confidence
7. `get_research_summary` - feeds the visual specification

## Study vs. composite

- **Study** (default): thumbnails used to learn shapes, textures, light. Not part of the output.
- **Composite**: `fetch_reference(..., size='large'|'full', purpose='composite')` is refused unless the
  license permits modification (CC0, public domain, CC BY, CC BY-SA; NC flagged for commercial use;
  ND and unknown licenses refused). `import_image_as_layer(reference_id=...)` re-checks the license,
  records provenance on the asset, and warns about attribution/ShareAlike. Exports write a
  `.credits.json` sidecar and (PNG) embedded credits text.

The license assessment (`research/licensing.py`) is conservative and is **not legal advice**; unknown
or unusual licenses are never treated as reusable. Public accessibility does not imply reuse rights.
