# Changelog

All notable changes to the OpenClaw Skills Catalog dataset and ecosystem research published in this repository.

Schema follows append-only evolution: new columns are added at the end; existing columns are never renamed, reordered, or removed without a major version bump.

## 2026-04-20 — Ecosystem Research v1 (sibling dataset added)

- Published *The State of AI Agent Skills: What Breaks, April 2026* — a 90-day classification of 16,840 public user reports (GitHub, Hacker News, Reddit). 16,635 rows classified by Claude Haiku 4.5 into a 12-type pain taxonomy.
- New location: `reports/state-of-agent-skills-ecosystem-2026-04.md`
- Dataset: `data/ecosystem-research-2026-04/` — `classified-mentions.csv` (16,635 rows, URLs + classifications only, no redistributed body text), `pain-distribution.csv`, `pain-distribution-by-source.csv`
- Headline: on GitHub, 55% of user pain is operational correctness (quality 21%, silent-failure 18%, compat 9%, install 7%). Discovery is 2%.
- Licensed CC BY 4.0. Point-in-time study; refresh cadence TBD based on reader interest.

## 2026-04-19 — v1.0.0 (initial release)

- First public release.
- Full-catalog scan of `openclaw/skills` (~7,000 skills).
- Schema v1.0.0: 11 base columns + 12 extended columns (see `SCHEMA.md`).
- Dataset licensed CC BY 4.0; scripts licensed MIT.
- Weekly Monday 07:00 UTC refresh via GitHub Actions.
