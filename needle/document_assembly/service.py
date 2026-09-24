from __future__ import annotations

from dataclasses import dataclass

from .clause_library import ClauseLibrary
from .context import AssemblyContext
from .renderer import AssemblyReport, render_template

HUMAN_REVIEW_WARNING = (
    "Generated documents require human review; Needle does not guarantee legal correctness."
)


@dataclass
class AssemblyResult:
    text: str
    report: AssemblyReport
    context: AssemblyContext


class AssemblyService:
    def __init__(self, clause_library: ClauseLibrary | None = None):
        self.clause_library = clause_library

    def assemble(self, template: str, context: AssemblyContext | dict, *,
                 selected_clauses: dict[str, str] | None = None,
                 strict: bool = False) -> AssemblyResult:
        context_obj = context if isinstance(context, AssemblyContext) else AssemblyContext(values=context)
        text, report = render_template(
            template,
            context_obj,
            strict=strict,
            selected_clauses=selected_clauses,
            clause_resolver=self.clause_library.get if self.clause_library is not None else None,
        )
        if HUMAN_REVIEW_WARNING not in report.warnings:
            report.warnings.append(HUMAN_REVIEW_WARNING)
        return AssemblyResult(text=text, report=report, context=context_obj)


def assemble_document(template: str, context: AssemblyContext | dict, *,
                      clause_library: ClauseLibrary | None = None,
                      selected_clauses: dict[str, str] | None = None,
                      strict: bool = False) -> AssemblyResult:
    return AssemblyService(clause_library=clause_library).assemble(
        template,
        context,
        selected_clauses=selected_clauses,
        strict=strict,
    )
