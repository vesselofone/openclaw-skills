# The State of AI Agent Skills: What Breaks, April 2026

**A 90-day classification of 16,840 user reports from GitHub, Hacker News, and Reddit.**

- **Author:** Mehul Bhardwaj, Vessel
- **Published:** 2026-04-20
- **License:** [CC BY 4.0](../LICENSE-DATA) — cite, quote, remix
- **Dataset:** [`data/ecosystem-research-2026-04/`](../data/ecosystem-research-2026-04/)
- **Repository:** https://github.com/vesselofone/openclaw-skills

---

## Summary

Between January 21 and April 20, 2026, we scraped 16,840 public mentions of AI-agent skills from three channels: GitHub issues on the major skill-ecosystem repositories (`vercel-labs/skills`, `anthropics/claude-code`, `anthropics/claude-agent-sdk-typescript`), Hacker News via Algolia, and 12 AI-focused subreddits on Reddit. 16,635 (98.8%) were classified by Claude Haiku 4.5 into one of twelve pain types.

Five findings:

1. **On GitHub — where signal-to-noise is highest — 55% of user pain is operational correctness**, not security, not discovery. The four operational pain types (quality 21%, silent-failure 18%, compat 9%, install 7%) dominate.
2. **Silent failure is an underrecognized category.** 1,891 GitHub issues (18%) describe a skill that ran without raising an error but produced wrong or no output. This is the failure mode that every existing tool — registries, scanners, install logs — is structurally blind to.
3. **Discovery is a 2% problem on GitHub.** Users do not file issues about difficulty finding skills. The "better skill search" product thesis is not backed by bug-reporting data.
4. **Security is a 1% user-reported problem on GitHub but a 37% static-scan problem per Snyk's [ToxicSkills](https://snyk.io/research/) study.**[^snyk] These numbers measure different things — reported vs. discoverable — and both are real. Users don't report flaws they can't see.
5. **Cross-platform compatibility is a specific, bounded pain.** 9% of GitHub issues describe a skill that works on one OS but fails on another — most often macOS-only skills breaking on Linux or Windows.

**All findings are reproducible.** The full classified dataset is published under CC BY 4.0 in this repository, linking every count to its original public GitHub issue / HN post / Reddit thread.

---

## Methodology

### Sources and volume

| Source | Collection | Scope | Rows |
|---|---|---|---:|
| GitHub Issues | Paginated REST API, PRs filtered out | `vercel-labs/skills`, `anthropics/claude-code`, `anthropics/claude-agent-sdk-typescript` | 10,442 |
| Hacker News | Algolia full-text API | 11 keywords × {story, comment}, 90-day window | 5,097 |
| Reddit | Public JSON search | 12 subreddits, OR-joined keyword query, 1.2s spacing | 1,301 |
| **Total** | | | **16,840** |

Keyword set: `openclaw`, `claw skill`, `clawhub`, `SKILL.md`, `openclaw/skills`, `claude skill`, `claude code skill`, `skill registry`, `agent marketplace`, `skill broken`, `skill doesn't work`.

Subreddit set: `LocalLLaMA`, `ChatGPTCoding`, `ClaudeAI`, `OpenAI`, `singularity`, `ArtificialInteligence`, `MachineLearning`, `AI_Agents`, `AgentLaboratory`, `AutoGPT`, `LangChain`, `OpenClaw`.

### Classification

Each mention was classified by Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via the Anthropic API using tool-use structured output with an enum-constrained schema and a short free-text reason. Single-label assignment — a mention that fits multiple pain types is forced into one bucket, which adds ≤2% noise to any per-type percentage.

Batches of 20 rows per API call, prompt caching on the taxonomy system prompt, resumable via ID-skip against an existing output file. 16,635 rows were classified on first or second pass; 205 (1.2%) remain unclassified due to sustained rate-limit pressure. The full prompt and twelve definitions are in [`data/ecosystem-research-2026-04/README.md`](../data/ecosystem-research-2026-04/README.md).

### Pain taxonomy

| Type | Definition |
|---|---|
| `compat` | OS/platform/version incompatibility |
| `silent-failure` | Skill ran without error but produced wrong or no output |
| `maintenance` | Abandoned, outdated, dead repo, schema drift |
| `security` | Credential leak, command injection, malicious behavior |
| `quality` | Bad prompts, hallucination, poor output, UX regressions |
| `docs` | Documentation missing, wrong, outdated, or unclear |
| `cross-skill` | Skills conflict, dependency hell, breaking each other |
| `discovery` | Hard to find, compare, or search for skills |
| `registry-meta` | Registry platform bugs (stale index, broken search, slow UI) |
| `install` | Installation failures, missing dependencies, setup breaks |
| `other` | Clearly about skills but doesn't fit the above |
| `noise` | Not about AI-agent skills (keyword match on unrelated content) |

---

## Findings

### 1. Overall distribution

| Pain type | Count | % of 16,635 |
|---|---:|---:|
| `other` | 3,983 | 24% |
| `noise` | 3,949 | 24% |
| **`quality`** | **2,577** | **15%** |
| **`silent-failure`** | **1,939** | **12%** |
| `compat` | 979 | 6% |
| `install` | 855 | 5% |
| `docs` | 735 | 4% |
| `security` | 450 | 3% |
| `discovery` | 412 | 2% |
| `registry-meta` | 338 | 2% |
| `maintenance` | 308 | 2% |
| `cross-skill` | 110 | 1% |

Signal (all non-noise, non-other categories combined): **52%**.

### 2. Signal varies sharply by source

| Source | Noise + Other | Top two real pains |
|---|---:|---|
| GitHub Issues | 30% | quality 21% · silent-failure 18% |
| Reddit | 61% | discovery 8% · quality 8% |
| Hacker News | 80% | quality 7% · security 5% |

Hacker News is keyword-match-heavy: searches for `openclaw` matched Peter Steinberger's unrelated TedTalk and multiple `OpenChain` conversations. Reddit is diffuse and conversational. **GitHub issues is the signal-rich source. Subsequent analysis is GitHub-only unless stated.**

### 3. GitHub-only distribution (10,256 classified issues)

| Pain type | Count | % |
|---|---:|---:|
| `other` | 2,340 | 23% |
| **`quality`** | **2,125** | **21%** |
| **`silent-failure`** | **1,891** | **18%** |
| **`compat`** | **927** | **9%** |
| `noise` | 752 | 7% |
| **`install`** | **745** | **7%** |
| `docs` | 549 | 5% |
| `registry-meta` | 294 | 3% |
| `maintenance` | 242 | 2% |
| `discovery` | 177 | 2% |
| `security` | 143 | 1% |
| `cross-skill` | 71 | 1% |

**The operational-correctness cluster (quality + silent-failure + compat + install) is 55% of GitHub user chatter.**

### 4. The four failure modes — with evidence

Each link below is a public GitHub issue in the dataset. Three representative examples per pain type, selected for clarity rather than extremity.

#### Quality — 21% on GitHub

Skills that ship but behave incorrectly, have confusing UX, or silently do the wrong thing when invoked with common inputs.

- `--help` flag silently executes the subcommand instead of printing help: [`vercel-labs/skills#960`](https://github.com/vercel-labs/skills/issues/960)
- Read-only `skills check` command *reinstalls* outdated skills instead of reporting: [`vercel-labs/skills#954`](https://github.com/vercel-labs/skills/issues/954)
- Selection UX ignores `space` and `return` inconsistently: [`vercel-labs/skills#936`](https://github.com/vercel-labs/skills/issues/936)

#### Silent failure — 18% on GitHub

The archetypal agent-era bug: the command succeeds, the log says "OK," and the expected outcome did not happen.

- `skills update` reports success without updating the skill contents: [`vercel-labs/skills#923`](https://github.com/vercel-labs/skills/issues/923)
- Dotfiles silently dropped during install from remote repositories: [`vercel-labs/skills#943`](https://github.com/vercel-labs/skills/issues/943)
- Scoped `npx skills update <skill-name>` unscoped: adds all other skills from the repo without error: [`vercel-labs/skills#915`](https://github.com/vercel-labs/skills/issues/915)

#### Compat — 9% on GitHub

Skills that work on one platform and fail on another. Almost always macOS works, Linux or Windows doesn't.

- `skills update` fails on Windows when the Node.js path contains spaces: [`vercel-labs/skills#941`](https://github.com/vercel-labs/skills/issues/941)
- Global-install skills update broken on Windows v1.5.0: [`vercel-labs/skills#840`](https://github.com/vercel-labs/skills/issues/840)
- CLI fails with an RFC 0.2 schema version mismatch across skill authors: [`vercel-labs/skills#949`](https://github.com/vercel-labs/skills/issues/949)

#### Install — 7% on GitHub

Installation fails outright, or succeeds with file-level corruption.

- `npx skills add` corrupts binary files fetched from well-known sources: [`vercel-labs/skills#953`](https://github.com/vercel-labs/skills/issues/953)
- Install renames source directory, breaking relative path references: [`vercel-labs/skills#917`](https://github.com/vercel-labs/skills/issues/917)
- Update command creates an unexpected `skills/` folder at project root: [`vercel-labs/skills#916`](https://github.com/vercel-labs/skills/issues/916)

### 5. What is *not* a major user-reported problem

#### Discovery — 2% on GitHub

The three discovery-tagged GitHub issues in the top sample are all *listing requests* — users asking the registry to *index* their skill, not users complaining about finding skills to install:

- `Listing: Request indexing for salvatorv/stem-tutor` — [`vercel-labs/skills#964`](https://github.com/vercel-labs/skills/issues/964)
- `Listing: Request indexing for factory-x-contributions/business-models` — [`vercel-labs/skills#947`](https://github.com/vercel-labs/skills/issues/947)
- `Listing: Request indexing for agentspace-so/skills` — [`vercel-labs/skills#945`](https://github.com/vercel-labs/skills/issues/945)

This should caution anyone building "the Google for skills" — the demand expressed by issue-filers is publication, not discovery.

#### Security — 1% on GitHub

Low as a user-reported pain, but high as a structurally-discoverable one. Snyk's ToxicSkills study[^snyk] found 36.82% of ClawHub skills have at least one security flaw; 43.4% contain command-injection patterns; 70.1% exhibit OAuth over-provisioning. Koi Security's [ClawHavoc](https://www.koi.ai/research) analysis[^koi] confirmed 824+ malicious skills distributing AMOS infostealers on ClawHub in January 2026 — roughly 12% of the ecosystem at the time. These are real threats that users overwhelmingly cannot see from the install side.

A representative user-visible report, for context: [`vercel-labs/skills#921`](https://github.com/vercel-labs/skills/issues/921) — `Security: malicious package roin-orca/skills in the ecosystem (SSRF + self-propagation)`.

---

## Interpretation

### Why silent failure is the structural gap

Every existing trust tool in the ecosystem — registry curation (ClawHub verification), static scanners (Snyk ToxicSkills, SkillsGate scan), runtime guards (Lakera, Guardrails AI) — answers questions about a skill *before* it runs. None of them answer whether the skill *produces correct output* once it does run.

This matches the shape of 18% of GitHub user pain: the command exited zero, the install log was green, the scanner said clean, and the skill still did the wrong thing. Fixing this requires a different class of tool — a harness that runs skills against golden inputs in a clean environment and compares outputs. That tool does not exist as a widely-adopted public product today.

### Why compat is bounded and solvable

The 9% `compat` slice concentrates on a small number of mechanical problems: path handling on Windows, macOS-only binaries assumed to exist, Node version mismatches. All of these are detectable by running the skill in a matrix of clean containers. The per-skill cost is one CI workflow, and the signal is unambiguous: either `install` exits zero or it doesn't.

### Why discovery is not the wound

13,729 skills on ClawHub, 83,627 on skills.sh. Users are not drowning in information asymmetry about which skills exist. They're drowning in uncertainty about which installed skills *work*. A product that indexes more skills addresses the less-reported problem. A product that verifies skills' behavior addresses the more-reported one.

---

## Prior and related research

This dataset complements — not replaces — several existing public studies.

- **Snyk, ToxicSkills.**[^snyk] Static-analysis scan of every ClawHub skill. Finds 36.82% have ≥1 security flaw; 13.4% critical-severity; 70.1% request over-provisioned OAuth scopes; 43.4% contain command-injection patterns. Measures *scanner-discoverable flaws*; our dataset measures *user-reported pain*. Both categories are real.
- **Koi Security / Repello AI, ClawHavoc analysis.**[^koi] Identifies 824+ malicious skills active in the January 2026 ClawHub campaign distributing AMOS infostealers. Confirms shared C2 infrastructure across 335 skills (single coordinated actor).
- **Microsoft Security, "Running OpenClaw Safely"** (February 2026). Enterprise-facing guidance — adoption is growing, the attack surface is growing, defensive tools are partial.
- **MITRE ATLAS framework** (AML.TA0003–AML.TA0009). Standardized tactics/techniques taxonomy for adversarial AI threats. Our `security` pain type does not re-derive this — it counts how often users encounter/report it in public channels.
- **jgamblin/OpenClawCVEs.** Hourly-updated indicator-of-compromise feed for OpenClaw skills. Churn rate justifies an hourly cadence; static snapshots grow stale fast.
- **OpenClaw Skills Catalog** (this repository, `../README.md`). Weekly refresh of ClawHub registry metadata + Linux compatibility status per skill. Measures the registry; this report measures the user experience.

---

## Limitations

1. **Single-label classification.** Each mention gets one pain tag. Mentions with overlapping signal (e.g. a compat bug that also has bad docs) are forced into the more specific bucket, adding ~2% noise to per-type percentages.
2. **GitHub basic pagination cap.** The REST API `page=` parameter is capped at 100 pages. `anthropics/claude-code` has ~10,000 issues; ~9,756 landed, the tail was truncated. Does not affect classification accuracy of the corpus that did land.
3. **Hacker News keyword noise.** Algolia fuzzy-matched `openclaw` against unrelated content (a Peter Steinberger TedTalk; OpenChain). 55% of HN rows are tagged `noise`. Filter HN to signal-only before using it for derivative analysis.
4. **Reddit under-sampled.** Public JSON is rate-limited; 1,301 rows is a floor, not a ceiling. Reddit-specific conclusions should be treated as indicative.
5. **205 unclassified rows (1.2%).** Sustained rate-limit pressure during classification. Does not change any per-type conclusion.
6. **LLM classifier is not ground truth.** Calibrated against a spot-check of reasons vs. titles, but an LLM-vs-human inter-rater agreement study on a sample would tighten confidence intervals.
7. **90-day window.** Single slice. Whether pain categories are rising or falling is not answered here.

---

## How to cite

**Plain text:**

> Bhardwaj, M. (2026). *The State of AI Agent Skills: What Breaks, April 2026*. Vessel. https://github.com/vesselofone/openclaw-skills/blob/main/reports/state-of-agent-skills-ecosystem-2026-04.md

**BibTeX:**

```bibtex
@misc{vessel_agent_skills_april_2026,
  author       = {Bhardwaj, Mehul},
  title        = {The State of AI Agent Skills: What Breaks, April 2026},
  year         = {2026},
  publisher    = {Vessel},
  howpublished = {\url{https://github.com/vesselofone/openclaw-skills/blob/main/reports/state-of-agent-skills-ecosystem-2026-04.md}},
  note         = {Dataset: \url{https://github.com/vesselofone/openclaw-skills/tree/main/data/ecosystem-research-2026-04}},
  license      = {CC-BY-4.0}
}
```

**For journalists:** All numbers in this report are reproducible from [`data/ecosystem-research-2026-04/classified-mentions.csv`](../data/ecosystem-research-2026-04/classified-mentions.csv). Every URL in that file links to a public mention. Feel free to independently verify any claim; open an issue on this repo if a number doesn't check out.

---

## About

**Vessel** builds infrastructure for running AI agents in production. We publish research on the agent ecosystem as a complement — not a marketing wrapper around — our product. The classified dataset is free. The methodology is open. Our product (https://vesselofone.com) is a separate thing; the research is useful regardless of whether you care about our product.

Questions, corrections, collaboration: open an issue on this repository.

---

[^snyk]: Snyk Labs. *ToxicSkills: Security Analysis of the OpenClaw/ClawHub Skill Ecosystem*. Referenced numbers: 36.82% flawed, 43.4% command-injection, 70.1% OAuth over-provision, 13.4% critical-severity.
[^koi]: Koi Security / Repello AI. *ClawHavoc: 824+ Malicious Skills on ClawHub, January 2026*. Confirmed shared C2 infrastructure (IP 91.92.242.30) across 335 AMOS-delivering skills.
