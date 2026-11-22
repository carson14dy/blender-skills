#!/usr/bin/env python3
"""Lint the blender-suite skill: frontmatter, size budgets, Windows-safe names, links and paths, script contract.

Usage: python tests/check_skill.py [--strict]      (plain Python 3.9+, no bpy; --strict: warnings fail too)
Prints ERROR/WARN lines, a size table, then OK or FAIL. Exit code: 0 ok, 1 failed.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent          # the skill folder
REPO = ROOT.parents[2] if ROOT.parent.name == "skills" and ROOT.parents[1].name == ".claude" else None
if REPO and not (REPO / "roof-blender").is_dir():
    REPO = None                                                # installed copy, not the RoofTec repository
# A packaged .skill leaves out tests/ except this file (lab/tools/package_skill.py), to stay under the upload limit.
PACKAGED = not (ROOT / "tests" / "run_all.py").exists()
MAX_SHIPPED = 199                                              # claude.ai takes at most 200 files per skill
NAME = "blender-suite"
# bytes: (max for one file, max for the folder)
BUDGET = {"SKILL.md": (15000, 15000), "references": (10000, 300000), "scripts": (24000, 580000),
          "pipelines": (20000, 270000), "tests": (16000, 180000), "assets": (4000, 8000),
          "LICENSE": (4000, 4000), "NOTICE.md": (4000, 4000)}
TOTAL_MAX = 1_400_000
ALLOWED_EXT = {".md", ".py", ".toml", ".json", ".ps1", ".sh", ".cmd", ""}
REPO_PREFIXES = ("roof-blender/", "roof-visualizer/", "lab/", "docs/", "property-model-pipeline/")
SKILL_PREFIXES = ("scripts/", "references/", "pipelines/", "assets/", "tests/")
# backticked `blender-...` names that are not references in this skill
NOT_REFS = {"blender-suite", "blender-master", "blender-mcp", "blender-skills", "blender-agent-skills",
            "blender-shim", "blender-film", "blender-car-film", "blender-forest"}
REFS_AS_NAMES = {"blender-film", "blender-forest"}             # these two ARE references here
# file names used as examples in the text, or written by the user's project, not shipped
PLACEHOLDER = {"__init__.py", "operators.py", "ui.py", "script.py", "x.py", "your_tests.py", "f.py",
               "roof_core.py", "roof_qa.py", "test_roof_core.py", "mock_blender_mcp.py", "rig_ui.py",
               "step1.py", "step2.py"}
BANNED = {"skills/blender-": "path from the 28-skill layout", "shared/_bpyx": "there is one _bpyx.py now",
          "tools/send.py": "use scripts/blender_send.py", "bridge.py": "dropped: port clash with MCP for Blender",
          "sync_shared": "dropped tool", "<skills_dir>": "write <skill_dir>"}
PIPELINE_DOCS = {"blender-film.md", "blender-forest.md", "long-renders.md", "film-sound.md"}
LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
FILE_RE = re.compile(r"(?<![\w/.\\-])((?:[\w.-]+/)*[A-Za-z0-9][\w.-]*\.(?:py|ps1|sh|cmd|json|toml|md))\b")
NAME_RE = re.compile(r"`(blender-[a-z0-9-]+)`")
errs, warns = [], []


def rel(p):
    return p.relative_to(ROOT).as_posix()


def frontmatter(text):
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return None, text
    end = text.find("\n---", 4)
    fm = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip("\"'")
    return fm, text[end + 4:]


def check_tree(files):
    seen = {}
    for f in files:
        r = rel(f)
        if f.is_symlink():
            errs.append(f"{r}: symlink (Windows checkouts break them)")
        if f.suffix.lower() not in ALLOWED_EXT:
            errs.append(f"{r}: file type {f.suffix} is not allowed in the skill (no media, .blend or caches)")
        if re.search(r'[<>:"|?*\\]|[ .]$', f.name) or re.match(r"(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)", f.name):
            errs.append(f"{r}: name is not valid on Windows")
        if seen.setdefault(r.lower(), r) != r:
            errs.append(f"{r}: differs only by case from {seen[r.lower()]}")
        if len(f".claude/skills/{NAME}/{r}") > 110:
            errs.append(f"{r}: path longer than 110 characters from the repo root")
        raw = f.read_bytes()
        if b"\x00" in raw:
            errs.append(f"{r}: binary content")
        elif f.suffix in {".ps1", ".cmd"} and any(b > 127 for b in raw):
            errs.append(f"{r}: non-ASCII bytes (Windows PowerShell 5 misreads them)")
    sizes = {}
    for f in files:
        top = rel(f).split("/")[0]
        one, _ = BUDGET.get(top, (0, 0))
        n = f.stat().st_size
        sizes[top] = sizes.get(top, 0) + n
        if top not in BUDGET:
            errs.append(f"{rel(f)}: unexpected top-level entry {top!r}")
        elif n > one:
            errs.append(f"{rel(f)}: {n} bytes > {one} budget for one file in {top}")
    for top, total in sorted(sizes.items()):
        cap = BUDGET.get(top, (0, 0))[1]
        print(f"  {top:<12} {total:>9} bytes" + (f"  (max {cap})" if cap else ""))
        if cap and total > cap:
            errs.append(f"{top}: {total} bytes > {cap} folder budget")
    total = sum(sizes.values())
    print(f"  {'total':<12} {total:>9} bytes  (max {TOTAL_MAX})")
    if total > TOTAL_MAX:
        errs.append(f"skill is {total} bytes > {TOTAL_MAX}")


def check_docs(files):
    by_name = {}
    for f in files:
        by_name.setdefault(f.name, []).append(f)
    refs = {f.stem for f in (ROOT / "references").glob("*.md")}
    docs = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]
    texts = {d: d.read_text("utf-8") for d in docs if d.exists()}
    for d, text in texts.items():
        r = rel(d)
        for bad, why in BANNED.items():
            if bad in text.replace("skills/blender-suite", ""):   # this skill's own folder is fine
                errs.append(f"{r}: contains {bad!r} ({why})")
        for link in LINK_RE.findall(text):
            if "://" not in link and not link.startswith("mailto:") and not (d.parent / link).exists():
                errs.append(f"{r}: broken link {link}")
        for name in set(NAME_RE.findall(text)):
            if name not in refs and name not in NOT_REFS - REFS_AS_NAMES:
                errs.append(f"{r}: `{name}` is not a reference (references/{name}.md)")
        code_free = re.sub(r"https?://\S+", "", text)
        for tok in set(FILE_RE.findall(code_free)):
            base = tok.rsplit("/", 1)[-1]
            if tok.startswith(SKILL_PREFIXES):
                if not (ROOT / tok).exists() and base not in PLACEHOLDER \
                        and not (PACKAGED and tok.startswith("tests/")):
                    errs.append(f"{r}: path {tok} does not exist in the skill")
            elif tok.startswith(REPO_PREFIXES):
                if REPO and not (REPO / tok).exists():
                    errs.append(f"{r}: repo path {tok} does not exist")
            elif tok.startswith((".claude/", "~", "out/", "render/", "export/", "src/", "scene/", "audio/")):
                continue
            elif base.endswith(".md") and base not in by_name and base not in {"PLAN.md", "SECURITY.md",
                                                                               "CLAUDE.md", "LOG.md", "NEXT.md"}:
                errs.append(f"{r}: mentions {tok}, which the skill does not ship")
            elif base.endswith((".py", ".ps1", ".sh", ".cmd")) and base not in by_name \
                    and base not in PLACEHOLDER and not base.startswith("test_"):
                errs.append(f"{r}: mentions {tok}, which the skill does not ship")
            elif "/" not in tok and d.name in PIPELINE_DOCS and (ROOT / "scripts" / base).exists() \
                    and any(p.parts[len(ROOT.parts)] == "pipelines" for p in by_name[base]):
                errs.append(f"{r}: bare {base} exists in scripts/ and in pipelines/; write the folder")
    everything = "\n".join(texts.values())
    skill_md = texts.get(ROOT / "SKILL.md", "")
    for ref in sorted(refs):
        others = "\n".join(t for d, t in texts.items() if d.stem != ref)
        if f"`{ref}`" not in others and f"{ref}.md" not in others:
            errs.append(f"references/{ref}.md: orphan (no other document points to it)")
    for f in sorted((ROOT / "scripts").glob("*.py")):
        if f.name != "_bpyx.py" and f.name not in everything:
            errs.append(f"scripts/{f.name}: never mentioned in SKILL.md or a reference")
    for d in sorted(p for p in (ROOT / "pipelines").iterdir() if p.is_dir()) if (ROOT / "pipelines").exists() else []:
        if f"pipelines/{d.name}/" not in everything:
            errs.append(f"pipelines/{d.name}: never mentioned in SKILL.md or a reference")
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.name not in everything:
                errs.append(f"{rel(f)}: never mentioned in a reference (add it to the pipeline's file table)")
    for row in re.findall(r"^\|[^|\n]+\|\s*`([a-z0-9-]+)`\s*\|", skill_md, re.M):   # routing table
        if row not in refs:
            errs.append(f"SKILL.md: routing row points to missing reference {row}")
    for need in ("\n## Accuracy first\n", "acceptance_check.py", "build_log.py", "build-accuracy"):   # trims keep it
        if need not in skill_md:
            errs.append(f"SKILL.md: lacks {need.strip()!r} (the accuracy rule stays; shorten something else)")
    return skill_md


def check_frontmatter(text):
    fm, body = frontmatter(text)
    if fm is None:
        errs.append("SKILL.md: no YAML frontmatter")
        return
    if fm.get("name") != NAME or ROOT.name != NAME:
        errs.append(f"SKILL.md: name {fm.get('name')!r} and folder {ROOT.name!r} must both be {NAME!r}")
    desc = fm.get("description", "")
    raw = next((ln for ln in text.splitlines() if ln.startswith("description:")), "")
    if not 1 <= len(desc) <= 1024:
        errs.append(f"SKILL.md: description is {len(desc)} characters (1-1024)")
    if ": " in raw[len("description: "):] or " #" in raw:
        errs.append("SKILL.md: description has ': ' or ' #' (breaks YAML plain scalars)")
    if body.count("\n") > 200:
        errs.append(f"SKILL.md: body is {body.count(chr(10))} lines (max 200)")


def check_code():
    for f in sorted(ROOT.rglob("*.py")):
        src = f.read_text("utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            errs.append(f"{rel(f)}: syntax error {e}")
            continue
        if f.parent != ROOT / "scripts" or f.name == "_bpyx.py":
            continue
        if "Usage" not in (ast.get_docstring(tree) or ""):
            errs.append(f"{rel(f)}: docstring lacks 'Usage'")
        top_imports = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        if "bpy" in top_imports:
            if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
                errs.append(f"{rel(f)}: Blender script without run()")
            if "_bpyx" not in src:
                errs.append(f"{rel(f)}: Blender script does not use _bpyx (one JSON result line)")


def check_license():
    for name, needles in {"LICENSE": ["EL4CTEO", "Mr omi", "Permission is hereby granted"],
                          "NOTICE.md": ["EL4CTEO", "Mr omi", "blender-master", "kevinbadi", "Poly Haven"]}.items():
        f = ROOT / name
        text = f.read_text("utf-8") if f.exists() else ""
        for n in needles:
            if n not in text:
                errs.append(f"{name}: missing {n!r}")
    for f in ROOT.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and f.name != "NOTICE.md" and f.suffix in {".md", ".py"} and f.name != "check_skill.py" \
                and "kevinbadi" in f.read_text("utf-8", errors="replace"):
            errs.append(f"{rel(f)}: mentions kevinbadi (only NOTICE.md may)")


def main():
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts)  # git-ignored
    check_tree(files)
    shipped = [f for f in files if rel(f).split("/")[0] != "tests" or f.name == "check_skill.py"]
    print(f"  {'packaged' if PACKAGED else 'repository'} copy: {len(shipped)} files ship in the .skill (max {MAX_SHIPPED})")
    if len(shipped) > MAX_SHIPPED:
        errs.append(f"{len(shipped)} files would ship in the .skill > {MAX_SHIPPED}")
    skill_md = (ROOT / "SKILL.md").read_text("utf-8") if (ROOT / "SKILL.md").exists() else ""
    if not skill_md:
        errs.append("SKILL.md: missing")
    else:
        check_frontmatter(skill_md)
    check_docs(files)
    check_code()
    check_license()
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    fail = bool(errs) or ("--strict" in sys.argv and bool(warns))
    print(f"{len(files)} files, {len(errs)} errors, {len(warns)} warnings")
    print("FAIL" if fail else "OK")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
