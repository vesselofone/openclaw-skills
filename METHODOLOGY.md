# Methodology

How the `data/latest.csv` numbers are produced, from discovery to classification.

## 1. Sampling

Source of truth is the `openclaw/skills` GitHub repository. One pass per run:

1. Fetch the recursive Git tree at HEAD via the GitHub API (`GET /repos/openclaw/skills/git/trees/HEAD?recursive=1`). One API call returns every path in the repo.
2. If the tree is truncated (rare — happens near the 100K-entry limit), fall back to per-directory listing via the Contents API. Truncation is logged but has not blocked a scan to date.
3. Filter to `skills/<owner>/<slug>/` directories. Each `(owner, slug)` pair is one row.

No sampling. No ordering bias. The dataset is the full catalog at HEAD at the moment the cron runs.

## 2. Dependency resolution

For each skill:

1. Fetch `skills/<owner>/<slug>/SKILL.md` via the GitHub raw endpoint.
2. Parse frontmatter. Two formats are supported:
   - `metadata: '{"openclaw":{"requires":{"bins":["rg"]}}}'` (JSON inside YAML).
   - `requires:\n  bins:\n    - rg` (plain YAML).
3. Extract `requires.bins`, `requires.anyBins`, `requires.env`, `requires.os`, and `install[].kind`.
4. Resolve each binary against `scripts/sidecar/bin-name-map.json`:
   - `system` — the binary is always on a Linux PATH (`git`, `curl`, `python3`, and a short list of system provisions).
   - `static` — the binary has an entry in `bin-name-map.json` (apt package, npm package, uv tool, Go install path, or SHA256-pinned tarball).
   - `dynamic` — the SKILL.md declares an `install:` spec for this binary that has a Linux-compatible path.
   - `brew` — the SKILL.md only declares a `brew`-kind install spec (macOS-only).
   - `unmapped` — the binary has no install path anywhere.

Fields not declared are treated as empty, not as failed. No SKILL.md means `coverage = no_md`.

## 3. Coverage classification

Each skill receives one `coverage` value:

- `no_md` — no `SKILL.md` fetched. We cannot classify. Not counted as "works" or "blocked".
- `no_deps` — SKILL.md present, no `requires.bins`, no `requires.env`. Runs immediately.
- `env_only` — SKILL.md present, env vars declared, no binary deps. Runs after the user sets keys.
- `fully_resolved` — every required binary resolves to `system`, `static`, or `dynamic`. Runs today on a Linux VM.
- `brew_blocked` — at least one required binary only resolves to `brew` (macOS path). Does not run on Linux without work.
- `unmapped_blocked` — at least one required binary has no install path anywhere. Does not run on Linux.

The headline "works on Linux today" percentage is `no_deps + env_only + fully_resolved` divided by total skills with a SKILL.md. Skills without SKILL.md are excluded from the denominator rather than counted as blocked, since their status is unknown rather than broken.

## 4. ClawHub metadata

For each skill we query the ClawHub Convex API (`skills:getBySlug`) with just the `slug` field (ClawHub enforces global uniqueness at the slug level). Fields captured per skill:

- `skill.stats.downloads`, `installsAllTime`, `stars`.
- `skill.displayName`, `summary`, `createdAt`, `updatedAt`.
- `latestVersion.version`, `createdAt` (as `latest_version_at`).
- `owner.handle`.
- `moderationInfo` presence → `moderation_status = flagged` when a record exists, `clean` otherwise.

Fields the ClawHub API shape does not currently expose (license, semantic tags, OS metadata) are not included in the dataset. They may be added in a future schema bump if the registry starts surfacing them.

## 5. Last-commit dates

To surface "how active is this skill" without per-file GitHub API calls (which would exhaust the 5,000/hr token limit on ~7K skills), we:

1. Shallow-clone `openclaw/skills` with `--filter=blob:none` once per run. History only, no file contents. ~900 MB on disk.
2. Run one `git log --no-merges --name-only --pretty=format:COMMIT<TAB>%H<TAB>%cI -- 'skills/*/*/SKILL.md'`.
3. The pathspec restricts the scan to commits that touched a SKILL.md. Parse top-down (newest first), record the first timestamp seen per `(owner, slug)` pair.

Using SKILL.md as the "last activity" proxy rather than any file under the skill directory is a deliberate choice: it captures version bumps and metadata changes, which are what data consumers care about. README-only edits without a SKILL.md bump are rare in this catalog.

## 6. Caching and reproducibility

- GitHub tree listings, SKILL.md fetches, ClawHub responses, and commit maps are cached by content-addressable keys in `coverage-output/cache.json`.
- ClawHub cache key is `clawhub_v2:<slug>` in extended mode so schema changes force a refetch without discarding backward-compat data.
- Commit maps are keyed on `commits_v1:<head_sha>`, so re-running at the same `openclaw/skills` HEAD is free.
- A cached re-run reproduces the CSV byte-identical except for `downloads`, `installs`, and `stars` values, which drift with user activity even when HEAD is unchanged.

Snapshots (`data/skills-YYYY-MM-DD.csv`) are dated artifacts, not recoverable recomputations. If you need to cite a specific snapshot, pin by commit SHA in this dataset repo.

## 7. Rate limits and failure handling

- GitHub: a token is required (`GITHUB_TOKEN`) — unauthenticated requests are throttled to 60/hr. Scan typically consumes ~200 authenticated calls (most work happens via the single tree fetch).
- ClawHub: no published rate limit. 25 concurrent workers empirically does not trigger throttling. Per-slug fetches that fail return `{}` and the row is written with empty ClawHub fields.
- SKILL.md 404: counted as `has_skill_md = false`. Never fatal.
- `git log` timeout: the pathspec-filtered pass completes in ~5 minutes on a full catalog clone. The runner allows 15 minutes before failing.

A scan that partially completes is discarded — the CSV is only written after every stage finishes cleanly.
