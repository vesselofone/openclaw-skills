# Changelog

All notable changes to the OpenClaw Skills Catalog dataset.

Schema follows append-only evolution: new columns are added at the end; existing columns are never renamed, reordered, or removed without a major version bump.

## 2026-04-19 — v1.0.0 (initial release)

- First public release.
- Full-catalog scan of `openclaw/skills` (~7,000 skills).
- Schema v1.0.0: 11 base columns + 12 extended columns (see `SCHEMA.md`).
- Dataset licensed CC BY 4.0; scripts licensed MIT.
- Weekly Monday 07:00 UTC refresh via GitHub Actions.
