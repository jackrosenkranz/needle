# Document assembly

Needle includes an independent, Pathagoras-inspired document assembly foundation in `needle.document_assembly`.
It is a fresh implementation of publicly described concepts such as bracket variables, choice variables,
optional text, clause libraries, structured intake extraction, deterministic assembly, and optional DOCX output.
It does **not** copy proprietary Pathagoras code, branding, manuals, or UI.

## Syntax

Needle keeps rendering deterministic and conservative:

- Variables: `[CLIENT_NAME]`, `[Client Name]`
- Choice variables: `[he/she/they]`
- Optional blocks: `{Optional text with [VARIABLES].}`
- Conditionals: `[[if FIELD]]...[[endif]]`
- Equality conditionals: `[[if FIELD == VALUE]]...[[endif]]`
- Clause insertion: `[[clause closing]]`

Field lookup normalizes whitespace, underscores, punctuation, and case, so `CLIENT_NAME`, `Client Name`,
and `client-name` can all resolve to the same value or alias.

### Optional block rules

Optional blocks are omitted when:

1. a variable inside the block is missing,
2. a nested conditional renders no text, or
3. the block is otherwise empty after deterministic rendering.

Nested optional blocks are intentionally unsupported to avoid ambiguous brace parsing.

## Deterministic rendering vs AI-assisted extraction

Needle separates two steps:

1. **AI-assisted extraction** uses `needle.extract()` or a `Needle` instance to propose structured matter data.
2. **Deterministic rendering** uses `needle.document_assembly.render_template()` or `AssemblyService` to assemble text.

The model can help extract structured data, but it does not directly rewrite the final document during assembly.
That boundary is intentional for auditability and reproducibility.

## Context model

`AssemblyContext` stores:

- `values`: canonical field values
- `aliases`: alternative field names
- `metadata`: matter-level metadata
- `confirmed`: fields already confirmed by a human
- `choices`: choice selections such as pronouns
- `required_fields`: fields that must be present in strict mode

`AssemblyContext` supports `to_dict()`, `to_json()`, `from_dict()`, and `from_json()`.

## Clause libraries

Use `InMemoryClauseLibrary` or `JSONClauseLibrary` for deterministic clause retrieval.
ID and tag lookup work offline. Query search falls back to deterministic token matching, and embeddings are optional.

## DOCX support

DOCX assembly is optional. Install the extra first:

```sh
pip install "cactus-needle[docx]"
```

If `python-docx` is absent, DOCX helpers raise a clear optional dependency error while the core package remains importable. The current helper preserves paragraph and basic table structure, but rewrites paragraph runs, so inline styling may need manual review after assembly.

## CLI examples

```sh
needle render-template --template template.txt --context matter.json --output output.txt --report report.json
needle extract-intake --schema myapp.schemas:IntakeModel --intake intake.txt --context matter.json
needle assemble-docx --template template.docx --context matter.json --output assembled.docx
```

## Privacy and review boundaries

- On-device or local extraction can reduce data movement, but callers remain responsible for how they store and transmit matter data.
- Generated documents require human review.
- Needle does not guarantee legal correctness, regulatory compliance, or suitability for a particular filing or contract.
