"""Seeded generator for a SYNTHETIC labelled JUnit-XML corpus.

Nothing here is real CI data. It simulates N CI runs of a test suite spanning pytest,
TestNG/Surefire (with rerun elements) and jest-junit output, where each flaky test has a
ground-truth root cause and fails with messages drawn from hand-written templates.

    python -m benchmarks.gen_corpus --out benchmarks/_corpus --seed 1337
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET  # noqa: S405 - used for writing only

from .templates_dev import DEV, GENERIC, Tpl
from .templates_holdout import HOLDOUT

CAUSES = [
    "timing_wait",
    "stale_element",
    "order_dependence",
    "shared_state",
    "network_env",
    "data",
]
BASE_TS = 1_735_689_600  # 2025-01-01T00:00:00Z
RUN_GAP = 6 * 3600

_PAGES = ["Login", "Checkout", "Cart", "Search", "Profile", "Orders", "Admin", "Report", "Upload"]
_ACTS = [
    "submits form",
    "shows total",
    "filters results",
    "paginates",
    "saves draft",
    "exports csv",
    "applies coupon",
    "updates avatar",
    "deletes row",
    "sorts table",
    "opens modal",
]


@dataclass
class SimTest:
    test_id: str
    classname: str
    name: str
    lang: str
    kind: str  # stable | flaky | broken
    cause: str | None = None
    split: str | None = None
    ambiguous: bool = False
    p_fail: float = 0.0
    templates: tuple[Tpl, ...] = ()
    broken_from: int = 0


def _fill(s: str, rng: random.Random) -> str:
    return s.format(
        n=rng.randint(10, 9999),
        m=rng.randint(10, 9999),
        port=rng.choice([3000, 4200, 5432, 8080, 9222]) + rng.randint(0, 50),
        hex=rng.getrandbits(64).__format__("016x"),
        email=f"qa+{rng.randint(100, 99999)}@example.com",
    )


def _trace(t: Tpl, test: SimTest, msg: str, rng: random.Random) -> tuple[str, str]:
    """Return (message attr, trace text) shaped like each framework's output."""
    ln = rng.randint(20, 240)
    head = f"{t.exc}: {msg}".rstrip(": ")
    if t.lang == "py":
        body = (
            "Traceback (most recent call last):\n"
            f'  File "/home/runner/work/shop/shop/{test.classname.replace(".", "/")}.py", '
            f"line {ln}, in {test.name}\n    page.act()\n"
            + (t.frames + "\n" if t.frames else "")
            + head
        )
        return head.splitlines()[0] if head else t.exc, body
    if t.lang == "java":
        simple = test.classname.rsplit(".", 1)[-1]
        frames = (
            "\tat org.openqa.selenium.support.ui.FluentWait.timeoutException(FluentWait.java:262)\n"
            if "selenium" in t.exc
            else ""
        )
        body = (
            f"{head}\n{frames}"
            f"\tat com.acme.shop.pages.BasePage.click(BasePage.java:{ln})\n"
            f"\tat {test.classname}.{test.name}({simple}.java:{ln + 7})\n"
            "\tat java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)"
        )
        return f"{msg}" if msg else t.exc, body
    body = f"{head}\n    at Object.<anonymous> (tests/{test.classname}.test.js:{ln}:{rng.randint(3, 40)})"
    return "", body


def _plan(seed: int, n_stable: int, per_cause: int, n_broken: int, runs: int) -> list[SimTest]:
    rng = random.Random(seed)
    tests: list[SimTest] = []
    used: set[str] = set()

    def new_name(lang: str) -> tuple[str, str]:
        while True:
            page, act = rng.choice(_PAGES), rng.choice(_ACTS)
            if lang == "py":
                cn, nm = (
                    f"tests.ui.test_{page.lower()}",
                    f"test_{act.replace(' ', '_')}_{rng.randint(1, 99)}",
                )
            elif lang == "java":
                cn, nm = (
                    f"com.acme.shop.web.{page}Test",
                    f"{act.title().replace(' ', '')[0].lower()}{act.title().replace(' ', '')[1:]}{rng.randint(1, 99)}",
                )
            else:
                cn, nm = f"{page} page", f"{page} page {act} {rng.randint(1, 99)}"
            if f"{cn}::{nm}" not in used:
                used.add(f"{cn}::{nm}")
                return cn, nm

    langs = ["py", "java", "js"]
    for _ in range(n_stable):
        lang = rng.choices(langs, [0.4, 0.35, 0.25])[0]
        cn, nm = new_name(lang)
        tests.append(SimTest(f"{cn}::{nm}", cn, nm, lang, "stable"))
    for cause in CAUSES:
        dev = [t for t in DEV if t.cause == cause]
        hold = [t for t in HOLDOUT if t.cause == cause]
        for i in range(per_cause):
            use_hold = bool(hold) and i % 2 == 1
            pool = hold if use_hold else dev
            tpl = rng.choice(pool)
            extra = rng.choice(pool)
            cn, nm = new_name(tpl.lang)
            ambiguous = rng.random() < 0.15
            chosen: tuple[Tpl, ...] = (
                (tpl,) if extra.lang != tpl.lang or rng.random() < 0.6 else (tpl, extra)
            )
            if ambiguous:
                gen = [g for g in GENERIC if g.lang == tpl.lang]
                chosen = (rng.choice(gen),)
            tests.append(
                SimTest(
                    f"{cn}::{nm}",
                    cn,
                    nm,
                    tpl.lang,
                    "flaky",
                    cause,
                    "holdout" if use_hold else "dev",
                    ambiguous,
                    p_fail=round(rng.uniform(0.12, 0.45), 3),
                    templates=chosen,
                )
            )
    for _ in range(n_broken):
        lang = rng.choice(langs)
        cn, nm = new_name(lang)
        err = Tpl(
            "broken",
            lang,
            "AssertionError" if lang != "java" else "java.lang.AssertionError",
            "expected status 200 but got 500 from /api/v2/cart",
        )
        tests.append(
            SimTest(
                f"{cn}::{nm}",
                cn,
                nm,
                lang,
                "broken",
                templates=(err,),
                broken_from=rng.randint(runs - 9, runs - 4),
            )
        )
    return tests


def build(
    out: Path,
    seed: int = 1337,
    runs: int = 30,
    n_stable: int = 60,
    per_cause: int = 10,
    n_broken: int = 6,
    outage_run: int | None = None,
) -> dict[str, Any]:
    """Write the corpus to `out`; return the labels dict (also written to labels.json)."""
    rng = random.Random(seed * 7919 + 1)
    tests = _plan(seed, n_stable, per_cause, n_broken, runs)
    stable = [t for t in tests if t.kind == "stable"]
    outage_run = runs // 2 + 2 if outage_run is None else outage_run
    outage_victims = {t.test_id for t in rng.sample(stable, k=min(5, max(1, len(stable) // 5)))}
    outage = Tpl(
        "outage",
        "py",
        "requests.exceptions.ConnectionError",
        "HTTPConnectionPool(host='api.staging.internal', port=8080): Max retries exceeded "
        "with url: /health (Caused by NewConnectionError('Connection refused'))",
    )

    out.mkdir(parents=True, exist_ok=True)
    commits: list[str] = []
    manifest: list[dict[str, Any]] = []
    for r in range(runs):
        commit_idx = (r * 2) // 3  # every third run re-runs the previous commit
        while len(commits) <= commit_idx:
            commits.append(f"{rng.getrandbits(160):040x}")
        sha = commits[commit_idx]
        ts = BASE_TS + r * RUN_GAP
        run_dir = out / f"run-{r:03d}"
        run_dir.mkdir(exist_ok=True)
        suites: dict[str, ET.Element] = {}
        for lang, _fname, sname in (
            ("py", "pytest.xml", "pytest"),
            ("java", "surefire.xml", "com.acme.shop.web"),
            ("js", "jest.xml", "jest tests"),
        ):
            suites[lang] = ET.Element("testsuite", name=sname, timestamp=_iso(ts), tests="0")
            if lang == "java":
                props = ET.SubElement(suites[lang], "properties")
                ET.SubElement(props, "property", name="java.version", value="17.0.9")
        counts = dict.fromkeys(suites, 0)
        for t in tests:
            suite = suites[t.lang]
            counts[t.lang] += 1
            case = ET.SubElement(
                suite,
                "testcase",
                classname=t.classname if t.lang != "js" else t.classname,
                name=t.name,
                time=f"{rng.uniform(0.2, 9.0):.3f}",
            )
            fails = False
            tpl: Tpl | None = None
            if t.kind == "flaky" and rng.random() < t.p_fail:
                fails, tpl = True, rng.choice(t.templates)
            elif t.kind == "broken" and r >= t.broken_from:
                fails, tpl = True, t.templates[0]
            elif r == outage_run and t.test_id in outage_victims:
                fails, tpl = True, outage
            if not fails or tpl is None:
                continue
            msg = _fill(tpl.msg, rng)
            attr_msg, trace = _trace(tpl, t, msg, rng)
            attrs = {"message": attr_msg} if attr_msg else {}
            if t.lang == "java":
                attrs["type"] = tpl.exc
            retried_pass = t.kind == "flaky" and t.lang == "java" and rng.random() < 0.6
            dup_pass = t.kind == "flaky" and t.lang == "py" and rng.random() < 0.3
            if retried_pass:  # Surefire rerunFailingTestsCount: flakyFailure + final pass
                el = ET.SubElement(case, "flakyFailure", attrs)
                el.text = trace
            elif dup_pass:  # pytest-rerunfailures style: failed entry then a passing entry
                el = ET.SubElement(case, "failure", attrs)
                el.text = trace
                ET.SubElement(
                    suite,
                    "testcase",
                    classname=t.classname,
                    name=t.name,
                    time=f"{rng.uniform(0.2, 9.0):.3f}",
                )
            else:
                el = ET.SubElement(case, "failure", attrs)
                el.text = trace
        for lang, fname in (("py", "pytest.xml"), ("java", "surefire.xml"), ("js", "jest.xml")):
            suites[lang].set("tests", str(counts[lang]))
            ET.indent(suites[lang])
            ET.ElementTree(suites[lang]).write(
                run_dir / fname, encoding="utf-8", xml_declaration=True
            )
        (run_dir / "commit.txt").write_text(sha + "\n")
        manifest.append({"run_id": run_dir.name, "commit": sha, "timestamp": ts})

    labels: dict[str, Any] = {
        "seed": seed,
        "synthetic": True,
        "runs": manifest,
        "tests": {
            t.test_id: {
                "kind": t.kind,
                "cause": t.cause,
                "split": t.split,
                "ambiguous": t.ambiguous,
                "framework": {"py": "pytest", "java": "surefire", "js": "jest"}[t.lang],
            }
            for t in tests
        },
    }
    (out / "labels.json").write_text(json.dumps(labels, indent=1, sort_keys=True) + "\n")
    return labels


def _iso(ts: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("benchmarks/_corpus"))
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--stable", type=int, default=60)
    ap.add_argument("--per-cause", type=int, default=10)
    ap.add_argument("--broken", type=int, default=6)
    a = ap.parse_args()
    labels = build(a.out, a.seed, a.runs, a.stable, a.per_cause, a.broken)
    print(f"wrote {a.runs} runs, {len(labels['tests'])} tests to {a.out}")


if __name__ == "__main__":
    main()
