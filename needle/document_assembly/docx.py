from __future__ import annotations

from pathlib import Path

from .context import AssemblyContext
from .renderer import AssemblyReport, TemplateSyntaxError, parse_template, render_template
from .service import AssemblyResult, HUMAN_REVIEW_WARNING


class OptionalDependencyError(ImportError):
    pass


FORMAT_WARNING = (
    "DOCX assembly preserves paragraph and basic table structure, but rewrites paragraph runs and may lose inline styling."
)


def assemble_docx(template_path: str, output_path: str, context: AssemblyContext | dict, *,
                  clause_library=None, selected_clauses: dict[str, str] | None = None,
                  strict: bool = False) -> AssemblyResult:
    """Assemble a DOCX while preserving paragraph and basic table structure.

    This helper renders each paragraph or table-cell paragraph independently.
    That keeps paragraph/table boundaries intact, but because `python-docx` only
    offers whole-paragraph text replacement cheaply, inline run formatting may be
    rewritten during substitution.
    """
    try:
        import docx
    except ImportError as exc:
        raise OptionalDependencyError(
            "DOCX support requires the optional dependency 'python-docx'. Install cactus-needle[docx]."
        ) from exc

    context_obj = context if isinstance(context, AssemblyContext) else AssemblyContext(values=context)
    report = AssemblyReport()
    document = docx.Document(template_path)
    _validate_paragraph_boundaries(document)
    rendered_segments = []
    clause_resolver = clause_library.get if clause_library is not None else None
    for paragraph in _iter_paragraphs(document):
        if not paragraph.text:
            continue
        text, paragraph_report = render_template(
            paragraph.text,
            context_obj,
            strict=strict,
            selected_clauses=selected_clauses,
            clause_resolver=clause_resolver,
        )
        paragraph.text = text
        rendered_segments.append(text)
        report.merge(paragraph_report)
    for warning in (HUMAN_REVIEW_WARNING, FORMAT_WARNING):
        if warning not in report.warnings:
            report.warnings.append(warning)
    report.warnings = list(dict.fromkeys(report.warnings))
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


def _validate_paragraph_boundaries(document) -> None:
    for paragraph in _iter_paragraphs(document):
        text = getattr(paragraph, "text", "")
        if not text or not any(token in text for token in ("[[if", "[[endif]]", "[[clause", "{", "[")):
            continue
        try:
            parse_template(text)
        except TemplateSyntaxError as exc:
            boundary_case = (
                ("[[if" in text and "[[endif]]" not in text)
                or ("[[endif]]" in text and "[[if" not in text)
                or ("{" in text and "}" not in text)
                or ("[" in text and "]" not in text)
            )
            if boundary_case:
                raise ValueError(
                    "DOCX assembly does not support template directives that span paragraphs or cells; "
                    f"rewrite the template so each directive is self-contained within one paragraph ({exc})."
                ) from exc
            raise
