# OpenClaw Skills Catalog + Ecosystem Research

Open research on the AI-agent skill ecosystem. Two complementary public datasets, CC BY 4.0.

**DOI (citable, archived):** [10.5281/zenodo.19691714](https://doi.org/10.5281/zenodo.19691714)  
**Browse the data:** [vesselofone.com/skills/openclaw](https://vesselofone.com/skills/openclaw)  
**Read the analysis:** [vesselofone.com/research/ai-agent-skills-ecosystem](https://vesselofone.com/research/ai-agent-skills-ecosystem)

---

## Datasets

### 1. OpenClaw Skills Catalog

A snapshot of every public skill in the [openclaw/skills](https://github.com/openclaw/skills) catalog, classified by Linux compatibility, ClawHub registry metadata, and last-commit activity. Measures the *registry layer*.

**Use it to:** identify which skills are blocked by missing system binaries, audit dependency surface area, build your own scanner, or reproduce the registry findings in the April 2026 ecosystem study.

| Path | Contents |
|---|---|
| `data/latest.csv` | Most recent snapshot |
| `data/skills-YYYY-MM-DD.csv` | Dated snapshots (append-only) |
| `reports/report-YYYY-MM-DD.txt` | Human-readable funnel summary per snapshot |
| `scripts/catalog-coverage.py` | Scan script (mirror of the authoritative copy in the [Vessel repo](https://github.com/vesselofone/vessel)) |
| `scripts/sidecar/bin-name-map.json` | Static binary install map used for dependency classification |
| `SCHEMA.md` | Every CSV column: type, nullable, enum values |
| `METHODOLOGY.md` | Sampling, dependency resolution, coverage classification, caching |
| `LIMITATIONS.md` | What this dataset does not tell you — read before citing |
| `CITATION.cff` | Machine-readable citation (recognized by GitHub's "Cite this repository" sidebar) |
| `CHANGELOG.md` | Schema and release history |

### 2. Ecosystem Research 2026-04

Classification of 16,635 public user reports (GitHub Issues, Hacker News, Reddit) about AI-agent skills across OpenClaw, Vercel `skills.sh`, and Anthropic Claude Code. Measures the *user experience layer*.

Headline finding: 55% of GitHub user pain is operational correctness — not security, not discovery.

**Use it to:** understand what breaks at runtime, build user-pain benchmarks, extend the taxonomy, or reproduce the user-layer findings in the April 2026 ecosystem study.

| Path | Contents |
|---|---|
| `data/ecosystem-research-2026-04/classified-mentions.csv` | 16,635 classified mentions, one row per report. Links to public sources only — no redistributed body text |
| `data/ecosystem-research-2026-04/pain-distribution.csv` | Aggregate count per pain type |
| `data/ecosystem-research-2026-04/pain-distribution-by-source.csv` | Pain distribution by source (GitHub / HN / Reddit) |
| `data/ecosystem-research-2026-04/README.md` | Schema, taxonomy definitions, and limitations for this dataset |
| `reports/state-of-agent-skills-ecosystem-2026-04.md` | Narrative analysis |

---

## How to cite

The Zenodo record at [doi.org/10.5281/zenodo.19691714](https://doi.org/10.5281/zenodo.19691714) is the stable, archived citation target. Use it for papers and reports. The GitHub repo is the browse and reproduce entry point.

### Ecosystem study (April 2026)

**Plain text:**
> Bhardwaj, M. (2026). *The AI Agent Skills Ecosystem: Registry, Scanner, and User View*. Vessel. https://doi.org/10.5281/zenodo.19691714

**BibTeX:**
```bibtex
@misc{vessel_agent_skills_ecosystem_2026_04,
  author       = {Bhardwaj, Mehul},
  title        = {The AI Agent Skills Ecosystem: Registry, Scanner, and User View},
  year         = {2026},
  month        = {4},
  publisher    = {Vessel},
  doi          = {10.5281/zenodo.19691714},
  url          = {https://doi.org/10.5281/zenodo.19691714},
  license      = {CC-BY-4.0}
}
```

### Catalog dataset

**Plain text:**
> Bhardwaj, M. (2026). *OpenClaw Skills Catalog: Linux Compatibility and Registry Metadata*. Vessel. https://doi.org/10.5281/zenodo.19691714

---

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

`downloads`, `installs`, and `stars` will drift from the published snapshot (these update continuously on ClawHub). Everything else should match within ±1% row count, barring skills added or removed between the snapshot date and your run.

A public-read `GITHUB_TOKEN` is required — unauthenticated requests are rate-limited. The scan uses ~200 API calls.

---

## Licensing

- **Data** (`data/`, `reports/`) — [CC BY 4.0](./LICENSE-DATA). Use freely; attribute.
- **Code** (`scripts/`) — [MIT](./LICENSE-CODE).

---

## Known limitations

Static analysis only. Skills are not executed. SKILL.md completeness is voluntary — declared dependencies may be incomplete. Moderation status reflects ClawHub staff flags only; it is not a security audit. Full list in [LIMITATIONS.md](./LIMITATIONS.md).

---

## Contributing

- **Row looks wrong?** Open an issue with the skill slug and the correction.
- **Scan logic disagreement?** Open a PR in the [Vessel repo](https://github.com/vesselofone/vessel) against `packages/infra/scripts/catalog-coverage.py`. Changes mirror here automatically.
- **New columns?** File an issue. Schema additions are append-only; renames and reorders force a major version bump.

---

## Contact

Dataset questions: open an issue on this repo.  
Commercial use or custom cuts: mehul@vesselofone.com
