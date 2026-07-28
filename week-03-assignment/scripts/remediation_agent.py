"""
Remediation agent (Week 3 Assignment, Task 2).

Detects ONE narrow failure class: a ModuleNotFoundError caused by a package
that's imported in code but missing from requirements.txt. Confirms the
package name with Claude (structured JSON output), then opens a PR that adds
exactly one line to requirements.txt -- nothing else.

Deliberately narrow blast radius: this agent can ONLY ever modify
requirements.txt, and can only ADD a line, never remove or rewrite existing
ones. See docs/guardrails.md.
"""
import argparse
import json
import os
import re
import sys

import anthropic
from github import Github

MODEL = os.environ.get("MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = """\
You are a narrowly-scoped remediation agent. Your ONLY job is: given a
Python build log containing a ModuleNotFoundError, identify the missing
package's PyPI name and propose a single requirements.txt line to add it
(e.g. "requests>=2.31"). You do not propose any other change. If the log
does not contain a ModuleNotFoundError, say so and propose nothing."""

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "is_missing_dependency": {"type": "boolean"},
        "missing_package": {"type": "string"},
        "requirements_line": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["is_missing_dependency", "missing_package", "requirements_line", "explanation"],
    "additionalProperties": False,
}


def detect_module_not_found(build_log):
    return bool(re.search(r"ModuleNotFoundError", build_log))


def ask_agent(build_log, client):
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": FIX_SCHEMA}},
        messages=[{
            "role": "user",
            "content": f"Build log:\n```\n{build_log}\n```",
        }],
    )
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def open_pr(fix, repo_name, base_branch, run_id, requirements_path):
    gh = Github(os.environ["GH_TOKEN"])
    repo = gh.get_repo(repo_name)
    branch_name = f"bot/fix-deps-{run_id}"

    ref = repo.get_git_ref(f"heads/{base_branch}")
    repo.create_git_ref(f"refs/heads/{branch_name}", ref.object.sha)

    contents = repo.get_contents(requirements_path, ref=base_branch)
    current_text = contents.decoded_content.decode("utf-8")
    new_text = current_text.rstrip("\n") + f"\n{fix['requirements_line']}\n"

    repo.update_file(
        requirements_path,
        f"[bot] deps: add missing {fix['missing_package']}",
        new_text,
        contents.sha,
        branch=branch_name,
    )

    pr = repo.create_pull(
        title=f"[Bot Fix] Add missing dependency: {fix['missing_package']}",
        body=(
            f"## Auto-Remediation: Missing Dependency\n\n"
            f"**Detected:** ModuleNotFoundError for `{fix['missing_package']}`\n\n"
            f"**Explanation:** {fix['explanation']}\n\n"
            f"**Change:** appended `{fix['requirements_line']}` to `{requirements_path}`. "
            f"No other lines were modified.\n\n"
            f"---\n*Opened by the remediation agent. A human must review and merge.*\n"
        ),
        head=branch_name,
        base=base_branch,
    )
    print(f"Opened PR #{pr.number}: {pr.html_url}")
    return pr.number


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--open-pr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.log) as f:
        build_log = f.read()

    if not detect_module_not_found(build_log):
        print("No ModuleNotFoundError detected in log -- nothing to remediate.")
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    fix = ask_agent(build_log, client)

    if not fix["is_missing_dependency"]:
        print(f"Agent determined this is not a missing-dependency issue: {fix['explanation']}")
        return

    print(f"Missing package: {fix['missing_package']}")
    print(f"Proposed line:   {fix['requirements_line']}")
    print(f"Explanation:     {fix['explanation']}")

    if args.open_pr:
        open_pr(
            fix,
            repo_name=os.environ["REPO"],
            base_branch=os.environ.get("BASE_BRANCH", "main"),
            run_id=os.environ.get("GITHUB_RUN_ID", "local"),
            requirements_path=args.requirements,
        )
    else:
        print("(dry run -- no PR opened)")


if __name__ == "__main__":
    main()
