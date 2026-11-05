#!/usr/bin/env python3
"""Discover runtime GitHub sources; Python stdlib and authenticated gh suffice.

Exit codes: 0 complete, 1 failed, 2 partial (also argparse usage errors).
Only --output writes a file; no gym state or question bank is read or changed.
Awesome counts describe sampled lists, never all of GitHub. README text is data
only: it is not emitted, executed, or used as instructions.
"""

import argparse
import base64
import binascii
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

FIELDS = "fullName,description,stargazersCount,url,updatedAt"
MAX_LISTS = 6
MAX_LINK_LOOKUPS = 12
MAX_README_BYTES = 512 * 1024
MAX_REQUESTS = 3 + MAX_LISTS + MAX_LINK_LOOKUPS
REPO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+\Z")
GITHUB_LINK = re.compile(
    r"https?://(?:www\.)?github\.com/"
    r"([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)", re.IGNORECASE
)
RESERVED = {"topics", "collections", "features", "settings", "marketplace",
            "orgs", "users", "search", "sponsors", "login", "about"}


class DiscoveryError(Exception):
    pass


def gh_json(args):
    """Do not relay gh stderr: it could contain credentials or private data."""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=30,
            check=False, env={**os.environ, "GH_PROMPT_DISABLED": "1"},
        )
    except FileNotFoundError:
        raise DiscoveryError("gh_not_installed") from None
    except subprocess.TimeoutExpired:
        raise DiscoveryError("timeout") from None
    except (OSError, UnicodeError):
        raise DiscoveryError("process_error") from None
    if result.returncode:
        message = result.stderr.lower()
        if any(x in message for x in ("rate limit", "secondary rate", "429")):
            reason = "rate_limited"
        elif any(x in message for x in ("auth", "401", "403", "token", "login")):
            reason = "authentication_or_access_denied"
        elif "404" in message or "not found" in message:
            reason = "not_found"
        else:
            reason = "network_or_command_error"
        raise DiscoveryError(reason)
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError):
        raise DiscoveryError("invalid_json_response") from None


def search_args(topic, stars, limit, language=None, awesome_mode=None):
    args = ["search", "repos", "--visibility", "public", "--stars", f">={stars}", "--archived=false",
            "--sort", "stars", "--order", "desc", "--limit", str(limit),
            "--json", FIELDS]
    if language:
        args += ["--language", language]
    if awesome_mode == "topic":
        args += ["--topic", "awesome"]
    elif awesome_mode == "name":
        topic = f"{topic} awesome in:name"
    # The option terminator prevents plain user input from becoming CLI options.
    return [*args, "--", topic]


def normalize_repo(item):
    if not isinstance(item, dict):
        raise DiscoveryError("invalid_repository_response")
    name = item.get("fullName", item.get("full_name"))
    stars = item.get("stargazersCount", item.get("stargazers_count"))
    if not isinstance(name, str) or not REPO_NAME.fullmatch(name):
        raise DiscoveryError("invalid_repository_response")
    if not isinstance(stars, int) or isinstance(stars, bool) or stars < 0:
        raise DiscoveryError("invalid_repository_response")
    return {"full_name": name, "url": f"https://github.com/{name}",
            "description": item.get("description"), "stars": stars,
            "updated_at": item.get("updatedAt", item.get("updated_at"))}


def readme_links(data):
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        raise DiscoveryError("unsupported_readme_response")
    content = data.get("content")
    size = data.get("size")
    if not isinstance(content, str) or not isinstance(size, int):
        raise DiscoveryError("invalid_readme_response")
    if size > MAX_README_BYTES or len(content) > MAX_README_BYTES * 1.5:
        raise DiscoveryError("readme_exceeds_size_bound")
    try:
        raw = base64.b64decode("".join(content.split()), validate=True)
    except (ValueError, binascii.Error):
        raise DiscoveryError("invalid_readme_base64") from None
    if len(raw) > MAX_README_BYTES:
        raise DiscoveryError("readme_exceeds_size_bound")
    links = set()
    for match in GITHUB_LINK.finditer(raw.decode("utf-8", errors="replace")):
        name = match.group(1).removesuffix(".git")
        if name.split("/", 1)[0].lower() not in RESERVED:
            links.add(name.lower())
    return links


def next_commands(name):
    return [shlex.join(["gh", "search", "issues", query, "--repo", name,
                        "--limit", "10", "--json", "title,url,state"])
            for query in ("RFC", "ADR", "design")]


def discover(args):
    errors, candidates, lists, evidence = [], {}, {}, {}
    requests = 0

    def request(command, operation, repository=None):
        nonlocal requests
        requests += 1
        try:
            return gh_json(command)
        except DiscoveryError as exc:
            errors.append({"operation": operation, "repository": repository,
                           "reason": str(exc)})
            return None

    def search(command, operation):
        payload = request(command, operation)
        if payload is None:
            return []
        if not isinstance(payload, list):
            errors.append({"operation": operation, "reason": "invalid_search_response"})
            return []
        rows = []
        for item in payload:
            try:
                rows.append(normalize_repo(item))
            except DiscoveryError as exc:
                errors.append({"operation": operation, "reason": str(exc)})
        return rows

    for repo in search(search_args(args.topic, args.min_stars, args.limit,
                                   args.language), "candidate_search"):
        if repo["stars"] >= args.min_stars:
            repo["discovery_signals"] = ["repository_search"]
            candidates[repo["full_name"].lower()] = repo

    # Awesome list search has its own lower floor; project star floor still applies.
    for mode in ("topic", "name"):
        for repo in search(search_args(args.topic, 100, MAX_LISTS,
                                       awesome_mode=mode), f"awesome_search_{mode}"):
            lists[repo["full_name"].lower()] = repo
    sampled = sorted(lists.values(), key=lambda r: (-r["stars"], r["full_name"]))[:MAX_LISTS]
    list_results = []
    for repo in sampled:
        name = repo["full_name"]
        data = request(["api", f"repos/{name}/readme"], "awesome_readme", name)
        record = {"full_name": name, "url": repo["url"], "stars": repo["stars"],
                  "readme_url": repo["url"] + "/blob/HEAD/README.md", "status": "unavailable"}
        if data is not None:
            try:
                links = readme_links(data)
                # Use API metadata for nonstandard README names, never README instructions.
                url = data.get("html_url")
                if isinstance(url, str) and url.startswith(repo["url"] + "/blob/"):
                    record["readme_url"] = url
                record["status"] = "read"
                for linked in links:
                    if linked != name.lower():
                        evidence.setdefault(linked, {})[name.lower()] = record["readme_url"]
            except DiscoveryError as exc:
                errors.append({"operation": "awesome_readme", "repository": name,
                               "reason": str(exc)})
        list_results.append(record)

    # Expand candidates from actual README links, using bounded metadata lookups.
    linked_names = sorted(evidence, key=lambda name: (-len(evidence[name]), name))
    expansion = [name for name in linked_names if name not in candidates and name not in lists]
    for name in expansion[:MAX_LINK_LOOKUPS]:
        data = request(["api", f"repos/{name}"], "linked_repository", name)
        if data is None:
            continue
        try:
            repo = normalize_repo(data)
            if data.get("private") is True or data.get("archived") is not False or data.get("disabled") is True:
                continue
            if repo["stars"] < args.min_stars:
                continue
            if args.language and str(data.get("language", "")).casefold() != args.language.casefold():
                continue
            canonical = repo["full_name"].lower()
            # Preserve evidence when a GitHub redirect resolves a renamed repository.
            evidence.setdefault(canonical, {}).update(evidence[name])
            if canonical in candidates:
                continue
            repo["discovery_signals"] = ["awesome_readme_link"]
            candidates[canonical] = repo
        except DiscoveryError as exc:
            errors.append({"operation": "linked_repository", "repository": name,
                           "reason": str(exc)})

    read_count = sum(item["status"] == "read" for item in list_results)
    search_failed = any(e["operation"].startswith("awesome_search") for e in errors)
    coverage = ("unknown" if not read_count else
                "partial" if search_failed or read_count != len(sampled) else "complete")
    ranked = sorted(candidates.values(), key=lambda r: (-r["stars"], r["full_name"]))[:args.limit]
    for repo in ranked:
        mentions = evidence.get(repo["full_name"].lower(), {})
        if mentions and "awesome_readme_link" not in repo["discovery_signals"]:
            repo["discovery_signals"].append("awesome_readme_link")
        repo["awesome_mentions"] = {
            "status": coverage, "distinct_count": len(mentions) if coverage == "complete" else None,
            "observed_count": len(mentions), "evidence_urls": sorted(mentions.values()),
        }
        repo["next_search_commands"] = next_commands(repo["full_name"])

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if errors and ranked else "error" if errors else "ok",
        "query": {"topic": args.topic, "min_stars": args.min_stars,
                  "limit": args.limit, "language": args.language},
        "request_count": requests, "request_budget": MAX_REQUESTS,
        "candidates": ranked, "awesome_lists": list_results,
        "awesome_coverage": coverage,
        "linked_candidates_considered": min(len(expansion), MAX_LINK_LOOKUPS),
        "linked_candidates_not_checked": max(0, len(expansion) - MAX_LINK_LOOKUPS),
        "errors": errors,
        "notes": [
            "Live GitHub discovery; no fixed question bank and no gym state changes.",
            "Awesome mentions are a popularity discovery signal, not a quality endorsement.",
            "Counts cover only sampled relevant lists (minimum 100 stars); they are not global counts.",
            "Unknown/partial coverage has null distinct_count; observed_count is a lower bound.",
            "README links can be incidental references; inclusion does not prove a curated recommendation.",
            "Search and expansion are bounded and not exhaustive. Issue commands are suggestions only.",
        ],
    }


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def limit_value(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return min(number, 20)


def plain_text(value):
    if not value.strip() or any(ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError("must be nonempty text without control characters")
    return value.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", type=plain_text, default="architecture",
                        help="repository search text (default: architecture)")
    parser.add_argument("--min-stars", type=nonnegative, default=1000)
    parser.add_argument("--limit", type=limit_value, default=8,
                        help="maximum output candidates, capped at 20 (default: 8)")
    parser.add_argument("--language", type=plain_text)
    parser.add_argument("--output", type=Path, help="also write JSON atomically to this path")
    args = parser.parse_args(argv)
    report = discover(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                             dir=args.output.parent, prefix=".discovery-") as handle:
                temporary = handle.name
                handle.write(rendered)
            os.replace(temporary, args.output)
        except OSError:
            report["errors"].append({"operation": "write_output", "reason": "output_write_failed"})
            report["status"] = "partial" if report["candidates"] else "error"
            rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    sys.stdout.write(rendered)
    return {"ok": 0, "error": 1, "partial": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
