# Ecosystem Research — AI Agent Skill Pain Points (April 2026)

**Snapshot date:** 2026-04-20
**Window:** 90 days ending 2026-04-20
**Corpus:** 16,840 mentions; 16,635 classified (98.8%)
**License:** [CC BY 4.0](../../LICENSE-DATA) — use, remix, attribute

A classified dataset of user-reported problems with AI-agent skills, aggregated from public GitHub issues, Hacker News, and Reddit. Complements the [OpenClaw Skills Catalog](../../README.md) — that dataset measures the *registry*; this one measures the *user experience*.

## Files

| File | Rows | Description |
|---|---:|---|
| `classified-mentions.csv` | 16,635 | One row per user mention. Columns: `source, context, kind, title, url, created_at, pain, pain_reason`. Links only — raw body text is not redistributed. |
| `pain-distribution.csv` | 12 | Aggregate count per pain type. |
| `pain-distribution-by-source.csv` | 36 | Pain distribution segmented by source (GitHub / HN / Reddit). |

## Schema — `classified-mentions.csv`

| Column | Type | Description |
|---|---|---|
| `source` | enum | `github-issue` \| `hn` \| `reddit` |
| `context` | string | Repo (GitHub), "story"/"comment" (HN), or subreddit name (Reddit) |
| `kind` | string | Record kind within its source (`issue`, `story`, `comment`, `post`) |
| `title` | string | Title of the issue / post / comment (as scraped). May be empty for HN comments. |
| `url` | URL | Permalink to the original public mention |
| `created_at` | ISO 8601 | When the original mention was posted |
| `pain` | enum | One of 12 classified pain types (see below) |
| `pain_reason` | string | Short (<50 char) free-text reason from the classifier |

## Pain taxonomy (12 types)

| Type | Definition |
|---|---|
| `compat` | OS/platform/version incompatibility (e.g. works on macOS, fails on Linux or Windows) |
| `silent-failure` | Skill ran without raising an error but produced wrong or no output |
| `maintenance` | Skill is abandoned, outdated, dead repo, schema drift |
| `security` | Credential leak, command injection, malicious or suspicious behavior |
| `quality` | Bad prompts, hallucination, poor output quality, UX regressions |
| `docs` | Documentation missing, wrong, outdated, or unclear |
| `cross-skill` | Skills conflict, dependency hell, breaking each other |
| `discovery` | Hard to find, compare, or search for skills |
| `registry-meta` | Registry platform bugs (stale index, slow UI, broken upload, search) |
| `install` | Installation failures, missing dependencies, setup breaks |
| `other` | Clearly about AI-agent skills but doesn't fit the above |
| `noise` | Not about AI-agent skills (e.g. keyword match on unrelated content) |

## Sources

- **GitHub Issues** — `vercel-labs/skills`, `anthropics/claude-code`, `anthropics/claude-agent-sdk-typescript`
- **Hacker News** — Algolia API, keywords: `openclaw`, `SKILL.md`, `claude skill`, `claude code skill`, `clawhub`, `claw skill`, `openclaw/skills`, `skill registry`, `agent marketplace`, `skill broken`, `skill doesn't work`
- **Reddit** — public JSON on: `LocalLLaMA`, `ChatGPTCoding`, `ClaudeAI`, `OpenAI`, `singularity`, `ArtificialInteligence`, `MachineLearning`, `AI_Agents`, `AgentLaboratory`, `AutoGPT`, `LangChain`, `OpenClaw`

## Classifier

Each row was classified by Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) using tool-use structured output with an enum-constrained schema. Single-label classification with a short free-text reason.

## Citation

If you use this dataset, please cite:

> Bhardwaj, M. (2026). *AI Agent Skills — User Pain Classification, April 2026* [Dataset]. Vessel. https://github.com/vesselofone/openclaw-skills

```bibtex
@dataset{vessel_agent_skills_pain_2026_04,
  author    = {Bhardwaj, Mehul},
  title     = {AI Agent Skills — User Pain Classification, April 2026},
  year      = {2026},
  publisher = {Vessel},
  url       = {https://github.com/vesselofone/openclaw-skills/tree/main/data/ecosystem-research-2026-04},
  license   = {CC-BY-4.0}
}
```

See the full narrative analysis: [`../../reports/state-of-agent-skills-ecosystem-2026-04.md`](../../reports/state-of-agent-skills-ecosystem-2026-04.md)

## Limitations (brief — full version in the report)

1. Single-label classification; edge-case mentions with overlapping pain types are forced into one bucket.
2. GitHub basic pagination capped at 100 pages per repo; `anthropics/claude-code` corpus tail is not covered.
3. Hacker News search matched 55% noise (unrelated "openclaw" keyword hits). The `noise` tag filters this; do not use HN subset without filtering.
4. Reddit is rate-limited without auth; 1,301 rows is a floor.
5. 205 rows (~1.2%) remain unclassified due to rate-limit exhaustion during the classification run.
6. LLM classifier is not ground truth. A human-agreement study on a sample would tighten confidence intervals.

## What this dataset does NOT include (intentionally)

- **Raw body text** of scraped content — redistribution boundaries vary per platform.
- **Author usernames** from HN and Reddit — privacy-conservative.
- **Internal Vessel roadmap implications** — those live in private product docs, not in research output.
