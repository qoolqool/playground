#!/usr/bin/env python3
"""
testbed — CLI for the Gated AI Testbed system.

Usage:
  testbed parse <spec-file>          # Parse a spec file through Gate 1
  testbed parse --stdin              # Read spec from stdin
  testbed validate <spec-file>       # Validate a spec file (no LLM)
  testbed feedback <feedback.json>   # Pretty-print a GateFeedback JSON
  testbed example success            # Show a success example
  testbed example failure            # Show a failure example
  testbed gate2 --spec <spec.json>   # Run Gate 2 — Code / Artifact Validator
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the testbed package is importable
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from testbed.contracts.spec import TestbedSpec
from testbed.contracts.feedback import GateFeedback, GateStatus
from testbed.gates.gate1_spec_parser import parse_spec, validate_spec
from testbed.gates.gate2_code_validator import validate_code, validate_code_from_file


def cmd_parse(args: argparse.Namespace) -> None:
    """Parse a spec file through Gate 1."""
    if args.stdin:
        raw_text = sys.stdin.read()
        source = "<stdin>"
    else:
        path = Path(args.spec_file)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        raw_text = path.read_text()
        source = str(path)

    print(f"📄 Parsing spec from: {source}")
    print(f"{'='*60}")

    # Resolve KB directories
    kb_dirs = []
    if args.kb_dir:
        for d in args.kb_dir:
            p = Path(d)
            if p.exists():
                kb_dirs.append(p)
            else:
                print(f"⚠️  KB directory not found: {p}", file=sys.stderr)

    spec, feedback = parse_spec(raw_text, use_llm=not args.no_llm, kb_dirs=kb_dirs or None, attempt_number=args.attempt)

    print(f"\n🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")
    print(f"🔄 Attempt: {feedback.attempt_number}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        print(f"{'─'*60}")
        for d in feedback.diagnostics:
            severity_icon = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️",
                "suggestion": "💡",
            }.get(d.severity.value, "•")
            loc = ""
            if d.location:
                loc = f" [{d.location.field}]"
            print(f"  {severity_icon} [{d.code}] {d.message}{loc}")
            if d.detail:
                print(f"     Detail: {d.detail[:200]}")
            if d.kb_refs:
                for ref in d.kb_refs:
                    print(f"     📚 KB: {ref.title} ({ref.path})")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("SUGGESTED ACTIONS (apply these in order):")
        print(f"{'─'*60}")
        for a in feedback.actions:
            priority_icon = "🔴" if a.priority <= 3 else "🟡" if a.priority <= 7 else "🟢"
            target = f" → {a.target_field}" if a.target_field else ""
            print(f"  {priority_icon} [{a.kind.value}] {a.description}{target}")
            if a.suggested_value:
                val_str = json.dumps(a.suggested_value, indent=2)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                print(f"     Suggested: {val_str}")

    if spec is not None:
        print(f"\n{'─'*60}")
        print("✅ VALIDATED TESTBED SPEC")
        print(f"{'─'*60}")
        print(f"  Name:        {spec.name}")
        print(f"  Version:     {spec.version}")
        print(f"  Description: {spec.description or '(none)'}")
        print(f"  Tags:        {', '.join(spec.tags) if spec.tags else '(none)'}")
        print(f"  Services:    {len(spec.services)}")
        for s in spec.services:
            mem = f" mem={s.mem_limit}" if s.mem_limit else ""
            hc = " ✓hc" if s.healthcheck else ""
            print(f"    • {s.name} ({s.image}){mem}{hc}")
        print(f"  Test Suites: {len(spec.test_suites)}")
        for ts in spec.test_suites:
            print(f"    • {ts.name} ({ts.path})")
        print(f"  Networks:    {len(spec.infrastructure.networks)}")
        print(f"  Guardrails:  require_mem_limit={spec.guardrails.require_mem_limit}, "
              f"require_healthcheck={spec.guardrails.require_healthcheck}")
    else:
        print(f"\n{'─'*60}")
        print("❌ SPEC VALIDATION FAILED")
        print(f"{'─'*60}")

    # Also write feedback JSON
    if args.output:
        output_path = Path(args.output)
        feedback_json = feedback.model_dump(mode="json", exclude_none=True)
        output_path.write_text(json.dumps(feedback_json, indent=2))
        print(f"\n💾 Feedback written to: {output_path}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a JSON spec file and cross-reference against KB."""
    path = Path(args.spec_file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    raw_text = path.read_text()

    # Try to parse as JSON
    try:
        spec_dict = json.loads(raw_text)
    except json.JSONDecodeError:
        print("Spec file is not valid JSON. Use 'testbed parse' for markdown specs.")
        sys.exit(1)

    # Resolve KB directories
    kb_dirs = []
    if args.kb_dir:
        for d in args.kb_dir:
            p = Path(d)
            if p.exists():
                kb_dirs.append(p)
            else:
                print(f"⚠️  KB directory not found: {p}", file=sys.stderr)

    # Use validate_spec (validates + runs KB cross-reference)
    validated, feedback = validate_spec(spec_dict, kb_dirs=kb_dirs or None, attempt_number=args.attempt)

    print(f"🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")
    print(f"🔄 Attempt: {feedback.attempt_number}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        for d in feedback.diagnostics:
            severity_icon = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️",
                "suggestion": "💡",
            }.get(d.severity.value, "•")
            loc = f" [{d.location.field}]" if d.location else ""
            print(f"  {severity_icon} [{d.code}] {d.message}{loc}")
            if d.kb_refs:
                for ref in d.kb_refs:
                    print(f"     📚 KB: {ref.title} ({ref.path})")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("SUGGESTED ACTIONS (apply these in order):")
        print(f"{'─'*60}")
        for a in feedback.actions:
            priority_icon = "🔴" if a.priority <= 3 else "🟡" if a.priority <= 7 else "🟢"
            target = f" → {a.target_field}" if a.target_field else ""
            print(f"  {priority_icon} [{a.kind.value}] {a.description}{target}")
            if a.suggested_value:
                val_str = json.dumps(a.suggested_value, indent=2)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                print(f"     Suggested: {val_str}")

    if validated:
        print(f"\n{'─'*60}")
        print(f"✅ VALIDATED TESTBED SPEC")
        print(f"{'─'*60}")
        print(f"  Name:        {validated.name}")
        print(f"  Version:     {validated.version}")
        print(f"  Description: {validated.description or '(none)'}")
        print(f"  Tags:        {', '.join(validated.tags) if validated.tags else '(none)'}")
        print(f"  Services:    {len(validated.services)}")
        for s in validated.services:
            mem = f" mem={s.mem_limit}" if s.mem_limit else ""
            hc = " ✓hc" if s.healthcheck else ""
            print(f"    • {s.name} ({s.image}){mem}{hc}")
        print(f"  Test Suites: {len(validated.test_suites)}")
        print(f"  Networks:    {len(validated.infrastructure.networks)}")
    else:
        print(f"\n{'─'*60}")
        print("❌ SPEC VALIDATION FAILED")
        print(f"{'─'*60}")
        sys.exit(1)


def cmd_feedback(args: argparse.Namespace) -> None:
    """Pretty-print a GateFeedback JSON file."""
    path = Path(args.feedback_json)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text())
    feedback = GateFeedback(**data)

    print(f"🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        for d in feedback.diagnostics:
            print(f"  [{d.code}] {d.severity.value}: {d.message}")
            if d.location:
                print(f"     at {d.location.field}")
            if d.detail:
                print(f"     {d.detail[:200]}")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("ACTIONS:")
        for a in feedback.actions:
            print(f"  [{a.kind.value}] {a.description}")


def cmd_example(args: argparse.Namespace) -> None:
    """Show an example spec file."""
    examples_dir = Path(__file__).parent / "examples"
    if args.example == "success":
        path = examples_dir / "success_spec.md"
    elif args.example == "failure":
        path = examples_dir / "failure_spec.md"
    else:
        print(f"Unknown example: {args.example}. Use 'success' or 'failure'.", file=sys.stderr)
        sys.exit(1)

    if path.exists():
        print(path.read_text())
    else:
        print(f"Example not found: {path}", file=sys.stderr)
        sys.exit(1)


def cmd_check(args: argparse.Namespace) -> None:
    """Check the testbed environment and report status."""
    import importlib
    import os

    print("🔍 Gated AI Testbed — Environment Check")
    print(f"{'='*50}")

    # Python version
    print(f"\n🐍 Python: {sys.version}")

    # Package root
    pkg_root = str(Path(__file__).resolve().parent.parent)
    print(f"📦 Package root: {pkg_root}")
    print(f"   PYTHONPATH: {os.environ.get('PYTHONPATH', '(not set)')}")

    # Dependencies
    deps = [
        ("pydantic", "pydantic"),
        ("pytest", "pytest"),
    ]
    print(f"\n📚 Dependencies:")
    for name, mod in deps:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "(unknown)")
            print(f"  ✅ {name} v{ver}")
        except ImportError:
            print(f"  ❌ {name} — not installed")

    # Testbed package
    print(f"\n🧩 Testbed package:")
    try:
        import testbed
        print(f"  ✅ testbed found at {testbed.__file__}")
        print(f"  ✅ Contracts: TestbedSpec, GateFeedback")
        print(f"  ✅ Gate 1: Spec Parser")
    except ImportError:
        print(f"  ❌ testbed package not importable")
        print(f"     Run: export PYTHONPATH={pkg_root}:$PYTHONPATH")

    # Ollama
    print(f"\n🤖 Ollama (LLM extraction):")
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("models", [])
            if models:
                print(f"  ✅ Ollama reachable ({len(models)} model(s) loaded)")
                for m in models:
                    print(f"     • {m.get('name', 'unknown')}")
            else:
                print(f"  ⚠️  Ollama reachable but no models loaded")
                print(f"     LLM extraction will fall back to keyword parser")
    except Exception as exc:
        print(f"  ⚠️  Ollama not reachable: {exc}")
        print(f"     LLM extraction will fall back to keyword parser")

    # KB directories
    print(f"\n📖 Knowledgebase directories:")
    kb_candidates = [
        Path("/workspace/scdlt/knowledgebase"),
        Path("/workspace/knowledgebase"),
    ]
    found_kb = False
    for kb in kb_candidates:
        if kb.exists():
            n_files = len(list(kb.rglob("*.md")))
            print(f"  ✅ {kb} ({n_files} entries)")
            found_kb = True
        else:
            print(f"  ❌ {kb} — not found")
    if not found_kb:
        print(f"  ℹ️  No KB directories found. KB cross-reference will be skipped.")

    # Tests
    print(f"\n🧪 Tests:")
    test_dir = Path(__file__).parent / "tests"
    if test_dir.exists():
        print(f"  ✅ Test directory: {test_dir}")
        print(f"     Run: make test  or  python3 -m pytest tests/ -v")
    else:
        print(f"  ❌ Test directory not found")

    print(f"\n{'='*50}")
    print("✅ Check complete")


def cmd_gate2(args: argparse.Namespace) -> None:
    """Run Gate 2 — Code / Artifact Validator."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    workspace_root = Path(args.workspace)
    if not workspace_root.exists():
        print(f"Error: workspace root not found: {workspace_root}", file=sys.stderr)
        sys.exit(1)

    compose_path = Path(args.compose) if args.compose else None
    if compose_path and not compose_path.exists():
        print(f"Error: compose file not found: {compose_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Gate 2 — Code / Artifact Validator")
    print(f"{'='*60}")
    print(f"📄 Spec:       {spec_path}")
    print(f"📁 Workspace:  {workspace_root}")
    if compose_path:
        print(f"📋 Compose:    {compose_path}")
    print()

    feedback = validate_code_from_file(
        spec_path=spec_path,
        workspace_root=workspace_root,
        compose_path=compose_path,
        attempt_number=args.attempt,
    )

    print(f"🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")
    print(f"🔄 Attempt: {feedback.attempt_number}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        print(f"{'─'*60}")
        for d in feedback.diagnostics:
            severity_icon = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️",
                "suggestion": "💡",
            }.get(d.severity.value, "•")
            loc = f" [{d.location.field}]" if d.location else ""
            src = f" ({d.location.source})" if d.location and d.location.source else ""
            print(f"  {severity_icon} [{d.code}] {d.message}{loc}{src}")
            if d.detail:
                print(f"     Detail: {d.detail[:200]}")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("SUGGESTED ACTIONS (apply these in order):")
        print(f"{'─'*60}")
        for a in feedback.actions:
            priority_icon = "🔴" if a.priority <= 3 else "🟡" if a.priority <= 7 else "🟢"
            target = f" → {a.target_field}" if a.target_field else ""
            print(f"  {priority_icon} [{a.kind.value}] {a.description}{target}")
            if a.suggested_value:
                val_str = json.dumps(a.suggested_value, indent=2)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                print(f"     Suggested: {val_str}")

    if feedback.status == GateStatus.pass_:
        print(f"\n{'─'*60}")
        print("✅ GATE 2 PASSED — Implementation is consistent with spec")
        print(f"{'─'*60}")
    elif feedback.status == GateStatus.fail:
        print(f"\n{'─'*60}")
        print("❌ GATE 2 FAILED — Fix issues and re-run")
        print(f"{'─'*60}")
    else:
        print(f"\n{'─'*60}")
        print(f"⚠️  GATE 2 STATUS: {feedback.status.value}")
        print(f"{'─'*60}")

    # Write feedback JSON if requested
    if args.output:
        output_path = Path(args.output)
        feedback_json = feedback.model_dump(mode="json", exclude_none=True)
        output_path.write_text(json.dumps(feedback_json, indent=2))
        print(f"\n💾 Feedback written to: {output_path}")

    if feedback.is_fail():
        sys.exit(1)


def cmd_gate2_help() -> str:
    return "Run Gate 2 — Code / Artifact Validator"


def cmd_gate3(args: argparse.Namespace) -> None:
    """Run Gate 3 — Security & Policy Guardrails."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    workspace_root = Path(args.workspace)
    if not workspace_root.exists():
        print(f"Error: workspace root not found: {workspace_root}", file=sys.stderr)
        sys.exit(1)

    compose_path = Path(args.compose) if args.compose else None
    if compose_path and not compose_path.exists():
        print(f"Error: compose file not found: {compose_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Gate 3 — Security & Policy Guardrails")
    print(f"{'='*60}")
    print(f"📄 Spec:       {spec_path}")
    print(f"📁 Workspace:  {workspace_root}")
    if compose_path:
        print(f"📋 Compose:    {compose_path}")
    print()

    from testbed.gates.gate3_guardrails import validate_guardrails_from_file

    feedback = validate_guardrails_from_file(
        spec_path=spec_path,
        workspace_root=workspace_root,
        compose_path=compose_path,
        attempt_number=args.attempt,
    )

    print(f"🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")
    print(f"🔄 Attempt: {feedback.attempt_number}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        print(f"{'─'*60}")
        for d in feedback.diagnostics:
            severity_icon = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️",
                "suggestion": "💡",
            }.get(d.severity.value, "•")
            loc = f" [{d.location.field}]" if d.location else ""
            src = f" ({d.location.source})" if d.location and d.location.source else ""
            print(f"  {severity_icon} [{d.code}] {d.message}{loc}{src}")
            if d.detail:
                print(f"     Detail: {d.detail[:200]}")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("SUGGESTED ACTIONS (apply these in order):")
        print(f"{'─'*60}")
        for a in feedback.actions:
            priority_icon = "🔴" if a.priority <= 3 else "🟡" if a.priority <= 7 else "🟢"
            target = f" → {a.target_field}" if a.target_field else ""
            print(f"  {priority_icon} [{a.kind.value}] {a.description}{target}")
            if a.suggested_value:
                val_str = json.dumps(a.suggested_value, indent=2)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                print(f"     Suggested: {val_str}")

    if feedback.status == GateStatus.pass_:
        print(f"\n{'─'*60}")
        print("✅ GATE 3 PASSED — Security posture is acceptable under policy")
        print(f"{'─'*60}")
    elif feedback.status == GateStatus.fail:
        print(f"\n{'─'*60}")
        print("❌ GATE 3 FAILED — Fix security/policy issues and re-run")
        print(f"{'─'*60}")
    else:
        print(f"\n{'─'*60}")
        print(f"⚠️  GATE 3 STATUS: {feedback.status.value}")
        print(f"{'─'*60}")

    # Write feedback JSON if requested
    if args.output:
        output_path = Path(args.output)
        feedback_json = feedback.model_dump(mode="json", exclude_none=True)
        output_path.write_text(json.dumps(feedback_json, indent=2))
        print(f"\n💾 Feedback written to: {output_path}")

    if feedback.is_fail():
        sys.exit(1)


def cmd_gate3_help() -> str:
    return "Run Gate 3 — Security & Policy Guardrails"


def cmd_gate4(args: argparse.Namespace) -> None:
    """Run Gate 4 — Runtime & Integration Verification."""
    workspace_root = Path(args.workspace)
    if not workspace_root.exists():
        print(f"Error: workspace root not found: {workspace_root}", file=sys.stderr)
        sys.exit(1)

    compose_path = Path(args.compose) if args.compose else None
    if compose_path and not compose_path.exists():
        print(f"Error: compose file not found: {compose_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Gate 4 — Runtime & Integration Verification")
    print(f"{'='*60}")
    print(f"📁 Workspace:  {workspace_root}")
    if compose_path:
        print(f"📋 Compose:    {compose_path}")
    print(f"⏭  Skip up:    {args.skip_up}")
    print(f"⏱  E2E timeout: {args.e2e_timeout}s")
    print()

    from testbed.gates.gate4_runtime import validate_runtime_from_cli

    feedback = validate_runtime_from_cli(
        workspace_root=workspace_root,
        compose_path=compose_path,
        skip_up=args.skip_up,
        e2e_timeout=args.e2e_timeout,
        attempt_number=args.attempt,
    )

    print(f"🔍 Gate: {feedback.gate_id} (v{feedback.gate_version})")
    print(f"📊 Status: {feedback.status.value}")
    print(f"⏱  Duration: {feedback.duration_ms}ms")
    print(f"📋 Diagnostics: {len(feedback.diagnostics)}")
    print(f"🔧 Actions: {len(feedback.actions)}")
    print(f"🔄 Attempt: {feedback.attempt_number}")

    if feedback.diagnostics:
        print(f"\n{'─'*60}")
        print("DIAGNOSTICS:")
        print(f"{'─'*60}")
        for d in feedback.diagnostics:
            severity_icon = {
                "critical": "🚨",
                "error": "❌",
                "warning": "⚠️",
                "info": "ℹ️",
                "suggestion": "💡",
            }.get(d.severity.value, "•")
            loc = f" [{d.location.field}]" if d.location else ""
            src = f" ({d.location.source})" if d.location and d.location.source else ""
            print(f"  {severity_icon} [{d.code}] {d.message}{loc}{src}")
            if d.detail:
                # Truncate detail for display
                detail_short = d.detail[:300]
                if len(d.detail) > 300:
                    detail_short += "..."
                print(f"     Detail: {detail_short}")

    if feedback.actions:
        print(f"\n{'─'*60}")
        print("SUGGESTED ACTIONS (apply these in order):")
        print(f"{'─'*60}")
        for a in feedback.actions:
            priority_icon = "🔴" if a.priority <= 3 else "🟡" if a.priority <= 7 else "🟢"
            target = f" → {a.target_field}" if a.target_field else ""
            print(f"  {priority_icon} [{a.kind.value}] {a.description}{target}")

    if feedback.status == GateStatus.pass_:
        print(f"\n{'─'*60}")
        print("✅ GATE 4 PASSED — Stack is running, healthy, and integration tests pass")
        print(f"{'─'*60}")
    elif feedback.status == GateStatus.fail:
        print(f"\n{'─'*60}")
        print("❌ GATE 4 FAILED — Fix runtime issues and re-run")
        print(f"{'─'*60}")
    else:
        print(f"\n{'─'*60}")
        print(f"⚠️  GATE 4 STATUS: {feedback.status.value}")
        print(f"{'─'*60}")

    # Write feedback JSON if requested
    if args.output:
        output_path = Path(args.output)
        feedback_json = feedback.model_dump(mode="json", exclude_none=True)
        output_path.write_text(json.dumps(feedback_json, indent=2))
        print(f"\n💾 Feedback written to: {output_path}")

    if feedback.is_fail():
        sys.exit(1)


def cmd_gate4_help() -> str:
    return "Run Gate 4 — Runtime & Integration Verification"


def cmd_init(args: argparse.Namespace) -> None:
    """Create a new testbed spec from a template."""
    name = args.name
    output_path = Path(args.output) if args.output else Path(f"{name}-spec.json")

    template = {
        "name": name,
        "version": "0.1.0",
        "description": f"Testbed: {name}",
        "tags": [],
        "services": [
            {
                "name": "app",
                "image": "my-app:latest",
                "ports": [{"host": 8080, "container": 8080}],
                "mem_limit": "512M",
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8080/health"], "interval": "15s"},
                "networks": ["app-net"],
                "labels": {"project": name, "managed-by": "testbed"},
            },
            {
                "name": "db",
                "image": "postgres:16-alpine",
                "ports": [{"host": 5432, "container": 5432}],
                "mem_limit": "512M",
                "healthcheck": {"test": ["CMD", "pg_isready"], "interval": "10s"},
                "networks": ["app-net"],
                "labels": {"project": name, "managed-by": "testbed"},
            },
        ],
        "test_suites": [
            {
                "name": "smoke",
                "path": "tests/smoke/",
                "framework": "pytest",
                "required_services": ["app", "db"],
                "timeout_seconds": 60,
            },
        ],
        "infrastructure": {
            "networks": {
                "app-net": {"driver": "bridge"},
            },
        },
        "constraints": {
            "memory_per_service": {
                "app": "512M",
                "db": "512M",
            },
            "max_containers": 10,
        },
        "guardrails": {
            "require_mem_limit": True,
            "require_healthcheck": True,
            "no_host_network": True,
            "no_privileged": True,
        },
    }

    import json
    output_path.write_text(json.dumps(template, indent=2))
    print(f"✅ Created testbed spec: {output_path}")
    print(f"   Name: {name}")
    print(f"   Services: 2 (app, db)")
    print(f"   Test suites: 1 (smoke)")
    print(f"")
    print(f"   Next steps:")
    print(f"     1. Edit {output_path} to match your testbed")
    print(f"     2. Validate: testbed validate {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gated AI Testbed CLI — create, validate, and iterate on testbed specs",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Check the testbed environment")
    p_check.set_defaults(func=cmd_check)

    # init
    p_init = sub.add_parser("init", help="Create a new testbed spec from a template")
    p_init.add_argument("name", help="Name for the new testbed")
    p_init.add_argument("-o", "--output", help="Output path (default: <name>-spec.json)")
    p_init.set_defaults(func=cmd_init)

    # parse
    p_parse = sub.add_parser("parse", help="Parse a spec file through Gate 1")
    p_parse.add_argument("spec_file", nargs="?", help="Path to spec file (markdown)")
    p_parse.add_argument("--stdin", action="store_true", help="Read spec from stdin")
    p_parse.add_argument("--no-llm", action="store_true", help="Skip LLM extraction (use keyword fallback)")
    p_parse.add_argument("--kb-dir", action="append", default=[], help="Knowledgebase directory to cross-reference (can be repeated)")
    p_parse.add_argument("-o", "--output", help="Write feedback JSON to file")
    p_parse.add_argument("--attempt", type=int, default=1, help="Attempt number for iteration tracking")
    p_parse.set_defaults(func=cmd_parse)

    # validate
    p_val = sub.add_parser("validate", help="Validate a JSON spec file and cross-reference against KB")
    p_val.add_argument("spec_file", help="Path to JSON spec file")
    p_val.add_argument("--kb-dir", action="append", default=[], help="Knowledgebase directory to cross-reference (can be repeated)")
    p_val.add_argument("--attempt", type=int, default=1, help="Attempt number for iteration tracking")
    p_val.set_defaults(func=cmd_validate)

    # feedback
    p_fb = sub.add_parser("feedback", help="Pretty-print a GateFeedback JSON")
    p_fb.add_argument("feedback_json", help="Path to feedback JSON file")
    p_fb.set_defaults(func=cmd_feedback)

    # example
    p_ex = sub.add_parser("example", help="Show an example spec file")
    p_ex.add_argument("example", choices=["success", "failure"])
    p_ex.set_defaults(func=cmd_example)

    # gate2
    p_g2 = sub.add_parser("gate2", help="Run Gate 2 — Code / Artifact Validator")
    p_g2.add_argument("--spec", required=True, help="Path to the approved TestbedSpec JSON file")
    p_g2.add_argument("--workspace", default="/workspace", help="Root directory of the implementation (default: /workspace)")
    p_g2.add_argument("--compose", help="Path to Docker Compose file (auto-detect if not specified)")
    p_g2.add_argument("-o", "--output", help="Write feedback JSON to file")
    p_g2.add_argument("--attempt", type=int, default=1, help="Attempt number for iteration tracking")
    p_g2.set_defaults(func=cmd_gate2)

    # gate3
    p_g3 = sub.add_parser("gate3", help="Run Gate 3 — Security & Policy Guardrails")
    p_g3.add_argument("--spec", required=True, help="Path to the approved TestbedSpec JSON file")
    p_g3.add_argument("--workspace", default="/workspace", help="Root directory of the implementation (default: /workspace)")
    p_g3.add_argument("--compose", help="Path to Docker Compose file (auto-detect if not specified)")
    p_g3.add_argument("-o", "--output", help="Write feedback JSON to file")
    p_g3.add_argument("--attempt", type=int, default=1, help="Attempt number for iteration tracking")
    p_g3.set_defaults(func=cmd_gate3)

    # gate4
    p_g4 = sub.add_parser("gate4", help="Run Gate 4 — Runtime & Integration Verification")
    p_g4.add_argument("--workspace", default="/workspace", help="Root directory of the implementation (default: /workspace)")
    p_g4.add_argument("--compose", help="Path to Docker Compose file (auto-detect if not specified)")
    p_g4.add_argument("--skip-up", action="store_true", help="Skip automatic stack bring-up if not running")
    p_g4.add_argument("--e2e-timeout", type=int, default=300, help="Timeout in seconds for E2E happy-flow test (default: 300)")
    p_g4.add_argument("-o", "--output", help="Write feedback JSON to file")
    p_g4.add_argument("--attempt", type=int, default=1, help="Attempt number for iteration tracking")
    p_g4.set_defaults(func=cmd_gate4)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
