#!/usr/bin/env python3
"""Offline tests for the parts of the plugin that must not need a network.

The hook is the risky surface: it sits in every tool result, so it has to annotate
and never rewrite, stay silent when it has nothing to say, and never raise into a
turn. These tests pin that contract with the network stubbed out.

Run:  python tests/test_hook.py
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("besthumanizer_plugin", ROOT / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
sys.modules["besthumanizer_plugin"] = plugin
spec.loader.exec_module(plugin)

PROSE = (
    "Furthermore, it is important to note that the implementation of this comprehensive "
    "framework serves to facilitate enhanced operational efficiency across all departments, "
    "and moreover stakeholders must leverage synergies to ensure optimal outcomes overall. "
    "In addition, the utilization of robust methodologies will undoubtedly facilitate the "
    "realization of significant improvements in the domain of organizational performance, "
    "thereby enabling the achievement of strategic objectives."
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")
        print(f"FAIL {name} {detail}")


def with_score(score, tells=None):
    """Stub the remote scorer; only the hook's own decisions are under test."""
    plugin._call_tool = lambda name, args: {
        "human_probability": score,
        "detected_patterns": tells or ["7:ai-vocabulary"],
        "words": len(str(args.get("text", "")).split()),
    }


def main() -> int:
    # no key: the hook is silent, so unattended runs never wait on it
    os.environ.pop("BESTHUMANIZER_API_KEY", None)
    check("silent without a key", plugin._on_transform_tool_result("post_tweet", {"text": PROSE}, "ok") is None)

    os.environ["BESTHUMANIZER_API_KEY"] = "bh_test"
    check("key resolves", plugin._available() is True)

    # a shipping call that reads machine-written gets one appended line
    with_score(17)
    out = plugin._on_transform_tool_result("post_tweet", {"text": PROSE}, "posted: hello")
    check("annotates a low-scoring send", isinstance(out, str) and "[besthumanizer]" in out, repr(out)[:80])
    check("keeps the original result intact", isinstance(out, str) and out.startswith("posted: hello"))
    check("reports the score it was given", isinstance(out, str) and "17/100" in out)

    # already-human text is left alone
    with_score(88)
    check("silent when the text already reads human",
          plugin._on_transform_tool_result("post_tweet", {"text": PROSE}, "ok") is None)

    # non-shipping tools are not annotated
    with_score(12)
    check("ignores non-shipping tools",
          plugin._on_transform_tool_result("read_file", {"text": PROSE}, "ok") is None)

    # too short to mean anything
    check("ignores short text", plugin._on_transform_tool_result("post_tweet", {"text": "hi there"}, "ok") is None)

    # a scorer outage must not break the turn
    def boom(name, args):
        raise RuntimeError("network down")

    plugin._call_tool = boom
    check("never raises into a turn",
          plugin._on_transform_tool_result("post_tweet", {"text": PROSE}, "ok") is None)

    # the secret is read through Hermes's scope when it exists, not only os.environ
    os.environ.pop("BESTHUMANIZER_API_KEY", None)
    fake = type(sys)("agent.secret_scope")
    fake.get_secret = lambda name: "bh_from_scope" if name == "BESTHUMANIZER_API_KEY" else None
    pkg = type(sys)("agent")
    pkg.secret_scope = fake
    sys.modules["agent"] = pkg
    sys.modules["agent.secret_scope"] = fake
    check("reads the key through secret_scope", plugin._key() == "bh_from_scope", plugin._key())
    del sys.modules["agent"], sys.modules["agent.secret_scope"]

    print()
    if failures:
        print(f"{len(failures)} failed:", "; ".join(failures))
        return 1
    print("all hook contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
