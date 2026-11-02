#!/usr/bin/env python3
"""engineering-rails: stage gates for engineering development with AI agents.

State lives in <project>/.rails/ so any agent (Claude Code, Codex, Pi, ...) and any human
sees the same truth. Stdlib only, Python 3.8+.

Commands (run from anywhere inside the project, or pass --root):
  init                                   create .rails/ and the project context template
  start "<title>" --lane L --why "..."   open a task (L = hotfix|small|feature) [--ai]
  status                                 where am I, what is missing, what to run next
  check [stage]                          validate a stage's artifact (exit 1 if not ready)
  approve <stage> --quote "<user words>" record the human's explicit approval
  advance                                move to the next stage if its gate passes
  back <stage> --reason "..."            return to an earlier stage (re-plan, re-design)
  lane <L> --why "..." [--quote "..."]   change lane; downgrade needs a human quote
  can-edit <path>...                     exit 0 only if editing these paths is allowed now
  metrics [--write]                      time per stage + bottleneck (optionally into the retro)
  list                                   all tasks
  switch <task-id>                       make another task current
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STAGES = ["context", "design", "plan", "implement", "verify", "release", "retro", "done"]
HUMAN_GATES = {"design", "plan", "verify"}
LANES = ["hotfix", "small", "feature"]
COMBINED_LANES = {"hotfix", "small"}  # may approve design+plan in one human answer
ARTIFACT = {
    "design": "01-design.md",
    "plan": "02-plan.md",
    "verify": "04-verify.md",
    "release": "05-release.md",
    "retro": "06-retro.md",
}
TEMPLATES = Path(__file__).resolve().parent.parent / "assets" / "templates"
CONTEXT_MAX_AGE_DAYS = 30

DESIGN_SECTIONS = {
    "feature": ["Задача бизнеса", "Ограничения", "Компоненты и интеграция", "Альтернативы",
                "Решение и обоснование", "Допущения и риски", "Критерии приёмки"],
    "small": ["Задача", "Решение", "Критерии приёмки"],
    "hotfix": ["Симптом и ожидаемое поведение", "Причина", "Критерии приёмки"],
}
PLAN_SECTIONS = {
    "feature": ["Шаги", "Границы", "Параллелизация", "Ревью"],
    "small": ["Шаги"],
    "hotfix": ["Шаги"],
}
CONTEXT_SECTIONS = ["Архитектура", "Предметная область", "Бизнес-правила", "Продакшн",
                    "Решения (ADR)", "Доступы агента"]
VERIFY_SECTIONS = ["Автоматические проверки", "Критерии приёмки", "Human review"]
RELEASE_SECTIONS = ["Деплой", "Откат", "Мониторинг ошибок"]
RETRO_SECTIONS = ["Узкое место", "Что улучшить"]

PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|\{title\}|<[^>\n]{0,40}>|^\s*\.\.\.\s*$|^\s*-\s*$", re.M)
AC_LINE = re.compile(r"^\s*[-*]\s*(AC-\d+)\s*:\s*(.+)$", re.M)
STEP_LINE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(S\d+)\s*:\s*(.+)$", re.M)
PASS_WORDS = re.compile(r"\b(PASS|OK)\b|✅|RISK-ACCEPTED", re.I)
RISK_LINE = re.compile(r"RISK-ACCEPTED\s*[—\-:]\s*(.+)", re.I)
# Pressure that is NOT consent: "просто пиши код", "нет времени", "skip the tests"...
PRESSURE = re.compile(r"просто\s+(пиши|делай|сделай|напиши|код)|нет\s+времени|некогда|хватит|"
                      r"без\s+(план|тест|дизайн|док|бюрократ)|не\s+(надо|нужн\w*)\s+(план|тест|дизайн|док)|"
                      r"just\s+(do|write|code|ship)|no\s+time|skip", re.I)
CONSENT = re.compile(r"(?<![а-яё])(да|ок|окей|согласен|согласна|одобряю|принимаю|подтверждаю|верно|годится)(?![а-яё])|"
                     r"\b(yes|ok|okay|approve[d]?|lgtm)\b", re.I)
FAIL_WORDS = re.compile(r"\b(FAIL|FAILED|SKIP|SKIPPED)\b|❌", re.I)
NA_LINE = re.compile(r"^\s*N/A\s*[—\-:]\s*\S.{8,}", re.M | re.I)


# ---------------------------------------------------------------- helpers

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def find_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".rails").is_dir():
            return p
    return None


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def sections(text: str) -> dict[str, str]:
    """Map '## Heading' -> body (comments stripped)."""
    text = strip_comments(text)
    out: dict[str, str] = {}
    parts = re.split(r"^##\s+(.+?)\s*$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        out[parts[i].strip()] = parts[i + 1].strip()
    return out


def check_sections(text: str, required: list[str], allow_na: bool = False) -> list[str]:
    problems = []
    secs = sections(text)
    for name in required:
        body = secs.get(name)
        if body is None:
            problems.append(f"section '## {name}' is missing")
        elif not body:
            problems.append(f"section '## {name}' is empty")
        elif PLACEHOLDER.search(body):
            problems.append(f"section '## {name}' still has a placeholder (TODO/TBD/<...>/...)")
        elif allow_na and body.upper().startswith("N/A") and not NA_LINE.search(body):
            problems.append(f"section '## {name}': 'N/A' needs a reason, e.g. 'N/A — no production yet'")
    return problems


def git_changed_files(root: Path) -> list[str] | None:
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True,
                             text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
                         capture_output=True, text=True).stdout
    files = []
    for line in out.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        abs_path = (Path(top) / path).resolve()
        try:
            files.append(abs_path.relative_to(root.resolve()).as_posix())
        except ValueError:
            continue
    return files


# ---------------------------------------------------------------- state

class Rails:
    def __init__(self, root: Path):
        self.root = root
        self.dir = root / ".rails"
        self.tasks = self.dir / "tasks"

    # -- task state
    def current_id(self) -> str | None:
        f = self.dir / "current"
        return f.read_text().strip() if f.exists() and f.read_text().strip() else None

    def task_dir(self, tid: str) -> Path:
        return self.tasks / tid

    def load(self, tid: str | None = None) -> dict | None:
        tid = tid or self.current_id()
        if not tid:
            return None
        f = self.task_dir(tid) / "state.json"
        return json.loads(f.read_text()) if f.exists() else None

    def save(self, st: dict) -> None:
        (self.task_dir(st["id"]) / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2))

    def log(self, st: dict, event: str, **kw) -> None:
        rec = {"at": now(), "event": event, "stage": st["stage"], **kw}
        with open(self.task_dir(st["id"]) / "log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def artifact(self, st: dict, stage: str) -> Path:
        return self.task_dir(st["id"]) / ARTIFACT[stage]

    # -- stage checks: return list of problems (empty = ready)
    def check_context(self) -> list[str]:
        f = self.dir / "context.md"
        if not f.exists():
            return ["`.rails/context.md` is missing — run `rails.py init`"]
        text = f.read_text(encoding="utf-8")
        problems = check_sections(text, CONTEXT_SECTIONS)
        m = re.search(r"Актуально на:\s*(\d{4}-\d{2}-\d{2})", strip_comments(text))
        if not m:
            problems.append("context: fill 'Актуально на: YYYY-MM-DD'")
        else:
            age = (dt.date.today() - dt.date.fromisoformat(m.group(1))).days
            if age > CONTEXT_MAX_AGE_DAYS:
                problems.append(f"context is {age} days old — re-read the code, refresh it, update the date")
        return problems

    def acceptance_criteria(self, st: dict) -> list[str]:
        f = self.artifact(st, "design")
        if not f.exists():
            return []
        body = sections(f.read_text(encoding="utf-8")).get("Критерии приёмки", "")
        return [m.group(1) for m in AC_LINE.finditer(body)]

    def check_design(self, st: dict) -> list[str]:
        f = self.artifact(st, "design")
        if not f.exists():
            return [f"{f.name} is missing"]
        text = f.read_text(encoding="utf-8")
        problems = check_sections(text, DESIGN_SECTIONS[st["lane"]])
        secs = sections(text)
        acs = list(AC_LINE.finditer(secs.get("Критерии приёмки", "")))
        if not acs:
            problems.append("acceptance criteria must be lines like '- AC-1: <fact> — проверка: <how>'")
        for m in acs:
            if "провер" not in m.group(2).lower():
                problems.append(f"{m.group(1)} has no 'проверка:' (how will we know it passed?)")
        if st["lane"] == "hotfix" and acs and not any("тест" in m.group(2).lower() or "test" in m.group(2).lower() for m in acs):
            problems.append("hotfix needs an AC with a regression test")
        if st["lane"] == "feature":
            alts = re.findall(r"^\s*(?:[-*]|\d+[.)])\s+\S", secs.get("Альтернативы", ""), re.M)
            if len(alts) < 2:
                problems.append("'## Альтернативы' needs at least 2 options as list items")
        return problems

    def plan_steps(self, st: dict) -> list[tuple[str, bool, str]]:
        f = self.artifact(st, "plan")
        if not f.exists():
            return []
        body = sections(f.read_text(encoding="utf-8")).get("Шаги", "")
        return [(m.group(2), m.group(1).lower() == "x", m.group(3)) for m in STEP_LINE.finditer(body)]

    def plan_files(self, st: dict) -> list[str]:
        files = []
        for _, _, rest in self.plan_steps(st):
            m = re.search(r"файлы\s*:\s*(.+)$", rest, re.I)
            if m:
                files += [x.strip().strip("`") for x in m.group(1).split(",") if x.strip()]
        return files

    def check_plan(self, st: dict) -> list[str]:
        f = self.artifact(st, "plan")
        if not f.exists():
            return [f"{f.name} is missing"]
        problems = check_sections(f.read_text(encoding="utf-8"), PLAN_SECTIONS[st["lane"]])
        steps = self.plan_steps(st)
        if not steps:
            problems.append("steps must be checkboxes like '- [ ] S1: <what> — файлы: a.py, b.py'")
        for sid, _, rest in steps:
            if not re.search(r"файлы\s*:\s*\S", rest, re.I):
                problems.append(f"{sid} does not list 'файлы:' — implementation scope must be explicit")
            what = re.split(r"\s+[—-]\s+файлы\s*:", rest, flags=re.I)[0].strip().lower()
            if re.match(r"(запуст|прогон|прогнать|выполнить\s+тест|проверить\s+тест|run\b|execute\b)", what):
                problems.append(f"{sid} is a run-only step ('{what[:40]}') — running checks belongs to verify; "
                                f"plan steps are changes (code, tests written)")
        return problems

    def check_implement(self, st: dict) -> list[str]:
        problems = []
        steps = self.plan_steps(st)
        open_steps = [sid for sid, done, _ in steps if not done]
        if open_steps:
            problems.append(f"plan steps not done: {', '.join(open_steps)} (tick '- [x]' only when really done)")
        changed = git_changed_files(self.root)
        if changed is not None:
            allowed = self.plan_files(st)
            outside = [p for p in changed if not p.startswith(".rails/")
                       and not any(fnmatch.fnmatch(p, a) or p == a for a in allowed)]
            if outside:
                problems.append("changed files outside the plan: " + ", ".join(outside)
                                + " — add them to the plan (`back plan`) or revert them")
        return problems

    def check_verify(self, st: dict) -> list[str]:
        f = self.artifact(st, "verify")
        if not f.exists():
            return [f"{f.name} is missing"]
        text = f.read_text(encoding="utf-8")
        required = VERIFY_SECTIONS + (["EVALs"] if st.get("ai") else [])
        problems = check_sections(text, required)
        body = sections(text).get("Критерии приёмки", "")
        lines = {m.group(1): m.group(2) for m in AC_LINE.finditer(body)}
        for ac in self.acceptance_criteria(st):
            line = lines.get(ac)
            if line is None:
                problems.append(f"{ac} from the design has no verification line")
            elif RISK_LINE.search(line):
                if not re.search(r"(человек|human)\s*:\s*[«\"].+[»\"]", line, re.I):
                    problems.append(f"{ac} RISK-ACCEPTED needs the human's words: "
                                    f"'- {ac}: RISK-ACCEPTED — <what is unverified, why> — человек: «<their words>»'")
            elif FAIL_WORDS.search(line) or not PASS_WORDS.search(line):
                problems.append(f"{ac} is not PASS with evidence: '{line.strip()}' (blocked check? "
                                f"show the human and, only if they accept the risk, write RISK-ACCEPTED)")
        return problems

    def check_release(self, st: dict) -> list[str]:
        f = self.artifact(st, "release")
        if not f.exists():
            return [f"{f.name} is missing"]
        return check_sections(f.read_text(encoding="utf-8"), RELEASE_SECTIONS, allow_na=True)

    def check_retro(self, st: dict) -> list[str]:
        f = self.artifact(st, "retro")
        if not f.exists():
            return [f"{f.name} is missing"]
        problems = check_sections(f.read_text(encoding="utf-8"), RETRO_SECTIONS)
        if "## Метрики" not in f.read_text(encoding="utf-8"):
            problems.append("run `rails.py metrics --write` to add the stage timing table")
        return problems

    def check(self, st: dict | None, stage: str) -> list[str]:
        if stage == "context":
            return self.check_context()
        if st is None:
            return ["no active task — `rails.py start`"]
        return getattr(self, f"check_{stage}")(st) if stage != "done" else []

    def gate(self, st: dict, stage: str) -> list[str]:
        problems = self.check(st, stage)
        if stage in HUMAN_GATES and stage not in st.get("approvals", {}):
            target = "design+plan" if stage == "design" and st["lane"] in COMBINED_LANES else stage
            problems.append(f"needs the human's explicit approval: show them the artifact, then "
                            f"`rails.py approve {target} --quote \"<their exact words>\"`")
        return problems


# ---------------------------------------------------------------- commands

NEXT_HINT = {
    "design": "fill {art} with the human (agent proposes options, human decides), then ask for approval"
              " (hotfix/small: also fill 02-plan.md and ask ONE combined approval → `approve design+plan`)",
    "plan": "fill {art}: small steps with explicit files, then ask for approval",
    "implement": "implement ONLY the plan steps, tick each '- [x]' when done; plan wrong? `rails.py back plan --reason ...`",
    "verify": "run the checks, record real output in {art}, map every AC to evidence, ask the human to review",
    "release": "fill {art} (or 'N/A — reason' per section)",
    "retro": "`rails.py metrics --write`, then fill {art}",
}


def copy_template(name: str, dest: Path, title: str, extra: str = "") -> None:
    if dest.exists():
        return
    text = (TEMPLATES / name).read_text(encoding="utf-8").replace("{title}", title)
    dest.write_text(text + extra, encoding="utf-8")


def materialize(r: Rails, st: dict) -> None:
    """Create the artifact template for the current stage, if any."""
    stage, lane, title = st["stage"], st["lane"], st["title"]
    d = r.task_dir(st["id"])
    if stage == "design":
        copy_template(f"design-{lane}.md", d / ARTIFACT["design"], title)
        if lane in COMBINED_LANES:  # short lanes draft the plan together with the design
            copy_template("plan-small.md", d / ARTIFACT["plan"], title)
    elif stage == "plan":
        copy_template("plan-feature.md" if lane == "feature" else "plan-small.md", d / ARTIFACT["plan"], title)
    elif stage == "verify":
        extra = (TEMPLATES / "evals-section.md").read_text(encoding="utf-8") if st.get("ai") else ""
        copy_template("verify.md", d / ARTIFACT["verify"], title, extra)
    elif stage == "release":
        copy_template("release.md", d / ARTIFACT["release"], title)
    elif stage == "retro":
        copy_template("retro.md", d / ARTIFACT["retro"], title)


def rel(r: Rails, p: Path) -> str:
    return os.path.relpath(p, Path.cwd())


def cmd_init(r: Rails, a) -> int:
    r.tasks.mkdir(parents=True, exist_ok=True)
    ctx = r.dir / "context.md"
    copy_template("context.md", ctx, "")
    print(f"rails ready at {r.dir}")
    problems = r.check_context()
    if problems:
        print(f"STAGE 0 (context) not ready — fill {rel(r, ctx)} from the real code and the human's answers:")
        for p in problems:
            print("  -", p)
        return 1
    print("context OK. Next: rails.py start \"<title>\" --lane hotfix|small|feature --why \"...\"")
    return 0


def cmd_start(r: Rails, a) -> int:
    if a.ai and a.lane != "feature":
        print("BLOCKED: an LLM/agent feature (--ai) is always lane 'feature' — model behaviour needs "
              "alternatives, failure policy and EVALs. Use --lane feature.")
        return 1
    ctx = r.check_context()
    if ctx:
        print("BLOCKED: stage 0 (project context) is not ready:")
        for p in ctx:
            print("  -", p)
        return 1
    slug = re.sub(r"[^a-z0-9а-я]+", "-", a.title.lower()).strip("-")[:40] or "task"
    tid = f"{dt.date.today():%Y%m%d}-{slug}"
    n = 2
    while r.task_dir(tid).exists():
        tid = f"{dt.date.today():%Y%m%d}-{slug}-{n}"
        n += 1
    r.task_dir(tid).mkdir(parents=True)
    st = {"id": tid, "title": a.title, "lane": a.lane, "lane_why": a.why, "ai": bool(a.ai),
          "stage": "design", "approvals": {}, "created": now()}
    r.save(st)
    (r.dir / "current").write_text(tid)
    r.log(st, "start", lane=a.lane, why=a.why)
    materialize(r, st)
    print(f"task {tid} started, lane={a.lane}{' (AI feature: EVALs required)' if a.ai else ''}")
    cmd_status(r, a)  # informational: the new stage's gate is expected to be blocked
    return 0


def cmd_status(r: Rails, a) -> int:
    st = r.load()
    ctx = r.check_context()
    if st is None or st["stage"] == "done":
        if st is not None:
            print(f"last task {st['id']} is done.")
        if ctx:
            print("STAGE 0 context NOT READY:")
            for p in ctx:
                print("  -", p)
            print("Next: fill .rails/context.md, then `rails.py start ...`")
            return 1
        print("No active task. Next: rails.py start \"<title>\" --lane hotfix|small|feature --why \"...\" [--ai]")
        return 0
    stage = st["stage"]
    idx = STAGES.index(stage)
    print(f"task: {st['id']} — {st['title']}")
    print(f"lane: {st['lane']}{' +AI' if st.get('ai') else ''}   stage {idx}/6: {stage.upper()}")
    print("track: " + " → ".join(s.upper() if s == stage else s for s in STAGES[1:-1]))
    if ctx:
        print("warning: context problems: " + "; ".join(ctx))
    problems = r.gate(st, stage)
    art = r.artifact(st, stage) if stage in ARTIFACT else None
    if problems:
        print("gate: BLOCKED")
        for p in problems:
            print("  -", p)
        hint = NEXT_HINT.get(stage, "").format(art=rel(r, art) if art else "")
        print(f"next: {hint}")
        print("code edits allowed: " + ("yes, plan files only" if stage == "implement" else "NO (not in implement stage)"))
        return 1
    print("gate: OPEN")
    print("next: rails.py advance")
    return 0


def cmd_check(r: Rails, a) -> int:
    st = r.load()
    stage = a.stage or (st["stage"] if st else "context")
    problems = r.check(st, stage)
    if problems:
        print(f"{stage}: NOT READY")
        for p in problems:
            print("  -", p)
        return 1
    print(f"{stage}: OK")
    return 0


def cmd_approve(r: Rails, a) -> int:
    st = r.load()
    if st is None:
        print("no active task")
        return 1
    stages = a.stage.split("+")
    if a.stage == "design+plan":
        if st["lane"] not in COMBINED_LANES:
            print(f"design+plan in one approval is only for lanes {sorted(COMBINED_LANES)}; "
                  f"'{st['lane']}' approves design and plan separately")
            return 1
    elif a.stage not in HUMAN_GATES:
        print(f"{a.stage} has no human gate (gated: {', '.join(sorted(HUMAN_GATES))})")
        return 1
    if stages[0] != st["stage"]:
        print(f"can only approve the current stage ({st['stage']})")
        return 1
    problems = [p for s in stages for p in r.check(st, s)]
    if problems:
        print("cannot approve, artifact not ready:")
        for p in problems:
            print("  -", p)
        return 1
    if len(a.quote.strip()) < 2:
        print("--quote must be the human's exact words")
        return 1
    if PRESSURE.search(a.quote) and not CONSENT.search(a.quote):
        print("REFUSED: this quote is pressure to skip, not approval of the shown artifact:\n"
              f"  \"{a.quote.strip()}\"\n"
              "Do not code. Reply with the derail protocol: one line on what is at stake, the artifact is "
              "already minimal, ask again for «да / поправь пункт N». See references/derail-protocol.md.")
        r.log(st, "approve-refused", quote=a.quote.strip())
        return 1
    for s in stages:
        st.setdefault("approvals", {})[s] = {"quote": a.quote.strip(), "at": now()}
    r.save(st)
    r.log(st, "approve", quote=a.quote.strip(), stages=stages)
    print(f"{a.stage} approved: \"{a.quote.strip()}\"")
    if len(stages) > 1:
        print("next: rails.py advance (design → plan), then rails.py advance again (plan → implement)")
    return 0


def cmd_advance(r: Rails, a) -> int:
    st = r.load()
    if st is None:
        print("no active task")
        return 1
    problems = r.gate(st, st["stage"])
    if problems:
        print(f"BLOCKED at {st['stage']}:")
        for p in problems:
            print("  -", p)
        return 1
    prev = st["stage"]
    st["stage"] = STAGES[STAGES.index(prev) + 1]
    r.save(st)
    r.log(st, "advance", **{"from": prev})
    materialize(r, st)
    print(f"{prev} → {st['stage']}")
    if st["stage"] != "done":
        cmd_status(r, a)  # informational: the new stage's gate is expected to be blocked
    return 0


def cmd_back(r: Rails, a) -> int:
    st = r.load()
    if st is None:
        print("no active task")
        return 1
    if STAGES.index(a.stage) >= STAGES.index(st["stage"]) or a.stage == "context":
        print(f"can only go back to an earlier task stage than {st['stage']}")
        return 1
    prev = st["stage"]
    st["stage"] = a.stage
    # approvals from the target stage onward are void: the human must re-confirm the changed artifact
    for s in STAGES[STAGES.index(a.stage):]:
        st.get("approvals", {}).pop(s, None)
    r.save(st)
    r.log(st, "back", **{"from": prev, "reason": a.reason})
    print(f"{prev} → back to {a.stage} ({a.reason}); approvals from {a.stage} on must be renewed")
    cmd_status(r, a)
    return 0


def cmd_lane(r: Rails, a) -> int:
    st = r.load()
    if st is None:
        print("no active task")
        return 1
    old, new = st["lane"], a.lane
    if st.get("ai") and new != "feature":
        print("an --ai task stays in lane 'feature'")
        return 1
    if LANES.index(new) < LANES.index(old) and not (a.quote and len(a.quote.strip()) >= 2):
        print(f"downgrade {old} → {new} needs the human's explicit words: --quote \"...\"")
        return 1
    st["lane"], st["lane_why"] = new, a.why
    r.save(st)
    r.log(st, "lane", **{"from": old, "to": new, "why": a.why, "quote": a.quote})
    stage_file = r.artifact(st, st["stage"]) if st["stage"] in ARTIFACT else None
    print(f"lane {old} → {new}. Artifacts already written stay; the current gate now uses '{new}' rules.")
    if stage_file and stage_file.exists():
        print(f"review {rel(r, stage_file)}: sections required for '{new}' may differ")
    cmd_status(r, a)
    return 0


def cmd_can_edit(r: Rails, a) -> int:
    st = r.load()
    denied = []
    for p in a.paths:
        path = Path(p).resolve()
        try:
            relp = path.relative_to(r.root.resolve()).as_posix()
        except ValueError:
            continue
        if relp.startswith(".rails/"):
            continue
        if st is None or st["stage"] == "done":
            denied.append(f"{relp}: no active task — `rails.py start` first")
        elif st["stage"] != "implement":
            denied.append(f"{relp}: stage is {st['stage']}, code edits only in implement")
        else:
            allowed = r.plan_files(st)
            if not any(fnmatch.fnmatch(relp, x) or relp == x for x in allowed):
                denied.append(f"{relp}: not in plan files ({', '.join(allowed)}) — `rails.py back plan --reason ...`")
    if denied:
        print("EDIT DENIED:")
        for d in denied:
            print("  -", d)
        return 1
    print("edit allowed")
    return 0


def stage_durations(r: Rails, st: dict) -> list[tuple[str, float]]:
    events = [json.loads(l) for l in (r.task_dir(st["id"]) / "log.jsonl").read_text().splitlines() if l.strip()]
    spent: dict[str, float] = {}
    cur, since = None, None
    for e in events:
        t = dt.datetime.fromisoformat(e["at"])
        if e["event"] == "start":
            cur, since = "design", t
        elif e["event"] in ("advance", "back") and cur:
            spent[cur] = spent.get(cur, 0) + (t - since).total_seconds()
            cur = STAGES[STAGES.index(e["from"]) + 1] if e["event"] == "advance" else e["stage"]
            since = t
    if cur and cur != "done" and since:
        spent[cur] = spent.get(cur, 0) + (dt.datetime.now(dt.timezone.utc) - since).total_seconds()
    return [(s, spent[s]) for s in STAGES if s in spent]


def fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"


def cmd_metrics(r: Rails, a) -> int:
    st = r.load()
    if st is None:
        print("no active task")
        return 1
    rows = stage_durations(r, st)
    total = sum(s for _, s in rows) or 1
    events = [json.loads(l) for l in (r.task_dir(st["id"]) / "log.jsonl").read_text().splitlines() if l.strip()]
    backs = [e for e in events if e["event"] == "back"]
    lines = ["| Этап | Время | Доля |", "|---|---|---|"]
    lines += [f"| {s} | {fmt(v)} | {v / total:.0%} |" for s, v in rows]
    worst = max(rows, key=lambda x: x[1])[0] if rows else "-"
    summary = f"Узкое место по времени: **{worst}**. Возвратов назад: {len(backs)}"
    if backs:
        summary += " (" + "; ".join(f"{b['from']}→{b['stage']}: {b.get('reason', '')}" for b in backs) + ")"
    table = "\n".join(lines) + "\n\n" + summary + "\n"
    print(table)
    if a.write:
        f = r.artifact(st, "retro")
        if not f.exists():
            print("retro file does not exist yet (reach the retro stage first)")
            return 1
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"\n## Метрики\n.*?(?=\n## |\Z)", "", text, flags=re.S)
        f.write_text(text.rstrip() + "\n\n## Метрики\n" + table, encoding="utf-8")
        print(f"written to {rel(r, f)}")
    return 0


def cmd_list(r: Rails, a) -> int:
    cur = r.current_id()
    for d in sorted(r.tasks.iterdir()) if r.tasks.exists() else []:
        st = r.load(d.name)
        if st:
            print(f"{'*' if d.name == cur else ' '} {st['id']}  [{st['lane']}]  {st['stage']}  — {st['title']}")
    return 0


def cmd_switch(r: Rails, a) -> int:
    if not r.load(a.task):
        print(f"no task {a.task}")
        return 1
    (r.dir / "current").write_text(a.task)
    return cmd_status(r, a)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rails.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="project root (default: nearest dir with .rails/, else cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("start")
    p.add_argument("title")
    p.add_argument("--lane", choices=LANES, required=True)
    p.add_argument("--why", required=True, help="why this lane (size, risk)")
    p.add_argument("--ai", action="store_true", help="task builds or changes an LLM/agent feature: EVALs required")
    sub.add_parser("status")
    p = sub.add_parser("check")
    p.add_argument("stage", nargs="?", choices=STAGES[:-1])
    p = sub.add_parser("approve")
    p.add_argument("stage", choices=sorted(HUMAN_GATES) + ["design+plan"])
    p.add_argument("--quote", required=True)
    sub.add_parser("advance")
    p = sub.add_parser("back")
    p.add_argument("stage", choices=STAGES[1:-1])
    p.add_argument("--reason", required=True)
    p = sub.add_parser("lane")
    p.add_argument("lane", choices=LANES)
    p.add_argument("--why", required=True)
    p.add_argument("--quote")
    p = sub.add_parser("can-edit")
    p.add_argument("paths", nargs="+")
    p = sub.add_parser("metrics")
    p.add_argument("--write", action="store_true")
    sub.add_parser("list")
    p = sub.add_parser("switch")
    p.add_argument("task")
    a = ap.parse_args(argv)

    if a.root:
        root = Path(a.root).resolve()
    else:
        root = find_root(Path.cwd()) or Path.cwd()
    if a.cmd != "init" and not (root / ".rails").is_dir():
        print(f"no .rails/ in {root} or its parents. Next: rails.py init (from the project root)")
        return 1
    return globals()[f"cmd_{a.cmd.replace('-', '_')}"](Rails(root), a)


if __name__ == "__main__":
    sys.exit(main())
