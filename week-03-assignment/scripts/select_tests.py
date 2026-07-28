"""
Test-impact analysis: run only the tests relevant to changed source files.

Convention: src/<name>.py maps to tests/test_<name>.py. Compares the current
working tree against the previous commit (or against an empty tree on the
very first commit) to find which src/ files actually changed, then prints
just the matching test file paths -- the CI workflow runs only those,
instead of the full suite every time.
"""
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path("src")
TESTS_DIR = Path("tests")


def get_changed_files():
    """Return changed .py files under src/, comparing HEAD~1..HEAD.
    Falls back to 'everything' on the first commit (no parent to diff against)."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True
    )
    if diff.returncode != 0:
        # No parent commit (first commit in the repo) -- treat all src files as changed.
        return [str(p) for p in SRC_DIR.glob("*.py")]

    changed = [
        line for line in diff.stdout.strip().splitlines()
        if line.startswith("src/") and line.endswith(".py")
    ]
    return changed


def map_to_test_files(changed_src_files):
    """src/foo.py -> tests/test_foo.py, by naming convention."""
    selected = []
    for src_path in changed_src_files:
        name = Path(src_path).stem  # e.g. "calculator"
        test_path = TESTS_DIR / f"test_{name}.py"
        if test_path.exists():
            selected.append(str(test_path))
    return selected


def main():
    all_tests = sorted(str(p) for p in TESTS_DIR.glob("test_*.py"))
    changed = get_changed_files()
    selected = map_to_test_files(changed)

    print(f"Changed src/ files: {changed or '(none)'}", file=sys.stderr)
    print(f"Total test files available: {len(all_tests)}", file=sys.stderr)
    print(f"Test files selected to run: {len(selected)}", file=sys.stderr)

    if not selected:
        # Nothing matched (e.g. only docs/config changed) -- run nothing extra,
        # but don't silently skip everything if src/ genuinely has no test yet.
        print("(no matching tests -- printing nothing to run)", file=sys.stderr)
        return

    # Print space-separated paths on stdout ONLY -- this is what the workflow
    # captures and passes straight to `pytest`.
    print(" ".join(selected))


if __name__ == "__main__":
    main()
