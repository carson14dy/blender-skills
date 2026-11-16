#!/usr/bin/env python3
"""Package a skill folder as a .skill file (a zip with the folder at its root) for claude.ai or other machines.

    python lab/tools/package_skill.py .claude/skills/blender-suite out/skills
    -> out/skills/blender-suite.skill

Runs the skill's own linter first when it has one (tests/check_skill.py --strict) and stops if it fails.
Leaves out __pycache__, *.pyc, .DS_Store and node_modules, like skill-creator's packager.
Also leaves out the skill's tests/ folder, except tests/check_skill.py: claude.ai takes at most 200 files per
skill, and the regression suite needs Blender, so it stays in the repository. Pass --with-tests to keep it.
The packaged copy is unzipped and linted again before the file is kept.
Install the result:
  claude.ai:   Settings > Capabilities > Skills, upload the .skill file
  Claude Code: unzip it into ~/.claude/skills/   (Windows: %USERPROFILE%\\.claude\\skills\\)
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

SKIP_DIRS = {"__pycache__", "node_modules"}
SKIP_FILES = {".DS_Store"}
KEEP_IN_TESTS = {"check_skill.py"}      # the linter ships, so an unpacked copy can check itself
MAX_FILES = 199                         # claude.ai refuses a skill with more than 200 files


def lint(folder):
    r = subprocess.run([sys.executable, str(folder / "tests" / "check_skill.py"), "--strict"],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:] + r.stderr[-1000:])
    return r.returncode == 0


def main():
    args = [a for a in sys.argv[1:] if a != "--with-tests"]
    with_tests = "--with-tests" in sys.argv
    if not args:
        print(__doc__)
        return 1
    src = pathlib.Path(args[0]).resolve()
    out_dir = pathlib.Path(args[1] if len(args) > 1 else ".").resolve()
    if not (src / "SKILL.md").is_file():
        print(f"no SKILL.md in {src}")
        return 1
    has_lint = (src / "tests" / "check_skill.py").is_file()
    if has_lint and not lint(src):
        print("lint failed: not packaged")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{src.name}.skill"
    files = sorted(p for p in src.rglob("*") if p.is_file() and not (SKIP_DIRS & set(p.relative_to(src).parts))
                   and p.name not in SKIP_FILES and p.suffix != ".pyc")
    if not with_tests:
        files = [p for p in files if p.relative_to(src).parts[0] != "tests" or p.name in KEEP_IN_TESTS]
    if len(files) > MAX_FILES:
        print(f"{len(files)} files > {MAX_FILES}: claude.ai will refuse it; not packaged")
        return 1
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(src.parent).as_posix())
    if has_lint:                          # the copy people install must pass its own linter
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="skill_check_"))
        try:
            with zipfile.ZipFile(dest) as z:
                z.extractall(tmp)
            if not lint(tmp / src.name):
                dest.unlink()
                print("the packaged copy fails its own lint: not packaged")
                return 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(files)} files -> {dest} ({dest.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
