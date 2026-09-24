from __future__ import annotations

from pathlib import Path

from .context import AssemblyContext
from .renderer import AssemblyReport
from .service import AssemblyResult, AssemblyService


class OptionalDependencyError(ImportError):
    pass


def assemble_docx(template_path: str, output_path: str, context: AssemblyContext | dict, *,
                  clause_library=None, selected_clauses: dict[str, str] | None = None,
                  strict: bool = False) -> AssemblyResult:
    try:
        import docx
    except ImportError as exc:
        raise OptionalDependencyError(
            "DOCX support requires the optional dependency 'python-docx'. Install cactus-needle[docx]."
        ) from exc

    service = AssemblyService(clause_library=clause_library)
    context_obj = context if isinstance(context, AssemblyContext) else AssemblyContext(values=context)
    report = AssemblyReport()
    document = docx.Document(template_path)
    rendered_segments = []
    for paragraph in _iter_paragraphs(document):
        if not paragraph.text:
            continue
        result = service.assemble(
            paragraph.text,
            context_obj,
            selected_clauses=selected_clauses,
            strict=strict,
        )
        paragraph.text = result.text
        rendered_segments.append(result.text)
        report.merge(result.report)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return AssemblyResult(text="\n".join(rendered_segments), report=report, context=context_obj)


def _iter_paragraphs(document):
    for paragraph in getattr(document, "paragraphs", []):
        yield paragraph
    for table in getattr(document, "tables", []):
        for row in getattr(table, "rows", []):
            for cell in getattr(row, "cells", []):
                for paragraph in getattr(cell, "paragraphs", []):
                    yield paragraph
