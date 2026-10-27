# Asset storage policy

- **Never commit** working projects (`projects/*` is git-ignored), downloaded references,
  caches (`.image_studio_cache/`), credentials or `.env` files.
- **Knowledge base**: text only. Link to sources; do not store third-party images, even thumbnails,
  unless their license explicitly permits redistribution and they are genuinely needed.
- **Examples**: scripts that rebuild results from licensed sources rather than committed outputs.
- **No images at all** are committed: `.gitignore` excludes common image and layered formats
  (png, jpg, webp, tiff, xcf, ora, psd, ...). Force-adding one should be a deliberate, reviewed exception.
- **Large binaries** you deliberately want under version control (e.g. a showcase `.xcf`, sample
  plates you own): use Git LFS:
  ```bash
  git lfs install
  git lfs track "*.xcf" "*.ora" "*.psd" "showcase/**/*.png"
  ```
- Tests generate their fixtures in code; recorded API responses are small JSON files.
- Imported assets inside a project keep their original bytes and provenance (`assets/`,
  `references/*.json`); exports write `.credits.json`.
