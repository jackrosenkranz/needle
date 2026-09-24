import json
from pathlib import Path
import sys
import types

import pytest


def test_context_round_trip_and_normalized_lookup():
    from needle.document_assembly import AssemblyContext

    context = AssemblyContext(
        values={"CLIENT_NAME": "Ada Lovelace"},
        aliases={"CLIENT_NAME": ["Client Name"]},
        metadata={"matter_id": "M-1"},
        confirmed={"CLIENT_NAME": True},
        choices={"pronouns": "they"},
        required_fields=["CLIENT_NAME"],
    )

    clone = AssemblyContext.from_json(context.to_json())

    assert clone.get("client name") == "Ada Lovelace"
    assert clone.is_confirmed("Client Name") is True
    assert clone.metadata["matter_id"] == "M-1"
    assert clone.choices["pronouns"] == "they"


def test_render_template_normalizes_aliases_and_choices():
    from needle.document_assembly import AssemblyContext, render_template

    context = AssemblyContext(
        values={"CLIENT_NAME": "Ada Lovelace", "pronouns": "they"},
        aliases={"CLIENT_NAME": ["Client Name"]},
    )

    text, report = render_template("Dear [Client Name], [he/she/they].", context)

    assert text == "Dear Ada Lovelace, they."
    assert [item.placeholder for item in report.substitutions] == ["[Client Name]", "[he/she/they]"]
    assert not report.unresolved_fields


def test_optional_and_conditional_blocks_are_deterministic():
    from needle.document_assembly import AssemblyContext, render_template

    context = AssemblyContext(values={"CLIENT_NAME": "Ada", "tier": "gold", "active": False})
    template = (
        "Dear [CLIENT_NAME],"
        "{ You selected [OPTIONAL_SERVICE].}"
        "[[if ACTIVE]] Active.[[endif]]"
        "[[if TIER == 'gold']] Gold tier.[[endif]]"
    )

    text, report = render_template(template, context)

    assert text == "Dear Ada, Gold tier."
    assert [item.kind for item in report.omitted_blocks] == ["optional", "conditional"]
    assert report.omitted_blocks[0].reason == "missing variables"
    assert report.omitted_blocks[1].expression == "ACTIVE"


def test_malformed_template_reports_in_non_strict_mode():
    from needle.document_assembly import render_template

    text, report = render_template("[[if CLIENT_NAME]]Hello", {"CLIENT_NAME": "Ada"})

    assert text == "[[if CLIENT_NAME]]Hello"
    assert report.malformed_blocks
    assert "missing [[endif]]" in report.malformed_blocks[0]


def test_strict_render_raises_for_unresolved_and_missing_required_fields():
    from needle.document_assembly import AssemblyContext, StrictRenderError, render_template

    context = AssemblyContext(values={"CLIENT_NAME": "Ada"}, required_fields=["CASE_NUMBER"])

    with pytest.raises(StrictRenderError) as exc_info:
        render_template("[CLIENT_NAME] [MISSING]", context, strict=True)

    report = exc_info.value.report
    assert "missing" in report.unresolved_fields
    assert report.missing_required_fields == ["CASE_NUMBER"]


def test_clause_library_lookup_and_assembly_report():
    from needle.document_assembly import Clause, InMemoryClauseLibrary, assemble_document

    clauses = InMemoryClauseLibrary([
        Clause(
            clause_id="termination",
            title="Termination",
            tags=("closing", "standard"),
            text="Signed by [CLIENT_NAME].",
            version="2026-09",
        )
    ])

    result = assemble_document(
        "Agreement\n[[clause closing]]",
        {"CLIENT_NAME": "Ada"},
        clause_library=clauses,
        selected_clauses={"closing": "termination"},
    )

    assert result.text == "Agreement\nSigned by Ada."
    assert result.report.inserted_clauses[0].clause_id == "termination"
    assert clauses.get("termination").title == "Termination"
    assert [clause.clause_id for clause in clauses.by_tag("closing")] == ["termination"]
    assert [clause.clause_id for clause in clauses.search("termination closing", limit=1)] == ["termination"]


def test_json_clause_library_and_embedding_ranking(tmp_path):
    from needle.document_assembly import JSONClauseLibrary

    payload = {
        "clauses": [
            {"clause_id": "a", "title": "Alpha", "tags": ["general"], "text": "alpha text"},
            {"clause_id": "b", "title": "Beta", "tags": ["special"], "text": "beta text"},
        ]
    }
    path = tmp_path / "clauses.json"
    path.write_text(json.dumps(payload))

    class FakeEmbedder:
        def embed(self, text):
            return [1.0, 0.0] if "alpha" in text else [0.0, 1.0]

    library = JSONClauseLibrary(path, embedding_client=FakeEmbedder())

    assert [item.clause_id for item in library.search("alpha", limit=1)] == ["a"]
    assert [item.clause_id for item in library.search("beta", tags=["special"], limit=1)] == ["b"]


def test_extract_context_from_intake_preserves_confirmed_values():
    from needle.document_assembly import AssemblyContext, extract_context_from_intake

    class FakeModel:
        def __init__(self, **payload):
            self.payload = payload

        def model_dump(self):
            return dict(self.payload)

    class FakeNeedle:
        def extract(self, text, schema, strict=True):
            assert strict is True
            assert schema is FakeModel
            assert text == "Ada can be reached at ada@example.com"
            return FakeModel(CLIENT_NAME="New Name", EMAIL="ada@example.com")

    existing = AssemblyContext(
        values={"CLIENT_NAME": "Confirmed Name"},
        confirmed={"CLIENT_NAME": True},
    )

    result = extract_context_from_intake(
        FakeNeedle(),
        "Ada can be reached at ada@example.com",
        FakeModel,
        existing_context=existing,
    )

    assert result.context.values["CLIENT_NAME"] == "Confirmed Name"
    assert result.context.values["EMAIL"] == "ada@example.com"
    assert result.preserved_confirmed_fields == ["CLIENT_NAME"]
    assert result.conflicts["CLIENT_NAME"]["proposed"] == "New Name"


def test_render_template_cli_writes_output_and_report(tmp_path):
    from needle.document_assembly.cli import render_template_cli
    from types import SimpleNamespace

    template = tmp_path / "template.txt"
    context = tmp_path / "context.json"
    output = tmp_path / "output.txt"
    report = tmp_path / "report.json"
    template.write_text("Dear [CLIENT_NAME]")
    context.write_text(json.dumps({"values": {"CLIENT_NAME": "Ada"}}))

    render_template_cli(SimpleNamespace(
        template=str(template),
        context=str(context),
        clauses=None,
        selected_clauses=None,
        output=str(output),
        report=str(report),
        strict=False,
    ))

    assert output.read_text() == "Dear Ada"
    assert json.loads(report.read_text())["substitutions"][0]["field"] == "CLIENT_NAME"


def test_cli_help_mentions_document_assembly_commands():
    from needle.cli import HELP

    assert "render-template" in HELP
    assert "extract-intake" in HELP
    assert "assemble-docx" in HELP


def test_docx_requires_optional_dependency(monkeypatch, tmp_path):
    from needle.document_assembly import OptionalDependencyError, assemble_docx

    monkeypatch.setitem(sys.modules, "docx", None)

    with pytest.raises(OptionalDependencyError, match="python-docx"):
        assemble_docx(str(tmp_path / "template.docx"), str(tmp_path / "out.docx"), {"CLIENT_NAME": "Ada"})


def test_docx_assembly_uses_fake_docx_module(monkeypatch, tmp_path):
    from needle.document_assembly import assemble_docx

    class Paragraph:
        def __init__(self, text):
            self.text = text

    class Cell:
        def __init__(self, text):
            self.paragraphs = [Paragraph(text)]

    class Row:
        def __init__(self, *texts):
            self.cells = [Cell(text) for text in texts]

    class Table:
        def __init__(self):
            self.rows = [Row("Cell [CLIENT_NAME]")]

    class FakeDocument:
        def __init__(self, _path):
            self.paragraphs = [Paragraph("Paragraph [CLIENT_NAME]")]
            self.tables = [Table()]
            self.saved = None

        def save(self, path):
            self.saved = path
            Path(path).write_text("saved")

    fake_module = types.SimpleNamespace(Document=FakeDocument)
    monkeypatch.setitem(sys.modules, "docx", fake_module)

    result = assemble_docx(str(tmp_path / "template.docx"), str(tmp_path / "out.docx"), {"CLIENT_NAME": "Ada"})

    assert "Paragraph Ada" in result.text
    assert "Cell Ada" in result.text
    assert (tmp_path / "out.docx").read_text() == "saved"


def test_extract_intake_cli_passes_strict_flag(monkeypatch, tmp_path, capsys):
    from needle.document_assembly.cli import extract_intake_cli
    from types import SimpleNamespace

    package = tmp_path / "schemas_for_cli.py"
    package.write_text("class DemoSchema: pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    calls = {}

    def fake_extract(*args, **kwargs):
        calls["kwargs"] = kwargs
        return {"CLIENT_NAME": "Ada"}

    fake_needle = types.SimpleNamespace(extract=fake_extract)
    monkeypatch.setitem(sys.modules, "needle", fake_needle)

    intake = tmp_path / "intake.txt"
    intake.write_text("hello")

    extract_intake_cli(SimpleNamespace(
        schema="schemas_for_cli:DemoSchema",
        intake=str(intake),
        context=None,
        allow_overwrite_confirmed=False,
        no_strict=True,
    ))

    captured = capsys.readouterr().out
    assert calls["kwargs"]["strict"] is False
    assert json.loads(captured)["applied_values"]["CLIENT_NAME"] == "Ada"


def test_clause_slot_requires_explicit_selection():
    from needle.document_assembly import Clause, InMemoryClauseLibrary, assemble_document

    library = InMemoryClauseLibrary([
        Clause(clause_id="closing", title="Closing", tags=("closing",), text="Signed.")
    ])

    result = assemble_document("[[clause closing]]", {}, clause_library=library)

    assert result.text == ""
    assert result.report.omitted_blocks[0].reason == "no clause selected"


def test_docx_rejects_cross_paragraph_directives(monkeypatch, tmp_path):
    from needle.document_assembly import assemble_docx

    class Paragraph:
        def __init__(self, text):
            self.text = text

    class FakeDocument:
        def __init__(self, _path):
            self.paragraphs = [Paragraph("[[if CLIENT_NAME]]"), Paragraph("Ada[[endif]]")]
            self.tables = []

        def save(self, path):
            Path(path).write_text("saved")

    fake_module = types.SimpleNamespace(Document=FakeDocument)
    monkeypatch.setitem(sys.modules, "docx", fake_module)

    with pytest.raises(ValueError, match="span paragraphs"):
        assemble_docx(str(tmp_path / "template.docx"), str(tmp_path / "out.docx"), {"CLIENT_NAME": "Ada"})


def test_alias_only_canonical_name_still_resolves_value():
    from needle.document_assembly import AssemblyContext

    context = AssemblyContext(
        values={"client_name": "Ada"},
        aliases={"CLIENT NAME": ["Primary Client"]},
    )

    assert context.get("Primary Client") == "Ada"


def test_recursive_clause_adds_warning_in_non_strict_mode():
    from needle.document_assembly import Clause, InMemoryClauseLibrary, assemble_document

    library = InMemoryClauseLibrary([
        Clause(clause_id="loop", title="Loop", tags=("loop",), text="[[clause loop]]")
    ])

    result = assemble_document("Start [[clause loop]]", {}, clause_library=library,
                               selected_clauses={"loop": "loop"})

    assert "recursive clause reference for loop" in result.report.warnings


def test_optional_block_omits_recursive_clause_in_non_strict_mode():
    from needle.document_assembly import Clause, InMemoryClauseLibrary, assemble_document

    library = InMemoryClauseLibrary([
        Clause(clause_id="loop", title="Loop", tags=("loop",), text="[[clause loop]]")
    ])

    result = assemble_document("Before{[[clause loop]]}After", {}, clause_library=library,
                               selected_clauses={"loop": "loop"})

    assert result.text == "BeforeAfter"
    assert result.report.omitted_blocks[0].kind == "optional"


def test_docx_preserves_local_template_syntax_errors(monkeypatch, tmp_path):
    from needle.document_assembly import assemble_docx, TemplateSyntaxError

    class Paragraph:
        def __init__(self, text):
            self.text = text

    class FakeDocument:
        def __init__(self, _path):
            self.paragraphs = [Paragraph("[[unknown TEST]]")]
            self.tables = []

        def save(self, path):
            Path(path).write_text("saved")

    fake_module = types.SimpleNamespace(Document=FakeDocument)
    monkeypatch.setitem(sys.modules, "docx", fake_module)

    with pytest.raises(TemplateSyntaxError, match="unsupported directive"):
        assemble_docx(str(tmp_path / "template.docx"), str(tmp_path / "out.docx"), {"CLIENT_NAME": "Ada"})


def test_extract_context_from_intake_falls_back_when_signature_unavailable(monkeypatch):
    from needle.document_assembly import extract_context_from_intake
    import needle.document_assembly.intake as intake_module

    class Extractor:
        def __call__(self, text, schema, **kwargs):
            return {"CLIENT_NAME": "Ada", "strict": kwargs.get("strict")}

    original = intake_module.inspect.signature

    def explode(_target):
        raise ValueError("no signature")

    monkeypatch.setattr(intake_module.inspect, "signature", explode)
    try:
        result = extract_context_from_intake(Extractor(), "hello", dict, strict=False)
    finally:
        monkeypatch.setattr(intake_module.inspect, "signature", original)

    assert result.extracted_values["CLIENT_NAME"] == "Ada"
    assert result.extracted_values["strict"] is False
