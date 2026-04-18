#!/usr/bin/env python3
"""
catalog-coverage.py — OpenClaw catalog dependency coverage analysis.

Fetches all skills in the openclaw/skills GitHub repo, parses their SKILL.md
dependency declarations, and generates a funnel report showing what percentage
of skills Vessel can fully resolve today.

Usage:
    python3 packages/infra/scripts/catalog-coverage.py
    python3 packages/infra/scripts/catalog-coverage.py --limit 1000
    python3 packages/infra/scripts/catalog-coverage.py --with-downloads
    python3 packages/infra/scripts/catalog-coverage.py --no-cache

Output (written to packages/infra/scripts/coverage-output/):
    report-YYYY-MM-DD.txt   — human-readable funnel report
    skills-YYYY-MM-DD.csv   — per-skill data (slug, owner, coverage, bins, env, ...)
    cache.json              — HTTP response cache (reused on next run, delete to refresh)

Funnel stages reported:
    1. Discovery        — skills in catalog, SKILL.md availability
    2. Dep declarations — breakdown by dep type (none / env-only / bins / mixed)
    3. Bin resolution   — each unique binary classified against our resolvers
    4. Skill coverage   — skills grouped: works today / env setup / brew-blocked / unmapped
    5. Quick wins       — top unmapped bins to add for maximum unblock

Default mode analyzes all skills without download ranking (fast, ~1-2 min first run).
Pass --with-downloads to also fetch ClawHub metadata and rank by downloads (~6 min first run).
All HTTP responses are cached; subsequent runs are instant.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Generator

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
BIN_MAP_PATH = SCRIPT_DIR / "sidecar" / "bin-name-map.json"
OUTPUT_DIR = SCRIPT_DIR / "coverage-output"

# ── Constants ─────────────────────────────────────────────────────────────────

CLAWHUB_CONVEX = "https://wry-manatee-359.convex.cloud"
OPENCLAW_SKILLS_RAW = "https://raw.githubusercontent.com/openclaw/skills/main/skills"
GITHUB_API = "https://api.github.com"

# Install kinds the sidecar handles on Linux VMs (mirrors SkillsSummaryCard.tsx)
LINUX_COMPATIBLE_KINDS = {"node", "download", "uv", "go"}

# Bins always in the container's system PATH — never truly missing
SYSTEM_PROVIDED_BINS = {"python3", "python", "node", "npm", "npx", "curl", "git", "bash", "sh", "jq"}

# ── HTTP / cache ──────────────────────────────────────────────────────────────

class DiskCache:
    """Simple JSON file cache — survives between runs."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._data: dict[str, Any] = {}
        if enabled and path.exists():
            try:
                self._data = json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                pass

    def get(self, key: str) -> Any:
        return self._data.get(key) if self.enabled else None

    def set(self, key: str, value: Any) -> None:
        if self.enabled:
            self._data[key] = value

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data))


def _make_headers(github_token: str | None = None) -> dict[str, str]:
    h = {"User-Agent": "VesselCatalogCoverage/1.0"}
    if github_token:
        h["Authorization"] = f"token {github_token}"
    return h


def http_get(url: str, timeout: int = 12, headers: dict | None = None) -> Any:
    """GET url, return parsed JSON or raw str. None on any error."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "VesselCatalogCoverage/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except Exception:
        return None


def convex_query(path: str, args: dict, timeout: int = 10) -> Any:
    """POST to ClawHub Convex API. Returns value on success, None on error."""
    data = json.dumps({"path": path, "format": "json", "args": args}).encode()
    req = urllib.request.Request(
        f"{CLAWHUB_CONVEX}/api/query",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "VesselCatalogCoverage/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            return result["value"] if result.get("status") == "success" else None
    except Exception:
        return None


# ── Stage 1: Skill discovery ──────────────────────────────────────────────────

def fetch_all_skills(cache: DiskCache, github_token: str | None = None) -> list[dict]:
    """
    Return list of {owner, slug} for every skill in openclaw/skills.
    Tries the recursive Git tree first (1 API call). If truncated, falls back
    to listing each owner directory individually (more API calls but complete).
    """
    cached = cache.get("catalog_skills_v2")
    if cached:
        _progress(f"  [cache] {len(cached)} skills")
        return cached

    headers = _make_headers(github_token)

    _progress("  Fetching Git tree from openclaw/skills...")
    tree = http_get(f"{GITHUB_API}/repos/openclaw/skills/git/trees/main?recursive=1", headers=headers)

    skills: list[dict] = []
    if tree and "tree" in tree:
        for item in tree["tree"]:
            path: str = item.get("path", "")
            # skills/{owner}/{slug}/_meta.json
            if path.endswith("/_meta.json") and path.count("/") == 3:
                parts = path.split("/")
                skills.append({"owner": parts[1], "slug": parts[2]})

    if tree and tree.get("truncated"):
        if len(skills) >= 500:
            # Tree returned a large, representative sample — directory listing would add
            # negligible coverage at high API cost. Use tree results as-is.
            _progress(f"  Tree truncated but returned {len(skills)} skills — skipping directory supplement")
        else:
            _progress(f"  Tree truncated (got {len(skills)}). Supplementing with directory listing...")
            dir_skills = _list_skills_by_dir(headers)
            seen = {(s["owner"], s["slug"]) for s in dir_skills}
            for s in skills:
                if (s["owner"], s["slug"]) not in seen:
                    dir_skills.append(s)
                    seen.add((s["owner"], s["slug"]))
            skills = dir_skills

    if not skills:
        _progress("  No skills found via tree or listing — check network/token")

    _progress(f"  Found {len(skills)} skills")
    cache.set("catalog_skills_v2", skills)
    cache.save()
    return skills


def _list_skills_by_dir(headers: dict) -> list[dict]:
    """Enumerate skills via Contents API with pagination (per_page=100)."""
    skills: list[dict] = []

    def get_pages(url: str) -> Iterator[list]:
        """Yield pages from a paginated GitHub Contents API URL."""
        while url:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    if isinstance(data, list):
                        yield data
                    # GitHub paginates via Link header
                    link = resp.headers.get("Link", "")
                    next_url = None
                    for part in link.split(","):
                        part = part.strip()
                        if 'rel="next"' in part:
                            m = part.split(";")[0].strip()
                            if m.startswith("<") and m.endswith(">"):
                                next_url = m[1:-1]
                    url = next_url
            except Exception:
                break

    owners_url = f"{GITHUB_API}/repos/openclaw/skills/contents/skills?per_page=100"
    for page in get_pages(owners_url):
        for owner_item in page:
            if owner_item.get("type") != "dir":
                continue
            owner = owner_item["name"]
            skills_url = f"{GITHUB_API}/repos/openclaw/skills/contents/skills/{owner}?per_page=100"
            for spage in get_pages(skills_url):
                for si in spage:
                    if si.get("type") == "dir":
                        skills.append({"owner": owner, "slug": si["name"]})
            time.sleep(0.05)  # gentle on GitHub API

    return skills


# ── Stage 2: SKILL.md fetch + parse ──────────────────────────────────────────

def fetch_skill_md(owner: str, slug: str, cache: DiskCache) -> str | None:
    """Fetch raw SKILL.md. Returns None on 404/error; empty string cached for misses."""
    key = f"skillmd:{owner}/{slug}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None  # "" → None (cached miss)

    url = f"{OPENCLAW_SKILLS_RAW}/{owner}/{slug}/SKILL.md"
    req = urllib.request.Request(url, headers={"User-Agent": "VesselCatalogCoverage/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode(errors="replace")
            cache.set(key, content)
            return content
    except urllib.error.HTTPError:
        cache.set(key, "")
        return None
    except Exception:
        return None  # transient error — don't cache


def parse_skill_md(content: str) -> dict:
    """
    Parse SKILL.md frontmatter. Returns:
        {
            requires: {bins, env, anyBins, config, os},  # all lists of strings
            install:  [{kind, os, bins, url, ...}],      # list of install specs
        }
    Handles both formats:
      - metadata: '{"openclaw":{"requires":{"bins":["rg"]}}}'  (JSON in YAML)
      - requires:\n  bins:\n    - rg                            (plain YAML)
    """
    result: dict = {"requires": {"bins": [], "env": [], "anyBins": [], "config": [], "os": []}, "install": []}
    if not content or not content.lstrip().startswith("---"):
        return result

    # Extract frontmatter block
    stripped = content.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        return result
    fm_text = stripped[3:end].strip()

    fm = _parse_yaml(fm_text)
    if not isinstance(fm, dict):
        return result

    # Format 1: metadata JSON field (most common in modern SKILL.md files)
    meta_raw = fm.get("metadata")
    if meta_raw:
        if isinstance(meta_raw, str):
            meta_raw = _try_json(meta_raw)
        if isinstance(meta_raw, dict):
            ns: dict = meta_raw.get("openclaw") or meta_raw.get("clawdbot") or {}
            req = ns.get("requires") or {}
            if isinstance(req, dict):
                result["requires"] = {
                    "bins":    _as_list(req.get("bins")),
                    "env":     _as_list(req.get("env")),
                    "anyBins": _as_list(req.get("anyBins")),
                    "config":  _as_list(req.get("config")),
                    "os":      _as_list(req.get("os")),
                }
            inst = ns.get("install") or []
            if isinstance(inst, list):
                result["install"] = inst
            return result

    # Format 2: top-level requires key
    req_raw = fm.get("requires")
    if isinstance(req_raw, dict):
        result["requires"] = {
            "bins":    _as_list(req_raw.get("bins")),
            "env":     _as_list(req_raw.get("env")),
            "anyBins": _as_list(req_raw.get("anyBins")),
            "config":  _as_list(req_raw.get("config")),
            "os":      _as_list(req_raw.get("os")),
        }

    return result


def _parse_yaml(text: str) -> dict:
    """Parse YAML frontmatter. Uses PyYAML if available, else minimal fallback."""
    try:
        import yaml  # type: ignore
        result = yaml.safe_load(text)
        return result if isinstance(result, dict) else {}
    except ImportError:
        pass
    except Exception:
        return {}
    # Minimal fallback: only handles flat key: value and key: 'json-string'
    result: dict = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("#"):
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _try_json(s: str) -> Any:
    """Try parsing s as JSON; also try single-quoted JSON variant."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return json.loads(s.replace("'", '"'))
    except (json.JSONDecodeError, TypeError):
        return None


def _as_list(v: Any) -> list:
    if isinstance(v, list):
        return [str(x) for x in v if x]
    if isinstance(v, str) and v:
        return [v]
    return []


# ── ClawHub download metadata (optional) ─────────────────────────────────────

def _iso_from_ms(ms: Any) -> str:
    """Convert Unix ms timestamp → UTC ISO8601 string. Empty string on falsy input."""
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return ""


def fetch_clawhub_meta(slug: str, cache: DiskCache, extended: bool = False) -> dict:
    """
    Fetch skill metadata from ClawHub. Returns {} on miss.

    Default mode (extended=False) keeps backward-compat shape: downloads, installs, display_name.
    Extended mode additionally captures Tier A+B fields: stars, summary, tags, created_at,
    updated_at, latest_version, latest_version_at, license, moderation_status, owner_handle,
    metadata_os.
    """
    key = f"clawhub_v2:{slug}" if extended else f"clawhub:{slug}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    value = convex_query("skills:getBySlug", {"slug": slug})
    if value is None:
        result: dict = {}
    else:
        skill = value.get("skill") or {}
        stats = skill.get("stats") or {}
        result = {
            "downloads": int(stats.get("downloads") or 0),
            "installs": int(stats.get("installsAllTime") or 0),
            "display_name": skill.get("displayName") or slug,
        }
        if extended:
            # API shape notes (as of 2026-04):
            #   - skill.tags is a version-id pointer (e.g. {"latest": "<id>"}),
            #     NOT semantic tags — drop.
            #   - latestVersion.license and value.metadata.os are always null
            #     in production responses — drop.
            latest = value.get("latestVersion") or {}
            owner = value.get("owner") or {}
            mod = value.get("moderationInfo")
            result.update({
                "stars": int(stats.get("stars") or 0),
                "summary": (skill.get("summary") or "").strip(),
                "created_at": _iso_from_ms(skill.get("createdAt")),
                "updated_at": _iso_from_ms(skill.get("updatedAt")),
                "latest_version": latest.get("version") or "",
                "latest_version_at": _iso_from_ms(latest.get("createdAt")),
                "moderation_status": "flagged" if mod else "clean",
                "owner_handle": owner.get("handle") or "",
            })
    cache.set(key, result)
    return result


# ── Per-file last-commit dates (optional) ────────────────────────────────────

def fetch_last_commit_map(
    cache: DiskCache,
    work_dir: Path,
) -> dict[tuple[str, str], tuple[str, str]]:
    """
    Build (owner, slug) → (iso_date, sha) map by shallow-cloning openclaw/skills
    (blobless) and running one `git log --name-only` pass.

    Rationale: 8K GitHub API commits queries would consume the full 5K/hr rate
    limit. A --filter=blob:none clone is ~50-150 MB of history only, zero API cost.
    """
    repo_dir = work_dir / "openclaw-skills"
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    if repo_dir.exists() and (repo_dir / ".git").exists():
        _progress(f"  [git] existing clone at {repo_dir}, fetching...")
        subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "--depth=2147483647", "origin", "main"],
            check=False, capture_output=True, timeout=300,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "reset", "--hard", "origin/main"],
            check=False, capture_output=True, timeout=60,
        )
    else:
        _progress(f"  [git] cloning openclaw/skills (blobless) to {repo_dir}...")
        subprocess.run(
            ["git", "clone", "--filter=blob:none",
             "https://github.com/openclaw/skills.git", str(repo_dir)],
            check=True, capture_output=True, timeout=600,
        )

    head_sha = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()

    cache_key = f"commits_v1:{head_sha}"
    cached = cache.get(cache_key)
    if cached:
        _progress(f"  [cache] commit map for HEAD {head_sha[:8]} ({len(cached)} entries)")
        return {tuple(k.split("/", 1)): tuple(v) for k, v in cached.items()}

    _progress(f"  [git] scanning SKILL.md history at HEAD {head_sha[:8]}...")
    # Pathspec-filter to commits that touched SKILL.md — cuts ~170K commits to
    # ~80K and ~5 min. Using SKILL.md as the "last activity" proxy is fine for
    # the data product (readers care about skill-level freshness; README-only
    # touches without a SKILL.md bump almost never happen in this catalog).
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--name-only",
         "--pretty=format:COMMIT\t%H\t%cI", "--no-merges",
         "--", "skills/*/*/SKILL.md"],
        check=True, capture_output=True, text=True, timeout=900,
    )

    result: dict[tuple[str, str], tuple[str, str]] = {}
    current_sha = ""
    current_iso = ""
    for line in proc.stdout.splitlines():
        if line.startswith("COMMIT\t"):
            parts = line.split("\t")
            if len(parts) >= 3:
                current_sha, current_iso = parts[1], parts[2]
            continue
        if not line or not current_sha:
            continue
        # Path pattern: skills/<owner>/<slug>/SKILL.md
        if not line.startswith("skills/") or not line.endswith("/SKILL.md"):
            continue
        parts = line.split("/")
        if len(parts) < 4:
            continue
        key = (parts[1], parts[2])
        # git log is newest-first — first seen is most recent
        if key not in result:
            result[key] = (current_iso, current_sha)

    _progress(f"  [git] mapped {len(result)} (owner, slug) paths to last SKILL.md commit")
    cache.set(cache_key, {f"{k[0]}/{k[1]}": list(v) for k, v in result.items()})
    cache.save()
    return result


# ── Stage 3: Dependency resolution classification ─────────────────────────────

def classify_bin(bin_name: str, install_specs: list, bin_map: dict) -> str:
    """
    Classify how a required binary is resolved. Returns:
      'system'   — always in container PATH (python3, git, etc.)
      'static'   — entry in bin-name-map.json
      'dynamic'  — SKILL.md has a Linux-compatible install spec for this bin
      'brew'     — all install specs for this bin are brew (macOS only)
      'unmapped' — no install spec at all
    """
    if bin_name in SYSTEM_PROVIDED_BINS:
        return "system"
    if bin_name in bin_map:
        return "static"

    # Find install specs that cover this binary.
    # Specs either list bins explicitly or install one binary = their own name.
    # Guard against malformed SKILL.md where install specs are strings, not dicts.
    dict_specs = [s for s in install_specs if isinstance(s, dict)]
    relevant = [
        s for s in dict_specs
        if bin_name in _as_list(s.get("bins")) or not s.get("bins")
    ]

    if not relevant:
        return "unmapped"

    # Among relevant specs, check if any target Linux
    linux_specs = [
        s for s in relevant
        if not s.get("os") or "linux" in [x.lower() for x in _as_list(s.get("os"))]
    ]

    linux_kinds = {s.get("kind", "") for s in linux_specs}

    if linux_kinds & LINUX_COMPATIBLE_KINDS:
        return "dynamic"
    if not linux_specs or all(s.get("kind", "") == "brew" for s in relevant):
        return "brew"
    return "brew"  # non-Linux-compatible spec (shell, etc.)


def analyze_skill(s: dict, bin_map: dict) -> dict:
    """
    Enrich skill dict with dep analysis.

    coverage values:
      'no_deps'          no deps → works today
      'env_only'         only env deps → works after user sets API keys
      'fully_resolved'   all bins covered (may still need env keys)
      'brew_blocked'     ≥1 bin is brew-only (macOS-only skill)
      'unmapped_blocked' ≥1 bin has no install spec at all
    """
    parsed = s.get("parsed") or {}
    req_raw = parsed.get("requires") or {}
    req: dict = req_raw if isinstance(req_raw, dict) else {}
    inst_raw = parsed.get("install") or []
    install_specs: list = inst_raw if isinstance(inst_raw, list) else []

    bins: list[str] = req.get("bins") or []
    any_bins: list[str] = req.get("anyBins") or []
    env: list[str] = req.get("env") or []
    os_req: list[str] = req.get("os") or []
    all_bins = bins + any_bins

    bin_cls: dict[str, str] = {b: classify_bin(b, install_specs, bin_map) for b in all_bins}

    dict_specs = [i for i in install_specs if isinstance(i, dict)]
    install_kinds = sorted({str(i.get("kind") or "") for i in dict_specs if i.get("kind")})

    if not all_bins and not env:
        coverage = "no_deps"
    elif not all_bins:
        coverage = "env_only"
    else:
        unresolvable = [b for b, c in bin_cls.items() if c in ("brew", "unmapped")]
        if not unresolvable:
            coverage = "fully_resolved"
        elif all(bin_cls[b] == "brew" for b in unresolvable):
            coverage = "brew_blocked"
        else:
            coverage = "unmapped_blocked"

    return {
        **s,
        "bins_required": all_bins,
        "env_required": env,
        "os_required": os_req,
        "install_kinds": install_kinds,
        "bin_cls": bin_cls,
        "coverage": coverage,
    }


# ── Stage 4: Report ───────────────────────────────────────────────────────────

def _pct(n: int, d: int, width: int = 5) -> str:
    if d == 0:
        return " " * width + "  0.0%"
    return f"{n:{width}d}  ({n/d*100:5.1f}%)"


def _bar(n: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "░" * width
    filled = round(n / total * width)
    return "█" * filled + "░" * (width - filled)


def generate_report(skills: list[dict], limit: int, with_downloads: bool) -> list[str]:
    # Sort + slice
    if with_downloads:
        ranked = sorted(skills, key=lambda s: s.get("downloads") or 0, reverse=True)
    else:
        ranked = sorted(skills, key=lambda s: s["slug"])

    top = ranked[:limit]
    total = len(top)
    analyzed_total = sum(1 for s in top if s.get("has_skill_md"))

    # Segment
    has_md = [s for s in top if s.get("has_skill_md")]
    no_md = [s for s in top if not s.get("has_skill_md")]

    no_deps       = [s for s in has_md if s["coverage"] == "no_deps"]
    env_only      = [s for s in has_md if s["coverage"] == "env_only"]
    fully_resolved= [s for s in has_md if s["coverage"] == "fully_resolved"]
    brew_blocked  = [s for s in has_md if s["coverage"] == "brew_blocked"]
    unmapped_blk  = [s for s in has_md if s["coverage"] == "unmapped_blocked"]

    has_bins = [s for s in has_md if s["bins_required"]]
    mixed = [s for s in has_bins if s["env_required"]]

    # Per-bin frequency maps
    bin_coverage: dict[str, str] = {}  # first (authoritative) classification per bin
    bin_skill_count: dict[str, int] = defaultdict(int)
    for s in has_md:
        for b, c in (s.get("bin_cls") or {}).items():
            bin_coverage[b] = c
            bin_skill_count[b] += 1

    total_unique_bins = len(bin_coverage)
    bins_by_class: dict[str, int] = defaultdict(int)
    for c in bin_coverage.values():
        bins_by_class[c] += 1

    works_today = no_deps + env_only + fully_resolved

    lines: list[str] = []
    w = lines.append
    rank_note = f"ranked by downloads" if with_downloads else "alphabetical (use --with-downloads for download ranking)"

    w("=" * 64)
    w(f"  OpenClaw Catalog Coverage Report")
    w(f"  {total} skills analyzed ({rank_note})")
    w(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    w("=" * 64)

    # ── Stage 1 ───────────────────────────────────────────────────
    w("")
    w("STAGE 1 ─ DISCOVERY")
    w(f"  Skills in sample:          {total:6d}")
    w(f"  With SKILL.md:             {_pct(len(has_md), total)}")
    w(f"  Without SKILL.md (opaque): {_pct(len(no_md), total)}")
    w("")
    w(f"  {_bar(len(has_md), total)} {len(has_md)/total*100:.0f}% have declared deps")

    # ── Stage 2 ───────────────────────────────────────────────────
    md = len(has_md) or 1
    w("")
    w("STAGE 2 ─ DEPENDENCY DECLARATIONS  (skills with SKILL.md)")
    w(f"  No deps at all:       {_pct(len(no_deps),  md)}")
    w(f"  Env / API key only:   {_pct(len(env_only), md)}")
    w(f"  Has binary deps:      {_pct(len(has_bins), md)}")
    w(f"    of which also env:  {_pct(len(mixed),    len(has_bins) or 1)}")
    w("")
    for label, n in [("no deps", len(no_deps)), ("env only", len(env_only)),
                     ("bins", len(has_bins) - len(mixed)), ("bins+env", len(mixed))]:
        w(f"  {_bar(n, md)} {label}")

    # ── Stage 3 ───────────────────────────────────────────────────
    ub = total_unique_bins or 1
    w("")
    w("STAGE 3 ─ BIN RESOLUTION")
    w(f"  Unique bins required:      {total_unique_bins:6d}  (across all skills with deps)")
    w(f"  ├─ system PATH:            {_pct(bins_by_class['system'],  ub)}")
    w(f"  ├─ bin-name-map.json:      {_pct(bins_by_class['static'],  ub)}")
    w(f"  ├─ SKILL.md install spec:  {_pct(bins_by_class['dynamic'], ub)}")
    w(f"  ├─ brew-only (macOS):      {_pct(bins_by_class['brew'],    ub)}")
    w(f"  └─ unmapped (no spec):     {_pct(bins_by_class['unmapped'],ub)}")
    w("")
    resolvable_bins = bins_by_class["system"] + bins_by_class["static"] + bins_by_class["dynamic"]
    w(f"  Total resolvable:          {_pct(resolvable_bins, ub)}")
    w("")
    hb = len(has_bins) or 1
    w("  Skills with bin deps — outcome:")
    w(f"  ├─ All bins resolvable:    {_pct(len(fully_resolved), hb)}")
    w(f"  ├─ Blocked by brew:        {_pct(len(brew_blocked),   hb)}")
    w(f"  └─ Blocked by unmapped:    {_pct(len(unmapped_blk),   hb)}")

    # ── Stage 4 ───────────────────────────────────────────────────
    w("")
    w("STAGE 4 ─ OVERALL COVERAGE")
    w(f"  Works on Vessel today:     {_pct(len(works_today), total)}")
    w(f"    ├─ No deps needed:       {len(no_deps):6d}")
    w(f"    ├─ API keys only:        {len(env_only):6d}")
    w(f"    └─ Bins auto-resolved:   {len(fully_resolved):6d}")
    w(f"  Blocked — brew/macOS:      {_pct(len(brew_blocked), total)}")
    w(f"  Blocked — unmapped bins:   {_pct(len(unmapped_blk), total)}")
    w(f"  Unknown (no SKILL.md):     {_pct(len(no_md), total)}")
    w("")
    w(f"  {_bar(len(works_today), total)} {len(works_today)/total*100:.0f}% work today")

    # ── Stage 5: Quick wins ───────────────────────────────────────
    unmapped_bins = {
        b: bin_skill_count[b]
        for b, c in bin_coverage.items()
        if c == "unmapped"
    }
    brew_bins = {
        b: bin_skill_count[b]
        for b, c in bin_coverage.items()
        if c == "brew"
    }

    if unmapped_bins:
        w("")
        w("STAGE 5 ─ QUICK WINS  (unmapped bins — add to bin-name-map.json)")
        w("  Adding these would unblock the most skills:")
        for b, cnt in sorted(unmapped_bins.items(), key=lambda x: -x[1])[:20]:
            w(f"  {b:<24s}  blocks {cnt:4d}  skill(s)  {_bar(cnt, total, 10)}")

    if brew_bins:
        w("")
        w("  Brew-only bins (need Linux install spec in bin-name-map.json or SKILL.md):")
        for b, cnt in sorted(brew_bins.items(), key=lambda x: -x[1])[:20]:
            w(f"  {b:<24s}  blocks {cnt:4d}  skill(s)  {_bar(cnt, total, 10)}")

    w("")
    w("=" * 64)
    return lines


# ── CSV export ────────────────────────────────────────────────────────────────

BASE_COLUMNS = [
    "rank", "slug", "owner", "display_name", "downloads", "installs",
    "has_skill_md", "coverage",
    "bins_required", "env_required", "bin_classifications",
]

EXTENDED_COLUMNS = [
    "os_required", "stars", "summary",
    "created_at", "updated_at", "latest_version", "latest_version_at",
    "moderation_status", "owner_handle",
    "last_commit_at", "last_commit_sha", "install_kinds",
]


def write_csv(skills: list[dict], path: Path, extended: bool = False) -> None:
    fieldnames = BASE_COLUMNS + (EXTENDED_COLUMNS if extended else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, s in enumerate(skills, 1):
            row = {
                "rank": i,
                "slug": s["slug"],
                "owner": s.get("owner", ""),
                "display_name": s.get("display_name") or s["slug"],
                "downloads": s.get("downloads") or 0,
                "installs": s.get("installs") or 0,
                "has_skill_md": s.get("has_skill_md", False),
                "coverage": s.get("coverage", "unknown"),
                "bins_required": "|".join(s.get("bins_required") or []),
                "env_required": "|".join(s.get("env_required") or []),
                "bin_classifications": json.dumps(s.get("bin_cls") or {}),
            }
            if extended:
                row.update({
                    "os_required": "|".join(s.get("os_required") or []),
                    "stars": s.get("stars") or 0,
                    "summary": s.get("summary", ""),
                    "created_at": s.get("created_at", ""),
                    "updated_at": s.get("updated_at", ""),
                    "latest_version": s.get("latest_version", ""),
                    "latest_version_at": s.get("latest_version_at", ""),
                    "moderation_status": s.get("moderation_status", "unknown"),
                    "owner_handle": s.get("owner_handle", ""),
                    "last_commit_at": s.get("last_commit_at", ""),
                    "last_commit_sha": s.get("last_commit_sha", ""),
                    "install_kinds": "|".join(s.get("install_kinds") or []),
                })
            writer.writerow(row)


# ── Progress helpers ──────────────────────────────────────────────────────────

def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


EXTENDED_DEFAULTS = {
    "stars": 0,
    "summary": "",
    "created_at": "",
    "updated_at": "",
    "latest_version": "",
    "latest_version_at": "",
    "moderation_status": "unknown",
    "owner_handle": "",
}


def _enrich_batch(
    skills: list[dict],
    cache: DiskCache,
    workers: int,
    with_downloads: bool,
    with_metadata: bool = False,
    commit_map: dict[tuple[str, str], tuple[str, str]] | None = None,
) -> list[dict]:
    total = len(skills)
    done = 0
    results: list[dict] = []
    want_clawhub = with_downloads or with_metadata

    def enrich(s: dict) -> dict:
        owner, slug = s["owner"], s["slug"]
        content = fetch_skill_md(owner, slug, cache)
        parsed = parse_skill_md(content) if content else {}
        out: dict = {
            "owner": owner,
            "slug": slug,
            "has_skill_md": content is not None,
            "parsed": parsed,
            "downloads": 0,
            "installs": 0,
            "display_name": slug,
        }
        if with_metadata:
            out.update(EXTENDED_DEFAULTS)
        if want_clawhub:
            meta = fetch_clawhub_meta(slug, cache, extended=with_metadata)
            out.update({
                "downloads": meta.get("downloads", 0),
                "installs": meta.get("installs", 0),
                "display_name": meta.get("display_name", slug),
            })
            if with_metadata:
                for field in EXTENDED_DEFAULTS:
                    if field in meta:
                        out[field] = meta[field]
        if commit_map is not None:
            iso, sha = commit_map.get((owner, slug), ("", ""))
            out["last_commit_at"] = iso
            out["last_commit_sha"] = sha
        return out

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(enrich, s): s for s in skills}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                s = futures[fut]
                results.append({"owner": s["owner"], "slug": s["slug"],
                                 "has_skill_md": False, "parsed": {}})
            done += 1
            if done % 200 == 0 or done == total:
                _progress(f"  {done}/{total} fetched...")
                cache.save()  # periodic save

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Analyze OpenClaw catalog dependency coverage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--limit", type=int, default=1000,
                    help="Number of skills to include in the report (default 1000)")
    ap.add_argument("--all", dest="all_skills", action="store_true",
                    help="Report on all discovered skills (overrides --limit)")
    ap.add_argument("--with-downloads", action="store_true",
                    help="Fetch ClawHub download counts and rank by downloads (slower first run)")
    ap.add_argument("--with-metadata", action="store_true",
                    help="Fetch extended ClawHub metadata (tags, license, stars, summary, timestamps, moderation). Implies --with-downloads.")
    ap.add_argument("--with-commits", action="store_true",
                    help="Clone openclaw/skills and attach last-commit dates per skill (adds ~2-3 min, requires git)")
    ap.add_argument("--work-dir", type=Path, default=None,
                    help="Working directory for git clone (default: <output>/repos/)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore existing cache and re-fetch everything")
    ap.add_argument("--workers", type=int, default=25,
                    help="Parallel HTTP workers (default 25)")
    ap.add_argument("--output", type=Path, default=OUTPUT_DIR,
                    help="Output directory (default: packages/infra/scripts/coverage-output/)")
    ap.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN"),
                    help="GitHub token for higher API rate limits (or set GITHUB_TOKEN env var)")
    args = ap.parse_args()

    # --with-metadata implies --with-downloads
    if args.with_metadata:
        args.with_downloads = True

    output_dir: Path = args.output
    cache = DiskCache(output_dir / "cache.json", enabled=not args.no_cache)

    if not BIN_MAP_PATH.exists():
        _progress(f"ERROR: bin-name-map.json not found at {BIN_MAP_PATH}")
        return 1
    bin_map: dict = json.loads(BIN_MAP_PATH.read_text())

    _progress(f"\n[1/4] Discovering skills in openclaw/skills catalog...")
    all_skills = fetch_all_skills(cache, args.github_token)
    if not all_skills:
        _progress("ERROR: no skills found — check network / GitHub token")
        return 1

    commit_map: dict[tuple[str, str], tuple[str, str]] | None = None
    if args.with_commits:
        work_dir = args.work_dir or (output_dir / "repos")
        _progress(f"\n[1b/4] Building last-commit map via git clone...")
        try:
            commit_map = fetch_last_commit_map(cache, work_dir)
        except subprocess.CalledProcessError as e:
            _progress(f"ERROR: git operation failed — {e.stderr.decode(errors='replace') if e.stderr else e}")
            return 1
        except FileNotFoundError:
            _progress("ERROR: git not found on PATH — install git or omit --with-commits")
            return 1

    _progress(f"\n[2/4] Fetching SKILL.md{' + ClawHub metadata' if args.with_downloads else ''}"
              f"{' (extended)' if args.with_metadata else ''} "
              f"for {len(all_skills)} skills ({args.workers} workers)...")
    enriched = _enrich_batch(
        all_skills, cache, args.workers,
        args.with_downloads,
        with_metadata=args.with_metadata,
        commit_map=commit_map,
    )
    cache.save()

    _progress(f"\n[3/4] Analyzing {len(enriched)} skills against {len(bin_map)} bin-map entries...")
    analyzed = [analyze_skill(s, bin_map) for s in enriched]

    limit = len(analyzed) if args.all_skills else args.limit
    _progress(f"\n[4/4] Generating report (top {limit})...\n")

    lines = generate_report(analyzed, limit, args.with_downloads)
    report_text = "\n".join(lines)
    print(report_text)

    # Write outputs
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"report-{date_str}.txt"
    report_path.write_text(report_text)

    # Sort same way as generate_report for CSV
    if args.with_downloads:
        ordered = sorted(analyzed, key=lambda s: s.get("downloads") or 0, reverse=True)[:limit]
    else:
        ordered = sorted(analyzed, key=lambda s: s["slug"])[:limit]

    csv_path = output_dir / f"skills-{date_str}.csv"
    write_csv(ordered, csv_path, extended=args.with_metadata)

    _progress(f"\nReport: {report_path}")
    _progress(f"CSV:    {csv_path}")
    _progress(f"Cache:  {output_dir / 'cache.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
