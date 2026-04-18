# Limitations

What this dataset does not tell you, and why the numbers are what they are.

## 1. Static analysis only

Every classification is derived by reading `SKILL.md` frontmatter and matching binaries against a Linux install map. No skill is actually executed. A skill marked `fully_resolved` means "every binary it declares has a Linux install path we know about" — not "this skill works end-to-end." Runtime failures (missing env vars, API auth issues, race conditions, model misbehavior) are outside this dataset.

## 2. SKILL.md completeness is voluntary

Skill authors are not required to declare dependencies exhaustively. A skill that runs `git` in its body but does not list `git` in `requires.bins` will appear as `no_deps` in this dataset and still fail to run on a stripped-down environment. We treat the frontmatter as authoritative because there is no practical way to infer shell invocations from the body at scale without executing the skill.

## 3. No execution sandbox

"Works on Linux today" means the declared dependencies resolve on a standard Linux VM with the Vessel install map applied. It does not mean the skill has been executed against any real workload. A skill can resolve cleanly and still be useless (bad prompts, broken integrations, outdated API targets).

## 4. ClawHub-first universe

Skills that exist in `openclaw/skills` but not on ClawHub (no registration, or removed) have `downloads`, `installs`, `stars`, `summary`, and all ClawHub-derived fields empty. This is a subset of the catalog — estimate it at single-digit percent most weeks — but it is real. The `moderation_status = unknown` value is a reliable marker for these rows.

## 5. Security data not included

This dataset does not re-derive security findings. The `moderation_status` field only reflects whether ClawHub staff have flagged a skill; it does not classify attack class or severity. Third-party security audits (Snyk, Koi Security, Repello AI) apply their own methodologies and are cited in the accompanying article without re-computation. Cross-referencing this dataset against a published audit is left to the reader.

## 6. First public snapshot is full-catalog, alphabetical predecessor retired

The original scan published alongside the v1 article sampled the top-1000 skills in `openclaw/skills` alphabetical order. Starting with the `2026-04-19` snapshot, this dataset is full-catalog from the start, ordered by `downloads` descending. References to "the top 1,000" in archived articles refer to the alphabetical sample, not this dataset's row order.

## 7. Weekly drift

Snapshots are taken Mondays 07:00 UTC. By the time you read the dataset, `downloads`, `installs`, `stars`, and any newly added skills may be up to 7 days behind the registry. `updated_at` and `last_commit_at` are frozen at the moment of the scan. For near-real-time data, query the ClawHub API directly.

## 8. No per-skill attribution

Individual skill authors have not been contacted or asked to validate this dataset. If you are a skill author and find your row inaccurate, file an issue at `github.com/vesselofone/openclaw-skills` with the slug and the correction; rows are edited in the next weekly snapshot rather than rewritten retroactively.

## 9. Install map is Vessel's, not canonical

`scripts/sidecar/bin-name-map.json` encodes the install paths Vessel uses for its own OpenClaw hosting. A different hoster with a different base image or different policy about unsigned tarballs will get different coverage numbers. The methodology is reproducible; the answer is opinionated.
