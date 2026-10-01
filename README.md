# Money Agent — Version 3

A safety-first autonomous business-agent prototype. It starts with a **simulated $100.00**, performs bounded read-only research, compares legitimate opportunities, and now creates and evaluates useful assets in a private local sandbox. It cannot spend real money or perform consequential external actions.

> Experimental planning and prototyping software—not financial advice or a promise of profit. Projections are hypotheses; only completed simulated ledger entries count as realized results.

## Version 3 workflow

```text
DISCOVER → RESEARCH → COMPARE → SELECT → PLAN → CREATE → EVALUATE
         → PROPOSE NEXT ACTION → SAVE STATE
```

One invocation loads the ledger and memory, optionally reuses or refreshes attributable research, selects an opportunity, creates or improves an appropriate local asset, evaluates locally verifiable properties, routes the proposed next action through the existing approval boundary, and persists everything. With no API key, the transparent deterministic planner selects a digital-template opportunity and produces a meaningful Markdown product prototype rather than pretending that web or AI calls occurred.

## Architecture

```text
src/money_agent/
├── approvals.py   # approval records and cash snapshots
├── creation.py    # asset selection, creation, reuse, and evaluation
├── workspace.py   # capability-based file sandbox, limits, artifact memory, safe checks
├── research.py    # bounded read-only web research, caching, attribution
├── planner.py     # Agents SDK planner and explicit offline fallback
├── service.py     # discover-to-create orchestration
├── storage.py     # SQLite state, evidence, and artifact schema
├── ledger.py      # simulated realized accounting and no-debt rule
└── safety.py      # prohibited activity and external-action approval gate
```

The `Workspace` API exposes explicit text, Markdown/HTML/CSS/JavaScript/Python, JSON, and CSV file operations—not a shell. `AssetCreator` chooses a deliverable from the selected strategy and calls that narrow API. The included default creator builds or improves a ready-to-use Markdown digital-product draft; the APIs also support landing pages, sales-copy drafts, service workflows, pricing documents, research summaries, and software prototype source files.

## Workspace sandbox

The default root is `workspace/` and is ignored by Git. Every requested path is resolved beneath that root. Unix, Windows, UNC, home-relative, URL-encoded, noncanonical Unicode, mixed-separator, overlong, and over-deep paths are rejected, as are `..` traversal, symlink escapes, and sensitive names such as `.env`, `.ssh`, credentials, private keys, browser profiles/cookies, and PEM files. Reads and writes use no-follow directory descriptors so each parent is revalidated at the filesystem operation, narrowing symlink-replacement races. Existing files require an explicit overwrite flag.

The boundary is capability-based: agent code receives a `Workspace`, never general filesystem or arbitrary-command tools. Files elsewhere—including operating-system paths and unrelated user files—are unavailable through the creation interface.

## Safe code execution

There is **no unrestricted shell executor**. Two explicit Python operations exist:

1. `python_compile` parses and compiles a workspace `.py` file without running it.
2. `restricted_python` first applies an AST allowlist, rejecting imports, attributes, definitions, dunder access, arbitrary calls, file access, comprehensions, exponentiation, oversized syntax/literals/ranges, and unbounded `while`; it then runs isolated (`-I -S`), in the workspace, with a minimal environment and a two-second timeout. POSIX child limits cap CPU, address space, file output, and open descriptors; captured output is bounded.

Only a small set of pure built-ins is allowed. Package installation, downloads, administrator/system commands, credential access, network tools, persistence, deployment, destructive commands, and execution of downloaded/untrusted files are not capabilities. This runner is intended only for tiny generated calculations/tests, not third-party applications.

## Artifact memory and evaluation

SQLite records each artifact's ID, workspace-relative path, type, purpose, selected opportunity, creation and modification timestamps, status, evaluation notes, and related research IDs. A unique file path and opportunity lookup let later runs improve the existing asset instead of starting again.

After creation the agent reads the result back, checks existence/UTF-8 content, required sections, and basic completeness, then records limitations. Python files can additionally receive syntax or restricted execution checks. “Verified” means only that stated local checks passed; it does not mean demand, revenue, usefulness, security, or production readiness was proven.

## Configurable limits

```dotenv
MONEY_AGENT_WORKSPACE=workspace
MONEY_AGENT_WORKSPACE_MAX_FILES=100
MONEY_AGENT_WORKSPACE_MAX_BYTES=1000000
MONEY_AGENT_CREATION_MAX_FILES=6
MONEY_AGENT_EXECUTION_MAX_ATTEMPTS=3
MONEY_AGENT_WORKSPACE_MAX_OPERATIONS=30
MONEY_AGENT_RESEARCH_MAX_QUERIES=3
MONEY_AGENT_RESEARCH_MAX_SOURCES=12
MONEY_AGENT_RESEARCH_STALE_HOURS=168
MONEY_AGENT_MAX_TURNS=8
```

Limits bound total files, total bytes, new files per run, code attempts, web queries, persisted sources, evidence staleness, and model turns. Attempts beyond a limit fail closed. A run performs one bounded create/evaluate cycle, preventing recursive creation and uncontrolled API use.

## Safety and approvals

Version 1 and 2 guarantees remain: integer-cent simulated accounting, no debt, no projected revenue in the ledger, prohibited-activity checks, read-only evidence gathering, source attribution, and persistence. Local zero-cost creation needs no approval. Spending, purchases, transactions, contacting people, email/messaging, posts/publication, agreements, account changes, authentication, form submission, deployment, and every other consequential external action require a persisted approval request **and are still never executed**, even if approved. There is no external executor.

Creating `landing_page.html` or email copy locally is allowed. Publishing the page or sending the email is proposed only. The product cannot control a browser/computer, create accounts, make payments, purchase, deploy, scrape generally, scan networks, or transact financially.

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
money-agent
```

State defaults to `data/money_agent.db`. Copy `.env.example` to `.env` to configure an API key for optional OpenAI planning/read-only hosted web research. API charges are external operational costs and are never represented as spending from the simulated ledger.

### Complete offline example

1. Load the persisted simulated balance: `$100.00`.
2. Compare three offline opportunities and select **Niche digital template pack**.
3. Create `workspace/projects/niche-digital-template-pack/product.md` with a customer job, usable workflow, fillable template, validation checklist, and evidence IDs.
4. Read it back and verify required sections and content length.
5. Save/update its artifact row and an evaluation-memory record.
6. Record no ledger transaction and perform no publication, outreach, payment, or other external action.
7. On the next run, overwrite that same tracked artifact as an improvement revision rather than duplicating it.

## Testing

```bash
pytest
ruff check .
mypy src/money_agent --ignore-missing-imports
pyright src/money_agent
python -m compileall -q src tests
```

Tests cover the Version 1 ledger/approval safety rules; Version 2 research attribution, caching, staleness, limits, and read-only tool exposure; and Version 3 traversal/symlink restrictions, sensitive-file denial, creation/modification, structured files, artifact persistence/reuse, size/file limits, restricted execution, and a complete offline no-external-action smoke run.

The hardened no-follow file operations and restricted executor currently require a POSIX platform. They are tested on Linux; the program fails closed rather than offering a weaker Windows executor.

## Current limitations

- The creator uses coarse strategy keywords to choose digital-product, service, content, or software/landing-page assets; it does not yet derive bespoke schemas or full applications for every niche.
- Local checks do not prove market demand, accessibility, browser compatibility, production security, profitability, or fitness for a customer.
- Restricted Python intentionally cannot import libraries or exercise full applications. There is no JavaScript runtime or package manager.
- The AST policy plus process limits are defense in depth, not an operating-system container. An attacker who already has independent host filesystem/process access is outside the planner threat model and could race or tamper with the process; use an OS container or VM for hostile human-supplied code.
- Online research findings remain model syntheses marked inferred; claim-level independent corroboration is not yet implemented.
- The CLI runs one bounded cycle per invocation and has no scheduler.
- No external action or real-world revenue/expense adapter exists.
