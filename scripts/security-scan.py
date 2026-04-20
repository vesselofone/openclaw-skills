#!/usr/bin/env python3
"""
security-scan.py — First-party security scan of the OpenClaw skills catalog.

Reads data/latest.csv and produces per-skill security verdicts from three
signal layers:

  1. SKILL.md static pattern analysis  — reuses catalog-coverage.py cache
  2. ClawHub registry signals           — LLM verdict, VirusTotal, moderation
  3. OpenClaw CVE tracker               — GHSA advisory mentions

Output (data/security-scan-YYYY-MM/):
  findings.csv   — one row per skill: slug, verdict, severity, pattern_flags,
                   clawhub_verdict, vt_analysis, moderation_status, cve_ids, evidence
  summary.json   — aggregate counts, advisories_per_1000, scan metadata

Usage:
  python3 scripts/security-scan.py
  python3 scripts/security-scan.py --limit 100   # test run
  python3 scripts/security-scan.py --no-cache
  python3 scripts/security-scan.py --output-dir data/security-scan-custom

Reproduce:
  export GITHUB_TOKEN=ghp_...   # optional, avoids GitHub rate limits on SKILL.md
  python3 scripts/security-scan.py --no-cache
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"

# ── Constants ─────────────────────────────────────────────────────────────────

CLAWHUB_CONVEX = "https://wry-manatee-359.convex.cloud"
OPENCLAW_SKILLS_RAW = "https://raw.githubusercontent.com/openclaw/skills/main/skills"
CVE_TRACKER_URL = "https://raw.githubusercontent.com/jgamblin/OpenClawCVEs/main/ghsa-advisories.json"

# SKILL.md security patterns — mirrors skill-check/lib/scoring.ts
# base64-command and piped-to-shell are ClawHavoc attack vectors → dangerous.
# All other flags → caution.
SKILL_MD_PATTERNS: list[dict] = [
    {
        "flag": "base64-command",
        "verdict": "dangerous",
        "severity": "critical",
        "description": "Base64-encoded command piped to shell — primary ClawHavoc attack vector",
        "re": re.compile(r"base64\s*-d.*?\|.*?(?:sh|bash)", re.IGNORECASE | re.DOTALL),
    },
    {
        "flag": "piped-to-shell",
        "verdict": "dangerous",
        "severity": "critical",
        "description": "Remote fetch piped directly to shell without review",
        "re": re.compile(r"(?:curl|wget)\s+\S+.*?\|.*?(?:sh|bash)", re.IGNORECASE | re.DOTALL),
    },
    {
        "flag": "password-prompt",
        "verdict": "caution",
        "severity": "medium",
        "description": "Social engineering: password/sudo prompt in install instructions",
        "re": re.compile(r"(?:enter\s+(?:your\s+)?password|sudo\s+password)", re.IGNORECASE),
    },
    {
        "flag": "non-registry-url",
        "verdict": "caution",
        "severity": "medium",
        "description": "Binary download from non-standard registry domain inside a shell command",
        # Only flag URLs that appear directly in shell download commands, not in plain text.
        # Anchored to curl/wget/sh context to avoid false positives in descriptions.
        "re": re.compile(
            r"(?:curl|wget)\s+(?:-\S+\s+)*"
            r"https?://(?!(?:clawhub\.ai|openclaw\.ai|github\.com|githubusercontent\.com"
            r"|npmjs\.com|pypi\.org|pkg\.go\.dev|registry\.npmjs\.org|apt\.get|deb\.nodesource\.com))"
            r"[\w\-\.]+\.[a-z]{2,}/\S+",
            re.IGNORECASE,
        ),
    },
]

# Verdict ordering — higher index is more severe
_VERDICT_ORDER = ["unknown", "safe", "caution", "dangerous"]
_SEVERITY_ORDER = ["unknown", "none", "low", "medium", "high", "critical"]


def _verdict_max(a: str, b: str) -> str:
    ia = _VERDICT_ORDER.index(a) if a in _VERDICT_ORDER else 0
    ib = _VERDICT_ORDER.index(b) if b in _VERDICT_ORDER else 0
    return _VERDICT_ORDER[max(ia, ib)]


def _severity_max(a: str, b: str) -> str:
    ia = _SEVERITY_ORDER.index(a) if a in _SEVERITY_ORDER else 0
    ib = _SEVERITY_ORDER.index(b) if b in _SEVERITY_ORDER else 0
    return _SEVERITY_ORDER[max(ia, ib)]


# ── Cache ─────────────────────────────────────────────────────────────────────

class DiskCache:
    """JSON file cache — survives between runs. read_only skips writes."""

    def __init__(self, path: Path, enabled: bool = True, read_only: bool = False) -> None:
        self.path = path
        self.enabled = enabled
        self.read_only = read_only
        self._data: dict[str, Any] = {}
        if enabled and path.exists():
            try:
                self._data = json.loads(path.read_text())
            except Exception:
                pass

    def get(self, key: str) -> Any:
        return self._data.get(key) if self.enabled else None

    def set(self, key: str, value: Any) -> None:
        if self.enabled and not self.read_only:
            self._data[key] = value

    def save(self) -> None:
        if not self.enabled or self.read_only:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data))


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _ua_headers(github_token: str | None = None) -> dict[str, str]:
    h = {"User-Agent": "VesselSecurityScan/1.0"}
    if github_token:
        h["Authorization"] = f"token {github_token}"
    return h


def http_get(url: str, timeout: int = 15, headers: dict | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "VesselSecurityScan/1.0"})
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
    data = json.dumps({"path": path, "format": "json", "args": args}).encode()
    req = urllib.request.Request(
        f"{CLAWHUB_CONVEX}/api/query",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "VesselSecurityScan/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            return result["value"] if result.get("status") == "success" else None
    except Exception:
        return None


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── Layer 1: SKILL.md pattern analysis ───────────────────────────────────────

def get_skill_md(
    owner: str,
    slug: str,
    catalog_cache: DiskCache,
    sec_cache: DiskCache,
    github_token: str | None,
) -> str | None:
    """Return SKILL.md content. Tries caches before fetching."""
    key = f"skillmd:{owner}/{slug}"
    # Catalog cache (populated by catalog-coverage.py) — free hit
    content = catalog_cache.get(key)
    if content is not None:
        return content or None
    # Security cache
    content = sec_cache.get(key)
    if content is not None:
        return content or None
    # Fresh fetch
    url = f"{OPENCLAW_SKILLS_RAW}/{owner}/{slug}/SKILL.md"
    req = urllib.request.Request(url, headers=_ua_headers(github_token))
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode(errors="replace")
            sec_cache.set(key, content)
            return content
    except urllib.error.HTTPError:
        sec_cache.set(key, "")
        return None
    except Exception:
        return None


def scan_skill_md(content: str | None) -> list[dict]:
    """Run SKILL.md pattern analysis. Returns list of matched pattern dicts."""
    if not content:
        return []
    return [p for p in SKILL_MD_PATTERNS if p["re"].search(content)]


# ── Layer 2: ClawHub registry signals ────────────────────────────────────────

def fetch_clawhub_security(slug: str, cache: DiskCache) -> dict:
    """Fetch ClawHub LLM verdict, VirusTotal analysis, and moderation flags."""
    key = f"sec_clawhub_v1:{slug}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    value = convex_query("skills:getBySlug", {"slug": slug})
    if value is None:
        result: dict = {"status": "not-found", "verdict": "unknown", "evidence": []}
        cache.set(key, result)
        return result

    skill = value.get("skill") or {}
    lv = value.get("latestVersion") or {}
    llm = lv.get("llmAnalysis") or {}
    vt_raw = lv.get("vtAnalysis") or {}
    mod = value.get("moderationInfo")

    verdict = "unknown"
    evidence: list[str] = []

    # LLM verdict
    llm_verdict = (llm.get("verdict") or "").lower()
    llm_map = {"benign": "safe", "clean": "safe", "suspicious": "caution", "malicious": "dangerous"}
    if llm_verdict in llm_map:
        verdict = _verdict_max(verdict, llm_map[llm_verdict])
        evidence.append(f"LLM analysis: {llm_verdict}")

    # VirusTotal — the "analysis" field is a free-text LLM description, not a
    # structured verdict (e.g. it contains phrases like "no evidence of malicious").
    # Include as evidence text only; do not use for verdict determination.
    vt_str = str(vt_raw.get("analysis") or "").strip()
    if vt_str:
        evidence.append(f"VirusTotal: {vt_str[:80]}")

    # Moderation overrides (highest priority)
    moderation_status = "clean"
    if mod:
        moderation_status = "flagged"
        if mod.get("isMalwareBlocked") or mod.get("isRemoved"):
            verdict = "dangerous"
            label = "malware-blocked" if mod.get("isMalwareBlocked") else "removed"
            evidence.append(f"ClawHub moderation: {label}")
        elif mod.get("isSuspicious"):
            verdict = _verdict_max(verdict, "caution")
            reasons = ", ".join(mod.get("reasonCodes") or [])
            evidence.append(f"ClawHub flagged suspicious ({reasons})")

    result = {
        "status": "found" if skill else "not-found",
        "verdict": verdict,
        "evidence": evidence,
        "llm_verdict": llm_verdict,
        "vt_analysis": vt_str[:120],
        "moderation_status": moderation_status,
    }
    cache.set(key, result)
    return result


# ── Layer 3: CVE tracker ──────────────────────────────────────────────────────

def load_advisories(cache: DiskCache) -> list[dict]:
    """Fetch and cache the GHSA advisory list from jgamblin/OpenClawCVEs."""
    key = "ghsa_advisories_v1"
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = http_get(CVE_TRACKER_URL, timeout=20)
    advisories = data if isinstance(data, list) else []
    cache.set(key, advisories)
    return advisories


def check_cve_mentions(slug: str, owner: str, advisories: list[dict]) -> list[dict]:
    """
    Return advisories that mention this skill's slug or owner.
    Searches title and packages[] fields.
    """
    slug_l = slug.lower()
    owner_l = owner.lower()
    matches = []
    for adv in advisories:
        title = (adv.get("title") or "").lower()
        packages = [str(p).lower() for p in (adv.get("packages") or [])]
        if slug_l in title or owner_l in title or any(slug_l in p for p in packages):
            matches.append({
                "ghsa_id": adv.get("ghsa_id") or "",
                "cve_id": adv.get("cve_id") or "",
                "severity": adv.get("severity") or "unknown",
                "title": (adv.get("title") or "")[:120],
            })
    return matches


# ── Combined verdict ──────────────────────────────────────────────────────────

def compute_verdict(
    pattern_matches: list[dict],
    clawhub: dict,
    cve_matches: list[dict],
) -> tuple[str, str]:
    """
    Compute final (verdict, severity) from all three signal layers.
    Mirrors scoring.ts logic:
      - base64-command / piped-to-shell → dangerous / critical
      - all other pattern flags → caution
      - clawhub verdict → passed through
      - CVE mentions → caution, severity from advisory
    """
    verdict = "unknown"
    severity = "unknown"

    # Pattern flags
    for p in pattern_matches:
        verdict = _verdict_max(verdict, p["verdict"])
        severity = _severity_max(severity, p["severity"])

    # ClawHub
    ch_verdict = clawhub.get("verdict", "unknown")
    verdict = _verdict_max(verdict, ch_verdict)

    # CVE mentions
    cve_sev_map = {"critical": "critical", "high": "high", "moderate": "medium", "low": "low"}
    for adv in cve_matches:
        verdict = _verdict_max(verdict, "caution")
        severity = _severity_max(severity, cve_sev_map.get((adv.get("severity") or "").lower(), "medium"))

    # Default severity when we have a verdict but no severity signal
    if verdict != "unknown" and severity == "unknown":
        severity = "low"

    return verdict, severity


# ── Per-skill scan ────────────────────────────────────────────────────────────

def scan_skill(
    row: dict,
    catalog_cache: DiskCache,
    sec_cache: DiskCache,
    advisories: list[dict],
    github_token: str | None,
) -> dict:
    slug = row["slug"]
    owner = row["owner"]

    # Layer 1
    content = get_skill_md(owner, slug, catalog_cache, sec_cache, github_token)
    pattern_matches = scan_skill_md(content)

    # Layer 2
    clawhub = fetch_clawhub_security(slug, sec_cache)

    # Layer 3
    cve_matches = check_cve_mentions(slug, owner, advisories)

    # Combined
    verdict, severity = compute_verdict(pattern_matches, clawhub, cve_matches)

    # Evidence
    evidence: list[str] = []
    for p in pattern_matches:
        evidence.append(f"pattern:{p['flag']}({p['severity']})")
    evidence.extend(clawhub.get("evidence") or [])
    for adv in cve_matches:
        evidence.append(f"{adv['ghsa_id'] or adv['cve_id']}:{adv['severity']}")

    return {
        "slug": slug,
        "owner": owner,
        "verdict": verdict,
        "severity": severity,
        "pattern_flags": json.dumps([p["flag"] for p in pattern_matches]),
        "clawhub_verdict": clawhub.get("llm_verdict", ""),
        "vt_analysis": clawhub.get("vt_analysis", ""),
        "moderation_status": clawhub.get("moderation_status", "unknown"),
        "cve_ids": "|".join(
            adv["ghsa_id"] or adv["cve_id"] for adv in cve_matches if adv["ghsa_id"] or adv["cve_id"]
        ),
        "cve_severities": "|".join(adv["severity"] for adv in cve_matches),
        "evidence": "|".join(evidence),
    }


# ── CSV / JSON output ─────────────────────────────────────────────────────────

FINDINGS_COLUMNS = [
    "slug", "owner", "verdict", "severity",
    "pattern_flags",
    "clawhub_verdict", "vt_analysis", "moderation_status",
    "cve_ids", "cve_severities",
    "evidence",
]

_VERDICT_SORT = {"dangerous": 0, "caution": 1, "safe": 2, "unknown": 3}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    default_out = DATA_DIR / f"security-scan-{today}"

    ap = argparse.ArgumentParser(
        description="First-party security scan of the OpenClaw skills catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--input", type=Path, default=DATA_DIR / "latest.csv",
                    help="Catalog CSV to scan (default: data/latest.csv)")
    ap.add_argument("--output-dir", type=Path, default=default_out,
                    help=f"Output directory (default: {default_out})")
    ap.add_argument("--catalog-cache", type=Path,
                    default=SCRIPT_DIR / "coverage-output" / "cache.json",
                    help="Catalog cache path — reuses SKILL.md content from catalog-coverage.py")
    ap.add_argument("--limit", type=int, default=0,
                    help="Scan only first N skills (0 = all; use for test runs)")
    ap.add_argument("--workers", type=int, default=10,
                    help="Parallel HTTP workers (default 10; Convex API is tolerant)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore existing security cache and re-fetch all signals")
    ap.add_argument("--github-token", default=os.getenv("GITHUB_TOKEN"),
                    help="GitHub token for SKILL.md fetches (or GITHUB_TOKEN env var)")
    args = ap.parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog_cache = DiskCache(args.catalog_cache, enabled=args.catalog_cache.exists(), read_only=True)
    sec_cache = DiskCache(output_dir / "cache.json", enabled=not args.no_cache)

    if not args.input.exists():
        _progress(f"ERROR: input not found at {args.input}")
        return 1

    with args.input.open(newline="", encoding="utf-8") as f:
        skills = list(csv.DictReader(f))

    if args.limit:
        skills = skills[:args.limit]

    cache_note = "warm" if catalog_cache.enabled and catalog_cache._data else "cold"
    _progress(f"\n[1/4] {len(skills)} skills loaded from {args.input.name} "
              f"(catalog cache: {cache_note})")

    _progress(f"\n[2/4] Loading OpenClaw CVE tracker...")
    advisories = load_advisories(sec_cache)
    sec_cache.save()
    _progress(f"  {len(advisories)} GHSA advisories")

    _progress(f"\n[3/4] Scanning {len(skills)} skills ({args.workers} workers)...")
    findings: list[dict] = []
    done = 0
    total = len(skills)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(scan_skill, row, catalog_cache, sec_cache, advisories, args.github_token): row
            for row in skills
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                findings.append(fut.result())
            except Exception as exc:
                row = futures[fut]
                findings.append({
                    "slug": row["slug"], "owner": row.get("owner", ""),
                    "verdict": "unknown", "severity": "unknown",
                    "pattern_flags": "[]", "clawhub_verdict": "",
                    "vt_analysis": "", "moderation_status": "unknown",
                    "cve_ids": "", "cve_severities": "",
                    "evidence": f"scan-error:{exc}",
                })
            done += 1
            if done % 500 == 0 or done == total:
                _progress(f"  {done}/{total} scanned...")
                sec_cache.save()

    sec_cache.save()

    # Sort by verdict severity descending, then slug
    findings.sort(key=lambda r: (_VERDICT_SORT.get(r["verdict"], 3), r["slug"]))

    _progress(f"\n[4/4] Writing outputs to {output_dir}...")

    findings_path = output_dir / "findings.csv"
    with findings_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FINDINGS_COLUMNS)
        writer.writeheader()
        writer.writerows(findings)

    # Aggregates
    by_verdict: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    pattern_counts: dict[str, int] = defaultdict(int)
    cve_sev_counts: dict[str, int] = defaultdict(int)
    skills_with_cve = 0
    skills_dangerous = []

    for r in findings:
        by_verdict[r["verdict"]] += 1
        by_severity[r["severity"]] += 1
        for flag in (json.loads(r["pattern_flags"] or "[]")):
            pattern_counts[flag] += 1
        if r["cve_ids"]:
            skills_with_cve += 1
            for sev in (r["cve_severities"] or "").split("|"):
                if sev:
                    cve_sev_counts[sev] += 1
        if r["verdict"] == "dangerous":
            skills_dangerous.append({"slug": r["slug"], "owner": r["owner"], "evidence": r["evidence"]})

    per_1000 = round(len(advisories) / (total / 1000), 1) if total else 0

    summary = {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "input": str(args.input),
        "total_skills_scanned": total,
        "by_verdict": dict(by_verdict),
        "by_severity": dict(by_severity),
        "pattern_flag_counts": dict(pattern_counts),
        "skills_with_cve_mention": skills_with_cve,
        "cve_severity_distribution": dict(cve_sev_counts),
        "ghsa_advisories_total": len(advisories),
        "advisories_per_1000_skills": per_1000,
        "top_dangerous": skills_dangerous[:20],
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # Print summary
    _progress(f"""
Results:
  dangerous : {by_verdict.get('dangerous', 0):6d}  ({by_verdict.get('dangerous', 0)/total*100:.1f}%)
  caution   : {by_verdict.get('caution', 0):6d}  ({by_verdict.get('caution', 0)/total*100:.1f}%)
  safe      : {by_verdict.get('safe', 0):6d}  ({by_verdict.get('safe', 0)/total*100:.1f}%)
  unknown   : {by_verdict.get('unknown', 0):6d}  ({by_verdict.get('unknown', 0)/total*100:.1f}%)

Pattern flags:
  base64-command   : {pattern_counts.get('base64-command', 0)}
  piped-to-shell   : {pattern_counts.get('piped-to-shell', 0)}
  password-prompt  : {pattern_counts.get('password-prompt', 0)}
  non-registry-url : {pattern_counts.get('non-registry-url', 0)}

CVE mentions : {skills_with_cve} skills
Advisories   : {len(advisories)} total → {per_1000} per 1,000 skills

Findings : {findings_path}
Summary  : {summary_path}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
