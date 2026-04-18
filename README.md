# OpenClaw Skills Catalog

Weekly-refreshed dataset classifying every skill in the [openclaw/skills](https://github.com/openclaw/skills) catalog by Linux compatibility, ClawHub registry metadata, and last-commit activity.

**Browse the data** → [vesselofone.com/skills/openclaw](https://vesselofone.com/skills/openclaw)
**Read the analysis** → [vesselofone.com/blog/openclaw-skills-1000-tested](https://vesselofone.com/blog/openclaw-skills-1000-tested)

## What's in this repo

| Path | Purpose |
|---|---|
| `data/latest.csv` | Most recent snapshot. Overwritten every Monday. |
| `data/skills-YYYY-MM-DD.csv` | Dated snapshots. Append-only. |
| `reports/report-YYYY-MM-DD.txt` | Human-readable funnel summary for each snapshot. |
| `scripts/catalog-coverage.py` | The scan script. Authoritative copy lives in the [Vessel repo](https://github.com/vesselofone/vessel); this is a mirror. |
| `scripts/sidecar/bin-name-map.json` | Static install map used to classify binary dependencies. Mirror of the vessel copy. |
| `SCHEMA.md` | Every CSV column: type, nullable, enum values. |
| `METHODOLOGY.md` | Sampling, dep resolution, coverage classification, caching. |
| `LIMITATIONS.md` | What this dataset does not tell you. Read before citing. |
| `CITATION.cff` | Academic citation format. |
| `CHANGELOG.md` | Schema and release history. |

## Licensing

- **Data** (`data/`, `reports/`) — [CC BY 4.0](./LICENSE-DATA). Use, remix, build on — attribute.
- **Code** (`scripts/`) — [MIT](./LICENSE-CODE).

## How to cite

**Plain text:**

> Bhardwaj, M. (2026). *OpenClaw Skills Catalog: Linux Compatibility and Registry Metadata* [Dataset]. Vessel. https://github.com/vesselofone/openclaw-skills

**BibTeX:**

```bibtex
@dataset{vessel_openclaw_skills_2026,
  author    = {Bhardwaj, Mehul},
  title     = {OpenClaw Skills Catalog: Linux Compatibility and Registry Metadata},
  year      = {2026},
  publisher = {Vessel},
  url       = {https://github.com/vesselofone/openclaw-skills},
  license   = {CC-BY-4.0}
}
```

The `CITATION.cff` file in this repo is machine-readable via [cffconvert](https://github.com/citation-file-format/cffconvert) and recognized by GitHub's "Cite this repository" sidebar.

## How to reproduce

```bash
git clone https://github.com/vesselofone/openclaw-skills.git
cd openclaw-skills
pip install -r requirements.txt

export GITHUB_TOKEN=ghp_your_public_read_token
python3 scripts/catalog-coverage.py --all --with-metadata --with-commits \
  --output coverage-output --work-dir coverage-output/repos

diff coverage-output/skills-$(date -u +%Y-%m-%d).csv data/latest.csv
```

`downloads`, `installs`, and `stars` will drift from the published snapshot (these update continuously on ClawHub). Everything else should match within ± 1% row count, barring skills added or removed between the dataset's last refresh and your run.

A public-read `GITHUB_TOKEN` is required — unauthenticated requests are throttled. The scan uses ~200 calls.

## Refresh cadence

The dataset is refreshed every Monday 07:00 UTC by the GitHub Actions workflow in `.github/workflows/refresh.yml`. The workflow clones `openclaw/skills`, runs the scan, and commits the new CSV + dated snapshot + report to `main`. Re-runs at the same `openclaw/skills` HEAD reproduce byte-identical except for ClawHub counters.

To trigger a refresh manually: `gh workflow run refresh.yml` on this repo (requires push access).

## Known limitations

Static analysis only. Skill runs are not executed. SKILL.md completeness is voluntary. Moderation status reflects ClawHub staff flags only — it is not a security audit. Full list in [LIMITATIONS.md](./LIMITATIONS.md).

## Contributing

- **Row looks wrong?** Open an issue with the slug and the correction. Rows are edited in the next weekly snapshot, not retroactively.
- **Scan logic disagreement?** Open a PR in the [Vessel repo](https://github.com/vesselofone/vessel) against `packages/infra/scripts/catalog-coverage.py`. Changes propagate here via mirror.
- **New columns requested?** File an issue. Schema additions are append-only; renames and reorders force a major version bump.

## Contact

- Dataset questions: issues on this repo.
- Commercial use, custom cuts: mehul@vesselofone.com
