# Dataset Schema

`data/latest.csv` (and each dated `data/skills-YYYY-MM-DD.csv` snapshot) has the columns below in this order. A row represents one skill at one point in time.

## Columns

| Column | Type | Nullable | Enum / format | Description |
|---|---|---|---|---|
| `rank` | int | no | | Row index within this snapshot. Rows are sorted by `downloads` descending when ClawHub data is available, else by `slug` alphabetical. `rank=1` is the top skill. |
| `slug` | string | no | | Skill slug (e.g. `humanizer`). Globally unique in ClawHub. |
| `owner` | string | no | | GitHub handle of the skill author (e.g. `biostartechnology`). Composed with `slug` as `skills/{owner}/{slug}/` in the openclaw/skills repo tree. |
| `display_name` | string | no | | Human-readable name from ClawHub, falls back to `slug`. |
| `downloads` | int | no | | All-time ClawHub download count. `0` when no ClawHub entry exists. |
| `installs` | int | no | | All-time ClawHub install count (distinct from downloads — install is a user action, download can be indirect). `0` when unavailable. |
| `has_skill_md` | bool | no | `true`, `false` | Whether a `SKILL.md` file was present and fetchable at the time of scan. |
| `coverage` | string | no | `no_md`, `no_deps`, `env_only`, `fully_resolved`, `brew_blocked`, `unmapped_blocked` | Classification of the skill's dependency resolution. See METHODOLOGY.md §3. |
| `bins_required` | list[string] | yes | pipe-joined | Binaries the skill declares via `requires.bins` or `requires.anyBins`. |
| `env_required` | list[string] | yes | pipe-joined | Environment variables the skill declares via `requires.env`. |
| `bin_classifications` | JSON string | no | JSON object | Per-binary classification: `{"rg": "static", "docker": "unmapped"}`. Values are `system`, `static`, `dynamic`, `brew`, `unmapped`. |
| `os_required` | list[string] | yes | pipe-joined | Operating systems the skill declares via `requires.os`. Usually empty — most SKILL.md files do not declare OS constraints. |
| `stars` | int | no | | ClawHub star count. `0` when no ClawHub entry exists. |
| `summary` | string | yes | | Short description from ClawHub. Empty when no ClawHub entry exists. |
| `created_at` | string | yes | ISO 8601 UTC | Timestamp the skill was first registered on ClawHub. |
| `updated_at` | string | yes | ISO 8601 UTC | Timestamp of the most recent ClawHub-tracked update (new version, metadata change). |
| `latest_version` | string | yes | semver | Latest published version on ClawHub. |
| `latest_version_at` | string | yes | ISO 8601 UTC | Timestamp the latest version was published. |
| `moderation_status` | string | no | `clean`, `flagged`, `unknown` | `flagged` means ClawHub staff attached a `moderationInfo` record. `unknown` appears only for skills without ClawHub data. |
| `owner_handle` | string | yes | | ClawHub owner handle. Usually matches `owner` but may differ when ownership transfers. |
| `last_commit_at` | string | yes | ISO 8601 UTC | Timestamp of the most recent commit in `openclaw/skills` that touched this skill's `SKILL.md`. Used as a proxy for skill activity. |
| `last_commit_sha` | string | yes | 40-char hex | Commit SHA of `last_commit_at`. |
| `install_kinds` | list[string] | yes | pipe-joined | Distinct `install[].kind` values from the SKILL.md (e.g. `apt`, `npm`, `uv`, `go`, `tarball`). Empty when the skill declares no install specs. |

## List encoding

List-typed columns (`bins_required`, `env_required`, `os_required`, `install_kinds`) are pipe-joined (`foo|bar|baz`) because CSV quoting of nested delimiters is fragile across parsers. An empty list is serialized as `""` (empty string).

## JSON column

`bin_classifications` is a JSON string (not a list) because the shape is a map, not a sequence. Parse with `JSON.parse` / `json.loads` after CSV decoding.

## Changelog of columns

Schema follows **append-only evolution**: new columns are added at the end, existing columns are never renamed or reordered. This keeps downstream parsers stable across weekly refreshes.

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-04-19 | Initial schema: 11 base columns + 12 extended columns. Extended columns added: `os_required`, `stars`, `summary`, `created_at`, `updated_at`, `latest_version`, `latest_version_at`, `moderation_status`, `owner_handle`, `last_commit_at`, `last_commit_sha`, `install_kinds`. |
