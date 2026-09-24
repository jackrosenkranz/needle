from .clause_library import Clause, ClauseLibrary, InMemoryClauseLibrary, JSONClauseLibrary
from .context import AssemblyContext, normalize_field_name
from .docx import OptionalDependencyError, assemble_docx
from .intake import IntakeExtractionResult, extract_context_from_intake
from .renderer import (AssemblyReport, ClauseInsertionRecord, OmittedBlockRecord,
                       StrictRenderError, SubstitutionRecord, TemplateSyntaxError,
                       parse_template, render_template)
from .service import AssemblyResult, AssemblyService, HUMAN_REVIEW_WARNING, assemble_document

__all__ = [
    "AssemblyContext",
    "AssemblyReport",
    "AssemblyResult",
    "AssemblyService",
    "Clause",
    "ClauseInsertionRecord",
    "ClauseLibrary",
    "HUMAN_REVIEW_WARNING",
    "InMemoryClauseLibrary",
    "IntakeExtractionResult",
    "JSONClauseLibrary",
    "OmittedBlockRecord",
    "OptionalDependencyError",
    "StrictRenderError",
    "SubstitutionRecord",
    "TemplateSyntaxError",
    "assemble_docx",
    "assemble_document",
    "extract_context_from_intake",
    "normalize_field_name",
    "parse_template",
    "render_template",
]
