#!/usr/bin/env python3
"""Lightweight quality-gate runner and PR helper for ganglia-studio."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "logs"


def run_command(cmd: List[str]) -> None:
    """Run a command and fail fast if it exits non-zero."""
    print(f"\n▶️  {shlex.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=False, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_lint() -> None:
    run_command(["ruff", "check", "src/"])
    run_command(
        [
            "pylint",
            "src/ganglia_studio/",
            "--disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801",
        ]
    )


def run_tests() -> None:
    run_command(["pytest", "tests/unit/", "-v", "--tb=short"])
    run_command(["pytest", "tests/integration/", "-v", "--tb=short", "-m", "not costly"])


def run_coverage() -> None:
    run_command(
        [
            "pytest",
            "tests/unit/",
            "--cov=src/ganglia_studio",
            "--cov-report=term",
            "--cov-report=xml",
            "--cov-report=html",
        ]
    )
    run_command(["python", "-m", "coverage", "report", "--show-missing"])


def run_package() -> None:
    run_command(["python", "-m", "build"])
    dist_dir = REPO_ROOT / "dist"
    artifacts = sorted(dist_dir.glob("*"))
    if not artifacts:
        raise SystemExit("No artifacts found in dist/ after build step.")
    run_command(["python", "-m", "twine", "check", *[str(a) for a in artifacts]])


CHECKS: Dict[str, Callable[[], None]] = {
    "lint": run_lint,
    "tests": run_tests,
    "coverage": run_coverage,
    "package": run_package,
}


def detect_repo() -> tuple[str, str]:
    """Return (owner, name) for the current GitHub repository."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "owner,name"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    owner = data.get("owner", {}).get("login")
    name = data.get("name")
    if not owner or not name:
        raise RuntimeError("Unable to determine repository owner/name via gh CLI.")
    return owner, name


def fetch_pr_comments(pr_number: int) -> None:
    """Dump review thread + general PR comments to logs/ and summarize to stdout."""
    owner, name = detect_repo()
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes {
              id
              isResolved
              comments(first: 1) {
                nodes {
                  id
                  body
                  path
                  line
                  author { login }
                  createdAt
                }
              }
            }
          }
          comments(first: 100) {
            nodes {
              id
              body
              author { login }
              createdAt
            }
          }
        }
      }
    }
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={pr_number}",
            "-f",
            f"query={query}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    pr_data = data.get("data", {}).get("repository", {}).get("pullRequest", {})
    threads = pr_data.get("reviewThreads", {}).get("nodes", [])
    review_entries = []
    for thread in threads:
        comment = (thread.get("comments") or {}).get("nodes", [{}])[0]
        review_entries.append(
            {
                "thread_id": thread.get("id"),
                "comment_id": comment.get("id"),
                "is_resolved": thread.get("isResolved", True),
                "author": (comment.get("author") or {}).get("login"),
                "path": comment.get("path"),
                "line": comment.get("line"),
                "created_at": comment.get("createdAt"),
                "body": comment.get("body"),
            }
        )
    general_entries = [
        {
            "comment_id": item.get("id"),
            "author": (item.get("author") or {}).get("login"),
            "created_at": item.get("createdAt"),
            "body": item.get("body"),
        }
        for item in pr_data.get("comments", {}).get("nodes", [])
    ]
    LOG_DIR.mkdir(exist_ok=True)
    out_file = LOG_DIR / f"pr_{pr_number}_comments.json"
    with out_file.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "pull_request": pr_number,
                "review_threads": review_entries,
                "general_comments": general_entries,
            },
            handle,
            indent=2,
        )
    unresolved = [entry for entry in review_entries if not entry["is_resolved"]]
    print(
        f"\n📝 Saved PR #{pr_number} comments to {out_file.relative_to(REPO_ROOT)} "
        f"(threads={len(review_entries)}, unresolved={len(unresolved)}, "
        f"general={len(general_entries)})"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local quality gates that mirror CI checks."
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        metavar="CHECK",
        help="Space-separated list of checks to run (lint, tests, coverage, package). "
        "Use 'all' to run everything.",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List available checks and exit.",
    )
    parser.add_argument(
        "--fetch-pr-comments",
        type=int,
        metavar="PR_NUMBER",
        help="Dump PR comments (review threads + general comments) to logs/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_checks:
        print("Available checks:", ", ".join(sorted(CHECKS)))
        return
    if args.fetch_pr_comments:
        fetch_pr_comments(args.fetch_pr_comments)
        if not args.checks:
            return
    checks = args.checks or ["lint", "tests"]
    if "all" in checks:
        checks = list(CHECKS.keys())
    for check in checks:
        handler = CHECKS.get(check)
        if not handler:
            raise SystemExit(f"Unknown check '{check}'. Use --list-checks for options.")
        print(f"\n=== Running {check} ===")
        handler()
    print("\n✅ All requested checks completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc)
        raise

