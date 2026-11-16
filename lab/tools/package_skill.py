#!/usr/bin/env python3
"""Package a skill folder as a .skill file (a zip with the folder at its root) for claude.ai or other machines.

    python lab/tools/package_skill.py .claude/skills/blender-suite out/skills
    -> out/skills/blender-suite.skill

Runs the skill's own linter first when it has one (tests/check_skill.py --strict) and stops if it fails.
Leaves out __pycache__, *.pyc, .DS_Store and node_modules, like skill-creator's packager.
Install the result:
  claude.ai:   Settings > Capabilities > Skills, upload the .skill file
  Claude Code: unzip it into ~/.claude/skills/   (Windows: %USERPROFILE%\\.claude\\skills\\)
"""
import pathlib
import subprocess
import sys
import zipfile

SKIP_DIRS = {"__pycache__", "node_modules"}
SKIP_FILES = {".DS_Store"}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = pathlib.Path(sys.argv[1]).resolve()
    out_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".").resolve()
    if not (src / "SKILL.md").is_file():
        print(f"no SKILL.md in {src}")
        return 1
    lint = src / "tests" / "check_skill.py"
    if lint.is_file():
        r = subprocess.run([sys.executable, str(lint), "--strict"], capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-2000:] + r.stderr[-1000:])
            print("lint failed: not packaged")
            return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{src.name}.skill"
    files = sorted(p for p in src.rglob("*") if p.is_file() and not (SKIP_DIRS & set(p.relative_to(src).parts))
                   and p.name not in SKIP_FILES and p.suffix != ".pyc")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(src.parent).as_posix())
    print(f"{len(files)} files -> {dest} ({dest.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
