from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from .clause_library import JSONClauseLibrary
from .context import AssemblyContext
from .docx import assemble_docx
from .intake import extract_context_from_intake
from .service import assemble_document


def render_template_cli(args) -> None:
    template = Path(args.template).read_text()
    context = AssemblyContext.from_json(Path(args.context).read_text())
    clauses = _load_clause_library(args.clauses)
    selected = _load_json_dict(args.selected_clauses)
    result = assemble_document(template, context, clause_library=clauses,
                               selected_clauses=selected, strict=args.strict)
    if args.output:
        Path(args.output).write_text(result.text)
    else:
        print(result.text)
    if args.report:
        Path(args.report).write_text(json.dumps(result.report.to_dict(), indent=2))


def extract_intake_cli(args) -> None:
    import needle

    schema = _load_schema(args.schema)
    existing = AssemblyContext.from_json(Path(args.context).read_text()) if args.context else AssemblyContext()
    result = extract_context_from_intake(
        needle.extract,
        Path(args.intake).read_text() if Path(args.intake).exists() else args.intake,
        schema,
        existing_context=existing,
        allow_overwrite_confirmed=args.allow_overwrite_confirmed,
        strict=not args.no_strict,
    )
    print(json.dumps(result.to_dict(), indent=2, default=str))


def assemble_docx_cli(args) -> None:
    context = AssemblyContext.from_json(Path(args.context).read_text())
    clauses = _load_clause_library(args.clauses)
    selected = _load_json_dict(args.selected_clauses)
    assemble_docx(args.template, args.output, context, clause_library=clauses,
                  selected_clauses=selected, strict=args.strict)
    print(args.output)


def _load_schema(target: str) -> Any:
    module_name, _, attr_name = target.partition(":")
    if not module_name or not attr_name:
        raise SystemExit("schema must be provided as module.path:ClassName")
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _load_clause_library(path: str | None):
    return JSONClauseLibrary(path) if path else None


def _load_json_dict(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text())
