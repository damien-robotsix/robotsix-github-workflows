# Workflow Authoring Guide

This guide consolidates the conventions for authoring new **reusable**
(`workflow_call`) workflows in this repository. It is the single source of
truth for workflow authors; `AGENT.md` holds the terse rule list, and
`CONTRIBUTING.md` covers the test/lint tooling this guide cross-references.

Citations below point at live workflows — read the cited step for a working
example, and copy its shape rather than inventing a new one.

## 1. Workflow structure

Scaffold every new reusable workflow as a `workflow_call` target:

```yaml
name: <human-readable name>
on:
  workflow_call:
    inputs:
      # ... see §2
    secrets:
      # ... declare every secret the workflow consumes
jobs:
  <job>:
    # Prefer job-level `if:` guards over a workflow-level condition so the
    # GitHub UI shows a clean per-job "skipped" status (AGENT.md Rule 4).
    if: ${{ inputs.<guard> }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<40-char-sha>  # vX.Y.Z
        with:
          persist-credentials: false         # AGENT.md Rule 3
```

Key structural rules:

- **Pin every `uses:` to a 40-char commit SHA** with a trailing `# vX.Y.Z`
  comment (AGENT.md Rule 1). Resolve the SHA with
  `git ls-remote <url> "refs/tags/<tag>^{}" "refs/tags/<tag>"` — never a
  floating tag like `@v4` or `@main`.
- **`persist-credentials: false` on every `actions/checkout`** (AGENT.md
  Rule 3).
- **Job-level `if:` guards** for conditional jobs (AGENT.md Rule 4).
- **No inline Python heredocs.** Reusable-workflow Python lives in
  `scripts/<name>.py` as an importable module invoked via
  `python3 scripts/<name>.py`, so tests exercise the live logic
  (AGENT.md Rule 6).

## 2. Input design patterns

Design `workflow_call` inputs explicitly:

- **`required: true`** for inputs with no sensible default; **`required:
  false` with a `default:`** otherwise.
- **`type:`** — always set it (`string`, `boolean`, or `number`).
- **`description:`** — every input gets one (see §9); it is the only
  documentation a caller sees.
- **Defaults must be static literals** — never `${{ }}` expressions
  (AGENT.md Rule 5). GitHub rejects dynamic `default:` values with an
  "Invalid workflow file" error that fails every caller run. For a dynamic
  fallback, declare `default: ""` and compute it inside a step:

  ```yaml
  ${{ inputs.image != '' && inputs.image || format('ghcr.io/{0}', github.repository) }}
  ```

See `.github/actions/python-setup/action.yml` for a compact example of
required vs. optional inputs with descriptions and a static default
(`install-extras` defaults to `"tracing"`).

## 3. Input validation patterns

Validate inputs in an early step and fail fast with an annotation.

**Range check** — reject out-of-bounds numeric inputs
(`python-ci.yml`, step *"Enforce coverage floor (hard minimum 80)"*,
lines ~125–139):

```yaml
- name: Enforce coverage floor (hard minimum 80)
  env:
    COVERAGE_THRESHOLD: ${{ inputs.coverage-threshold }}
  run: |
    if [ "${COVERAGE_THRESHOLD}" -lt 80 ]; then
      echo "::error::coverage-threshold=${COVERAGE_THRESHOLD} is below the fleet-wide hard minimum of 80. Either omit the input (default: 80) or set a value ≥ 80."
      exit 1
    fi
```

**Enum check** — validate a closed set of allowed values with a `case`
statement whose `*)` arm exits non-zero
(`bump.yml`, step *"Set bump-mode parameters"*, lines ~117–139):

```yaml
- name: Set bump-mode parameters
  env:
    BUMP_MODE: ${{ inputs.bump-mode }}
  run: |
    case "$BUMP_MODE" in
      deps) ... ;;
      pins) ... ;;
      *)
        echo "ERROR: unknown bump-mode: $BUMP_MODE" >&2
        exit 1
        ;;
    esac
```

**String emptiness check** — guard required-but-empty strings before use:

```yaml
run: |
  if [ -z "${MY_INPUT}" ]; then
    echo "::error::my-input must not be empty"
    exit 1
  fi
```

In every case the input is read from an `env:` map, never interpolated
directly into the shell (see §5).

## 4. Error handling and reporting

Use GitHub's workflow commands to surface problems where maintainers see
them:

- **`::error::<message>`** for a fatal validation failure; follow it with
  `exit 1` so the step fails. `baseline-check.yml` uses this pattern
  throughout, e.g.:

  ```bash
  echo "::error::AGENT.md is missing from repo root — create one following https://github.com/damien-robotsix/robotsix-standards"
  echo "::error::README.md does not reference damien-robotsix/robotsix-standards"
  ```

- **`::warning::<message>`** for a non-fatal issue the caller should notice
  but that should not fail the run.

- **`$GITHUB_STEP_SUMMARY`** for human-readable result reporting rendered on
  the run summary page. `mutation-test.yml` (step *"Write mutation score to
  step summary"*, line ~73) appends a Markdown heading:

  ```bash
  echo "### Mutation score: ${SCORE}%" >> "$GITHUB_STEP_SUMMARY"
  ```

Rule of thumb: `::error::` + `exit 1` for anything that invalidates the
run; `::warning::` for advisory signals; `$GITHUB_STEP_SUMMARY` for results
a human reads after a successful (or informational) run.

## 5. Template-injection prevention

**Never interpolate `${{ }}` expressions directly inside a `run:` block**
(AGENT.md Rule 2). Direct interpolation is a template-injection vector
flagged by `zizmor`. Always route the expression through the step's `env:`
map, which escapes the value before it reaches the shell:

```yaml
# WRONG — injection vector
- run: echo "coverage ${{ inputs.coverage-threshold }}"

# RIGHT — value escaped via env:
- env:
    COVERAGE_THRESHOLD: ${{ inputs.coverage-threshold }}
  run: echo "coverage ${COVERAGE_THRESHOLD}"
```

Every validation example in §3 follows this pattern.

## 6. Testing requirements

See `CONTRIBUTING.md` for the full tooling reference. In summary:

- **Python helpers** (`scripts/*.py`) are tested by importable pytest suites
  under `tests/test-*.py`. Run the suite with bare `pytest` or
  `pytest tests/` — `pyproject.toml` auto-discovers `tests/test-*.py`
  (see `CONTRIBUTING.md` → *Running tests* / *Adding a new test*).
- **Shell logic** that is non-trivial belongs in a `scripts/*.py` module
  (AGENT.md Rule 6) so it is unit-testable, rather than embedded inline.
- Because workflows invoke `python3 scripts/<name>.py` and tests import the
  same module, test coverage always exercises the live logic and the
  workflow cannot drift from it.

## 7. Pre-commit checklist

Before opening a PR, confirm the AGENT.md rules and run the linters:

- [ ] **Rule 1** — every `uses:` is a 40-char SHA with a `# vX.Y.Z` comment.
- [ ] **Rule 2** — no `${{ }}` inside any `run:` block; inputs flow through `env:`.
- [ ] **Rule 3** — `persist-credentials: false` on every `actions/checkout`.
- [ ] **Rule 4** — `workflow_call` jobs use job-level `if:` guards.
- [ ] **Rule 5** — `workflow_call` input `default:` values are static literals.
- [ ] **Rule 6** — no inline `python3 << 'PYEOF'` heredocs; Python lives in `scripts/*.py`.
- [ ] **Rule 7** — composite actions live at `.github/actions/<name>/action.yml`.
- [ ] `make lint` passes (see `CONTRIBUTING.md` → *Linting* / *Workflow validation*).
- [ ] `pytest` passes for any changed `scripts/*.py`.
- [ ] The commit subject / PR title uses a Conventional Commits type
      (`feat:`/`fix:`/`chore:`/`docs:`/`refactor:`/`test:`/`ci:`).

## 8. Composite action patterns

Extract duplicated workflow logic into a composite action when two or more
workflows (or jobs) share the same step sequence (AGENT.md Rule 7). Existing
examples: `.github/actions/python-setup` (shared checkout + Python + uv +
dev-deps install) and `.github/actions/trivy-sarif` (Trivy scan + SARIF
upload).

Conventions:

- A single `action.yml` at the root of a **snake_case** directory:
  `.github/actions/<name>/action.yml`.
- `runs.using: composite` with a `steps:` array; each run step declares
  `shell: bash`.
- Inputs carry `description`, `required`, and (where optional) a static
  `default`; reference them via `${{ inputs.* }}`.
- Rule 1 applies — pin every nested `uses:` to a 40-char SHA.
- Rule 3 applies — any `actions/checkout` sets `persist-credentials: false`.

```yaml
# .github/actions/<name>/action.yml
name: <name>
description: <what it does>
inputs:
  <input>:
    description: <...>
    required: false
    default: "<static literal>"
runs:
  using: composite
  steps:
    - uses: actions/checkout@<40-char-sha>  # vX.Y.Z
      with:
        persist-credentials: false
    - name: <step>
      shell: bash
      env:
        MY_INPUT: ${{ inputs.<input> }}
      run: |
        ...
```

## 9. Documentation requirements

Input `description:` fields are not optional metadata — they are the public
contract surfaced in `docs/workflow-reference.md`. Write each description so
it stands alone:

- State **what** the input controls and its **unit or accepted values**.
- Note the **default** behaviour when the input is omitted.
- Keep it to a single sentence where possible; callers read these in a table.

When you add, rename, or remove a workflow or its inputs, update
`docs/workflow-reference.md` so the consolidated reference stays accurate.
