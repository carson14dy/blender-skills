#!/usr/bin/env python3
"""Build log: stages, gates, times and every shortcut of one build; `close` refuses "done" too early.

Plain Python, no bpy. Each command prints one JSON line and rewrites the log (--log, default build_log.json).
Usage:
  python build_log.py start --name "Garden shed" --accept acceptance.json [--session cloud|local] [--force]
  python build_log.py stage NAME [--done] [--note T]
  python build_log.py gate NAME --stdin|--result FILE|--pass|--fail [--deliverable] [--note T]
      (reads the last @@JSON@@, RT_RESULT or RT_QA line of the text, else the text as JSON)
  python build_log.py shortcut --kind K --what T --why T [--effect T] [--check ID] [--approved]
  python build_log.py approve N [N ...]       (only after the user said yes)
  python build_log.py close [--times FILE]    exit 0 when done, 2 while blockers remain
  python build_log.py report [--json]         the text for the final message
Kinds: simplified omitted substituted assumed preview unverified tolerance brief-change.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time

KINDS = ("simplified", "omitted", "substituted", "assumed", "preview", "unverified", "tolerance", "brief-change")
LINE = re.compile(r"(?:@@JSON@@|RT_RESULT |RT_QA )(\{.*\})\s*$")
KEEP = ("complete", "spec_sha", "partial", "failed", "assumed", "checked", "passed", "preset", "samples", "res",
        "device", "deliverable", "sec_per_image", "blender", "error", "tris")
ARGS = {"start": "--name! --accept! --session --force?", "stage": "name --done? --note",
        "gate": "name --stdin? --result --pass? --fail? --deliverable? --note",
        "shortcut": "--kind! --what! --why! --effect --check --approved?", "approve": "numbers+",
        "close": "--times", "report": "--json?"}


class Fail(Exception):
    pass


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def _cur(log):  # the open stage
    return next((s for s in log["stages"] if "end" not in s), None)


def _end(s):
    s["end"] = time.time()
    s["seconds"] = round(s["end"] - s["start"], 1)


def cmd_start(a, log):
    if log and not a.force:
        raise Fail(f"{a.log} exists: pass --force to start over")
    if a.session not in (None, "cloud", "local"):
        raise Fail("--session is cloud or local")
    try:
        with open(a.accept, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError) as e:
        raise Fail(f"acceptance file: {e}") from None
    checks = [c for c in (spec.get("checks") if isinstance(spec, dict) else 0) or [] if isinstance(c, dict)]
    if not checks:
        raise Fail("the acceptance file has no checks")
    assumed = [f"{c.get('id') or i + 1}: {c.get('note') or 'no note'}" for i, c in enumerate(checks)
               if c.get("source") not in ("given", "reference", "measured", "standard")]
    log.clear()
    log.update(name=a.name, started=time.time(), date=datetime.datetime.now().isoformat(timespec="seconds"),
               session=a.session or ("local" if sys.platform == "win32" else "cloud"), accept=os.path.abspath(a.accept),
               sha=_sha(a.accept), checks=len(checks), assumed=assumed, stages=[], gates=[], shortcuts=[])
    return {"ok": True, "log": a.log, "sha": log["sha"], "checks": len(checks), "assumed": assumed}


def cmd_stage(a, log):
    cur = _cur(log)
    if a.done and (not cur or cur["name"] != a.name):
        raise Fail(f"stage {a.name!r} is not open" + (f" ({cur['name']!r} is)" if cur else ""))
    if cur:
        _end(cur)
    if not a.done:
        log["stages"].append({"name": a.name, "start": time.time()})
    (cur if a.done else log["stages"][-1]).update({"note": a.note} if a.note else {})
    return {"ok": True, "stage": a.name, "seconds": cur["seconds"]} if a.done else \
        {"ok": True, "stage": a.name, "ended": cur and cur["name"]}


def cmd_gate(a, log):
    src = [k for k in ("stdin", "result", "pass", "fail") if getattr(a, k)]
    if len(src) != 1:
        raise Fail("give one of --stdin, --result FILE, --pass, --fail")
    g = {"name": a.name, "stage": (_cur(log) or {}).get("name"), "time": time.time()}
    if src[0] in ("pass", "fail"):
        g.update({"pass": src[0] == "pass", "manual": True})
    else:
        if a.result:
            with open(a.result, encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
        hits = [m.group(1) for m in map(LINE.search, text.splitlines()) if m]
        try:
            r = json.loads(hits[-1] if hits else text)
        except ValueError as e:
            raise Fail(f"no input or unreadable JSON: {e}") from None
        if not isinstance(r, dict):
            raise Fail("the result is not a JSON object")
        g["pass"] = bool(r.get("pass", r.get("ok")))
        g.update({k: r[k] for k in KEEP if k in r})
        sec = r.get("seconds", r.get("sec_per_image"))
        w = r.get("warnings", r.get("warning"))
        w = w if isinstance(w, list) or w is None else str(w).split("; ")
        objs = r.get("objects") if isinstance(r.get("objects"), dict) else {}
        g.update({k: v for k, v in (
            ("seconds", sec), ("errors", len(r["errors"]) if isinstance(r.get("errors"), list) else None),
            ("warnings", None if w is None else len(w)), ("warning_texts", w and [str(x) for x in w[:5]]),
            ("forbidden", [f.get("rule") for f in r.get("forbidden") or []] or None),
            ("fails", [{k: x[k] for k in ("id", "expect", "got", "unit", "error") if k in x}
                       for x in r.get("results") or [] if isinstance(x, dict) and not x.get("pass")] or None),
            ("files", r["files"][:10] if isinstance(r.get("files"), list) else None),
            ("files_count", len(r["files"]) if isinstance(r.get("files"), list) else None),
            ("tris", r.get("tris") or sum(m.get("tris", 0) for m in objs.values() if isinstance(m, dict)) or None))
            if v is not None})
    if a.deliverable:
        g["for_delivery"] = True
        if g.get("deliverable") is False:
            g.update({"pass": False, "why": "preview quality is not a deliverable"})
    g.update({"note": a.note} if a.note else {})
    log["gates"].append(g)
    return {"ok": True, "gate": a.name, "pass": g["pass"], "stage": g["stage"]}


def cmd_shortcut(a, log):
    if a.kind not in KINDS:
        raise Fail(f"kind {a.kind!r}: use one of {', '.join(KINDS)}")
    if not a.what.strip() or not a.why.strip():
        raise Fail("--what and --why must say something")
    s = {"n": len(log["shortcuts"]) + 1, "kind": a.kind, "what": a.what.strip(), "why": a.why.strip(),
         "approved": a.approved, "stage": (_cur(log) or {}).get("name"),
         **{k: getattr(a, k) for k in ("effect", "check") if getattr(a, k)}}
    log["shortcuts"].append(s)
    return {"ok": True, "shortcut": s["n"], "approved": a.approved}


def cmd_approve(a, log):
    known = {s["n"]: s for s in log["shortcuts"]}
    if set(a.numbers) - set(known):
        raise Fail(f"no shortcut {sorted(set(a.numbers) - set(known))}: there are {len(known)}")
    for n in a.numbers:
        known[n]["approved"] = True
    return {"ok": True, "approved": a.numbers}


def _why(f):
    u = f" {f['unit']}" if f.get("unit") else ""
    return f.get("error") or f"expected {f.get('expect')}{u}, got {f.get('got')}{u}"


def _full(log):  # complete acceptance runs
    return [g for g in log["gates"] if g.get("spec_sha") and not g.get("partial")]


def _last(log, name):
    return ([g for g in log["gates"] if g["name"] == name] or [None])[-1]


def blockers(log):
    out, cuts, full = [], log["shortcuts"], _full(log)
    base = os.path.basename(log["accept"])
    if not full:
        out.append("no full acceptance run: pipe acceptance_check.py (no --only) into gate acceptance --stdin")
    elif not full[-1]["pass"]:
        items = [(f["id"], _why(f)) for f in full[-1].get("fails", [])]
        items += [(r, "forbidden items in the scene") for r in full[-1].get("forbidden", [])]
        out += [] if items else [f"the last acceptance run failed: {full[-1].get('error', 'no pass')}"]
        for cid, why in items:
            mine = [s for s in cuts if s.get("check") == cid]
            if not any(s["approved"] for s in mine):
                n = mine and mine[-1]["n"]
                out.append(f"check '{cid}' fails ({why}): " + (f"shortcut {n} needs the user's yes (approve {n})" if n
                           else f"fix it, or log a shortcut with --check {cid} and get the user's yes"))
    now = _sha(log["accept"]) if os.path.isfile(log["accept"]) else "missing"
    if full and now != full[-1]["spec_sha"]:
        out.append(f"{base} changed after the last acceptance run: run it again")
    if now != log["sha"] and not any(s["kind"] in ("brief-change", "tolerance") for s in cuts):
        out.append(f"{base} changed since start ({log['sha']} -> {now}): log why as a brief-change shortcut")
    qa, look = _last(log, "qa"), _last(log, "look")
    if not qa or not qa["pass"] or qa.get("complete") is False:
        out.append("no qa gate: run qa_check.py, then gate qa" if not qa else
                   f"the last qa gate {'failed' if not qa['pass'] else 'is incomplete: re-run with --max-tris 0'}")
    if not look or not look["pass"] or not look.get("note"):
        out.append("no passing look gate with a note: look, then gate look --pass --note '<what you saw>'")
    for name in dict.fromkeys(g["name"] for g in log["gates"] if g.get("for_delivery")):
        g = [g for g in log["gates"] if g["name"] == name and g.get("for_delivery")][-1]
        if not g["pass"]:
            out.append(f"deliverable gate '{name}' failed" + (f": {g['why']}" if g.get("why") else ""))
    if _cur(log):
        out.append(f"stage '{_cur(log)['name']}' is still open: stage {_cur(log)['name']} --done")
    return out


def _min(sec):
    return f"{sec / 60:.1f}" if sec < 600 else f"{sec / 60:.0f}"


def _stages(log):
    st = {}
    for s in log["stages"]:
        st[s["name"]] = round(st.get(s["name"], 0) + s.get("seconds", time.time() - s["start"]), 1)
    return st


def report(log):
    b, full, cuts = blockers(log), _full(log), log["shortcuts"]
    acc = f"({os.path.basename(log['accept'])} {log['sha']})"
    out = [f"Build: {log['name']} ({log['session']}, {_min(time.time() - log['started'])} min)"]
    if full:
        g = full[-1]
        out += [f"Acceptance: {g.get('passed')} of {g.get('checked')} checks pass {acc}"]
        out += [f"  FAIL {f['id']}: {_why(f)}" for f in g.get("fails", [])]
        out += [f"  FAIL forbid {r}" for r in g.get("forbidden", [])]
    else:
        out.append(f"Acceptance: not run {acc}")
    out.append(f"Shortcuts ({len(cuts)}):" if cuts else "Shortcuts: none logged")
    for s in cuts:
        out.append(f"  {s['n']}. {s['kind']}: {s['what'].rstrip('.')}. Why: {s['why'].rstrip('.')}."
                   + "".join(f" {k.title()}: {s[k].rstrip('.')}." for k in ("effect", "check") if s.get(k))
                   + (" APPROVED" if s["approved"] else " NOT APPROVED"))
    assumed = full[-1].get("assumed", log["assumed"]) if full else log["assumed"]
    out.append(f"Assumed values ({len(assumed)}): " + "; ".join(assumed) if assumed else "Assumed values: none")
    parts = []
    for n in dict.fromkeys(g["name"] for g in log["gates"] if not g.get("spec_sha")):
        g = _last(log, n)
        info = [f"{g[k]} {k}" for k in ("errors", "warnings") if k in g]
        info += [("complete" if g["complete"] else "INCOMPLETE")] if "complete" in g else []
        parts.append(f"{n} {'pass' if g['pass'] else 'FAIL'}" + (f" ({', '.join(info)})" if info else "")
                     + (f", {g['preset']} {'x'.join(map(str, g.get('res') or []))} {g.get('samples')} samples"
                        if "preset" in g else ""))
    out.append("Gates: " + (", ".join(parts) or "none"))
    out.append("Time: " + (", ".join(f"{n} {_min(s)} min" for n, s in _stages(log).items()) or "no stages")
               + f"; gates {_min(sum(g.get('seconds') or 0 for g in log['gates']))} min")
    out.append("Done: yes" if not b else f"Done: no ({len(b)} blocker{'s' * (len(b) > 1)})")
    return "\n".join(out + [f"  - {x}" for x in b]), b


def cmd_close(a, log):
    b, full = blockers(log), _full(log)
    minutes = round((time.time() - log["started"]) / 60, 1)
    log["closed"] = {"time": time.time(), "done": not b, "blockers": b}
    if a.times:
        gates, rend = log["gates"], [g for g in log["gates"] if "preset" in g or "sec_per_image" in g]
        pick = lambda k, gs=gates: next((g[k] for g in reversed(gs) if g.get(k) is not None), None)  # noqa: E731
        gsec = {}
        for g in gates:
            gsec[g["name"]] = round(gsec.get(g["name"], 0) + (g.get("seconds") or 0), 2)
        row = {"name": log["name"], "date": log["date"], "session": log["session"], "blender": pick("blender"),
               "device": pick("device", rend), "minutes": minutes, "stages": _stages(log), "gates": gsec,
               "renders": [{k: g.get(k) for k in ("res", "samples", "sec_per_image", "device")} for g in rend],
               "tris": pick("tris"), "checks": pick("checked", full), "passed": pick("passed", full),
               "shortcuts": len(log["shortcuts"]), "done": not b}
        with open(a.times, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    return {"done": not b, "blockers": b, "shortcuts": len(log["shortcuts"]), "minutes": minutes}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, spec in ARGS.items():
        s = sub.add_parser(cmd)
        s.add_argument("--log", default="build_log.json")
        for x in spec.split():
            kw = {"?": {"action": "store_true"}, "+": {"nargs": "+", "type": int}, "!": {"required": True}}
            s.add_argument(x.rstrip("?+!"), **kw.get(x[-1], {}))
    a = p.parse_args(argv)
    try:
        log = {}
        if os.path.exists(a.log):
            with open(a.log, encoding="utf-8") as f:
                log = json.load(f)
        elif a.cmd != "start":
            raise Fail(f"no log at {a.log}: run build_log.py start first")
        if a.cmd == "report":
            text, b = report(log)
            print(json.dumps({"done": not b, "blockers": b, "text": text}) if a.json else text)
            return 0
        res = globals()["cmd_" + a.cmd](a, log)
        with open(a.log + ".tmp", "w", encoding="utf-8") as f:
            json.dump(log, f, indent=1)
        os.replace(a.log + ".tmp", a.log)
    except Fail as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 0 if a.cmd == "report" else 1
    print(json.dumps(res))
    return 2 if a.cmd == "close" and not res["done"] else 0


if __name__ == "__main__":
    sys.exit(main())
