from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable

from .context import AssemblyContext, normalize_field_name


class TemplateSyntaxError(ValueError):
    pass


class StrictRenderError(ValueError):
    def __init__(self, report: "AssemblyReport"):
        self.report = report
        issues = []
        if report.unresolved_fields:
            issues.append("unresolved fields: " + ", ".join(report.unresolved_fields))
        if report.malformed_blocks:
            issues.append("malformed blocks: " + "; ".join(report.malformed_blocks))
        if report.missing_required_fields:
            issues.append("missing required fields: " + ", ".join(report.missing_required_fields))
        super().__init__("; ".join(issues) or "strict rendering failed")


@dataclass
class SubstitutionRecord:
    field: str
    placeholder: str
    value: str


@dataclass
class OmittedBlockRecord:
    kind: str
    expression: str
    reason: str


@dataclass
class ClauseInsertionRecord:
    slot: str
    clause_id: str
    title: str | None = None


@dataclass
class AssemblyReport:
    substitutions: list[SubstitutionRecord] = field(default_factory=list)
    omitted_blocks: list[OmittedBlockRecord] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    malformed_blocks: list[str] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    inserted_clauses: list[ClauseInsertionRecord] = field(default_factory=list)

    def merge(self, other: "AssemblyReport") -> None:
        self.substitutions.extend(other.substitutions)
        self.omitted_blocks.extend(other.omitted_blocks)
        self.inserted_clauses.extend(other.inserted_clauses)
        for warning in other.warnings:
            if warning not in self.warnings:
                self.warnings.append(warning)
        for target, source in (
            (self.unresolved_fields, other.unresolved_fields),
            (self.malformed_blocks, other.malformed_blocks),
            (self.missing_required_fields, other.missing_required_fields),
        ):
            for item in source:
                if item not in target:
                    target.append(item)

    def to_dict(self) -> dict:
        return {
            "substitutions": [item.__dict__ for item in self.substitutions],
            "omitted_blocks": [item.__dict__ for item in self.omitted_blocks],
            "unresolved_fields": list(self.unresolved_fields),
            "warnings": list(self.warnings),
            "malformed_blocks": list(self.malformed_blocks),
            "missing_required_fields": list(self.missing_required_fields),
            "inserted_clauses": [item.__dict__ for item in self.inserted_clauses],
        }


@dataclass
class TextNode:
    value: str


@dataclass
class VariableNode:
    raw: str


@dataclass
class ChoiceNode:
    raw: str
    options: list[str]


@dataclass
class OptionalNode:
    raw: str
    children: list[object]


@dataclass
class ConditionalNode:
    expression: str
    field: str
    expected: object | None
    children: list[object]


@dataclass
class ClauseNode:
    slot: str


class _Parser:
    def __init__(self, template: str):
        self.template = template
        self.index = 0

    def parse(self, *, stop_tokens: tuple[str, ...] = (), in_optional: bool = False) -> list[object]:
        nodes = []
        buffer = []
        while self.index < len(self.template):
            if stop_tokens and any(self.template.startswith(token, self.index) for token in stop_tokens):
                break
            if self.template.startswith("[[", self.index):
                directive = self._read_directive()
                if directive == "endif":
                    raise TemplateSyntaxError("unexpected [[endif]]")
                if directive.startswith("if "):
                    if buffer:
                        nodes.append(TextNode("".join(buffer)))
                        buffer = []
                    nodes.append(self._parse_conditional(directive[3:].strip(), in_optional=in_optional))
                    continue
                if directive.startswith("clause "):
                    if buffer:
                        nodes.append(TextNode("".join(buffer)))
                        buffer = []
                    slot = directive[7:].strip()
                    if not slot:
                        raise TemplateSyntaxError("empty [[clause]] directive")
                    nodes.append(ClauseNode(slot=slot))
                    continue
                raise TemplateSyntaxError(f"unsupported directive [[{directive}]]")
            char = self.template[self.index]
            if char == "[":
                if buffer:
                    nodes.append(TextNode("".join(buffer)))
                    buffer = []
                nodes.append(self._parse_bracket())
                continue
            if char == "{":
                if in_optional:
                    raise TemplateSyntaxError("nested optional blocks are not supported")
                if buffer:
                    nodes.append(TextNode("".join(buffer)))
                    buffer = []
                nodes.append(self._parse_optional())
                continue
            if char == "}":
                break
            buffer.append(char)
            self.index += 1
        if buffer:
            nodes.append(TextNode("".join(buffer)))
        return nodes

    def _read_directive(self) -> str:
        end = self.template.find("]]", self.index)
        if end == -1:
            raise TemplateSyntaxError("unclosed directive block")
        raw = self.template[self.index + 2:end].strip()
        self.index = end + 2
        return raw

    def _parse_bracket(self) -> object:
        end = self.template.find("]", self.index)
        if end == -1:
            raise TemplateSyntaxError("unclosed [variable] placeholder")
        raw = self.template[self.index + 1:end]
        self.index = end + 1
        options = [item.strip() for item in raw.split("/")]
        if len(options) > 1 and all(options):
            return ChoiceNode(raw=raw, options=options)
        return VariableNode(raw=raw)

    def _parse_optional(self) -> OptionalNode:
        start = self.index
        self.index += 1
        children = self.parse(stop_tokens=("}",), in_optional=True)
        if self.index >= len(self.template) or self.template[self.index] != "}":
            raise TemplateSyntaxError("unclosed optional block")
        self.index += 1
        return OptionalNode(raw=self.template[start:self.index], children=children)

    def _parse_conditional(self, expression: str, *, in_optional: bool) -> ConditionalNode:
        field, expected = _parse_condition(expression)
        children = self.parse(stop_tokens=("[[endif]]",), in_optional=in_optional)
        if not self.template.startswith("[[endif]]", self.index):
            raise TemplateSyntaxError(f"missing [[endif]] for condition '{expression}'")
        self.index += len("[[endif]]")
        return ConditionalNode(expression=expression, field=field, expected=expected, children=children)


def parse_template(template: str) -> list[object]:
    parser = _Parser(template)
    nodes = parser.parse()
    if parser.index != len(template):
        raise TemplateSyntaxError("template parsing did not consume the full input")
    return nodes


def render_template(template: str, context: AssemblyContext | dict, *, strict: bool = False,
                    selected_clauses: dict[str, str] | None = None,
                    clause_resolver: Callable[[str], object | None] | None = None,
                    report: AssemblyReport | None = None,
                    clause_stack: set[str] | None = None) -> tuple[str, AssemblyReport]:
    context = context if isinstance(context, AssemblyContext) else AssemblyContext(values=context)
    report = report or AssemblyReport()
    for field in context.required_fields:
        if not context.has_value(field):
            resolved = context.resolve_name(field) or field
            if resolved not in report.missing_required_fields:
                report.missing_required_fields.append(resolved)
    try:
        nodes = parse_template(template)
    except TemplateSyntaxError as exc:
        report.malformed_blocks.append(str(exc))
        report.warnings.append(str(exc))
        if strict:
            raise StrictRenderError(report) from exc
        return template, report
    text = _render_nodes(nodes, context, report, strict=strict,
                         selected_clauses=selected_clauses or {},
                         clause_resolver=clause_resolver,
                         clause_stack=clause_stack or set())
    if strict and (report.unresolved_fields or report.malformed_blocks or report.missing_required_fields):
        raise StrictRenderError(report)
    return text, report


def _render_nodes(nodes: list[object], context: AssemblyContext, report: AssemblyReport, *, strict: bool,
                  selected_clauses: dict[str, str],
                  clause_resolver: Callable[[str], object | None] | None,
                  clause_stack: set[str]) -> str:
    output = []
    for node in nodes:
        if isinstance(node, TextNode):
            output.append(node.value)
        elif isinstance(node, VariableNode):
            value = context.get(node.raw)
            if value is None:
                normalised = normalize_field_name(node.raw)
                if normalised not in report.unresolved_fields:
                    report.unresolved_fields.append(normalised)
                if not strict:
                    report.warnings.append(f"unresolved placeholder [{node.raw}]")
                    output.append(f"[{node.raw}]")
            else:
                report.substitutions.append(SubstitutionRecord(
                    field=context.resolve_name(node.raw) or node.raw,
                    placeholder=f"[{node.raw}]",
                    value=str(value),
                ))
                output.append(str(value))
        elif isinstance(node, ChoiceNode):
            value = _resolve_choice(node, context)
            if value is None:
                if strict:
                    token = normalize_field_name(node.raw)
                    if token not in report.unresolved_fields:
                        report.unresolved_fields.append(token)
                else:
                    report.warnings.append(f"unresolved choice [{node.raw}]")
                    output.append(f"[{node.raw}]")
            else:
                report.substitutions.append(SubstitutionRecord(
                    field="choice",
                    placeholder=f"[{node.raw}]",
                    value=value,
                ))
                output.append(value)
        elif isinstance(node, OptionalNode):
            nested = AssemblyReport()
            try:
                nested_text = _render_nodes(node.children, context, nested, strict=True,
                                            selected_clauses=selected_clauses,
                                            clause_resolver=clause_resolver,
                                            clause_stack=set(clause_stack))
            except StrictRenderError as exc:
                nested = exc.report
                nested_text = ""
            if nested.unresolved_fields or nested.malformed_blocks or not nested_text.strip():
                reason = "missing variables" if nested.unresolved_fields else (
                    nested.malformed_blocks[0] if nested.malformed_blocks else "condition evaluated false or empty"
                )
                report.omitted_blocks.append(OmittedBlockRecord(
                    kind="optional",
                    expression=node.raw,
                    reason=reason,
                ))
            else:
                report.merge(nested)
                output.append(nested_text)
        elif isinstance(node, ConditionalNode):
            if _condition_matches(node, context):
                output.append(_render_nodes(node.children, context, report, strict=strict,
                                            selected_clauses=selected_clauses,
                                            clause_resolver=clause_resolver,
                                            clause_stack=clause_stack))
            else:
                report.omitted_blocks.append(OmittedBlockRecord(
                    kind="conditional",
                    expression=node.expression,
                    reason="condition evaluated false",
                ))
        elif isinstance(node, ClauseNode):
            slot = node.slot
            clause_id = _resolve_clause_id(slot, selected_clauses)
            if clause_id is None:
                report.omitted_blocks.append(OmittedBlockRecord(
                    kind="clause",
                    expression=slot,
                    reason="no clause selected",
                ))
                continue
            if clause_resolver is None:
                report.warnings.append(f"clause resolver missing for {slot}")
                report.omitted_blocks.append(OmittedBlockRecord(
                    kind="clause",
                    expression=slot,
                    reason="clause resolver missing",
                ))
                continue
            if clause_id in clause_stack:
                message = f"recursive clause reference for {clause_id}"
                if message not in report.malformed_blocks:
                    report.malformed_blocks.append(message)
                if message not in report.warnings:
                    report.warnings.append(message)
                if strict:
                    raise StrictRenderError(report)
                continue
            clause = clause_resolver(clause_id)
            if clause is None:
                report.omitted_blocks.append(OmittedBlockRecord(
                    kind="clause",
                    expression=slot,
                    reason=f"clause '{clause_id}' not found",
                ))
                continue
            report.inserted_clauses.append(ClauseInsertionRecord(
                slot=slot,
                clause_id=getattr(clause, "clause_id", clause_id),
                title=getattr(clause, "title", None),
            ))
            clause_stack.add(clause_id)
            nested_text, nested_report = render_template(
                getattr(clause, "text", str(clause)),
                context,
                strict=strict,
                selected_clauses=selected_clauses,
                clause_resolver=clause_resolver,
                report=AssemblyReport(),
                clause_stack=clause_stack,
            )
            clause_stack.remove(clause_id)
            report.merge(nested_report)
            output.append(nested_text)
    return "".join(output)


def _resolve_choice(node: ChoiceNode, context: AssemblyContext) -> str | None:
    options = {normalize_field_name(option): option for option in node.options}
    for key in (node.raw, normalize_field_name(node.raw), "pronouns"):
        candidate = context.choices.get(key)
        if candidate is None:
            continue
        match = options.get(normalize_field_name(candidate))
        if match is not None:
            return match
    pronouns = context.get("pronouns")
    if pronouns is not None:
        match = options.get(normalize_field_name(pronouns))
        if match is not None:
            return match
    return None


def _resolve_clause_id(slot: str, selected_clauses: dict[str, str]) -> str | None:
    if slot in selected_clauses:
        return selected_clauses[slot]
    needle = normalize_field_name(slot)
    for key, value in selected_clauses.items():
        if normalize_field_name(key) == needle:
            return value
    return None


def _parse_condition(expression: str) -> tuple[str, object | None]:
    if not expression:
        raise TemplateSyntaxError("empty if condition")
    if "==" not in expression:
        return expression.strip(), None
    left, right = expression.split("==", 1)
    field = left.strip()
    if not field:
        raise TemplateSyntaxError(f"invalid condition '{expression}'")
    return field, _parse_literal(right.strip())


def _parse_literal(value: str) -> object:
    if not value:
        raise TemplateSyntaxError("empty comparison value")
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("none", "null"):
        return None
    try:
        return ast.literal_eval(value)
    except Exception:
        return value


def _condition_matches(node: ConditionalNode, context: AssemblyContext) -> bool:
    actual = context.get(node.field)
    if node.expected is None and "==" not in node.expression:
        return bool(actual)
    return actual == node.expected
