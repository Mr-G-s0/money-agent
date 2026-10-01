# Money Agent — Version 2

A safety-first autonomous AI business-agent prototype. It starts with a **simulated $100.00**,
performs bounded read-only web research, compares legitimate opportunities, selects a strategy,
creates a plan, cites its evidence, and proposes one next action. It never spends real money or
performs consequential external actions.

> This is experimental planning software, not a promise of profit or financial advice. Projections
> are hypotheses. Only completed, recorded simulated transactions affect realized profit.

## Version 2 run flow

```text
DISCOVER → RESEARCH → COMPARE → SELECT → PLAN → PROPOSE NEXT ACTION → SAVE STATE
```

1. Open or create the local SQLite database and load the simulated ledger and prior memory.
2. Reuse fresh research and refresh stale research automatically.
3. With `OPENAI_API_KEY`, run bounded discovery, demand, competitor, pricing, marketplace, and
   constraints research through the OpenAI Responses API's hosted `web_search` tool.
4. Persist attributable sources and a separate research-run usage/audit record.
5. Have the OpenAI Agents SDK compare opportunities and produce a typed decision citing stored
   numeric research IDs and listing assumptions separately.
6. Validate the next action against hard safety rules. A harmless local action may be recorded;
   everything financial or consequential becomes a pending approval request and is not executed.
7. Save the strategy, decision, action result, sources, and metrics for the next run.

Without a key, a clearly labeled deterministic offline planner runs and reuses saved research. It
does not pretend that an AI or web call happened.

## Architecture

```text
src/money_agent/
├── approvals.py   # approval records and cash snapshots
├── cli.py         # beginner-friendly command-line output
├── config.py      # environment configuration
├── ledger.py      # realized cash/profit accounting
├── models.py      # validated decision and action contracts
├── planner.py     # Agents SDK planner and explicit offline fallback
├── research.py    # read-only OpenAI web search, caching, attribution, and limits
├── safety.py      # prohibited activity and approval gate
├── service.py     # one discover/research/decide/save cycle
└── storage.py     # SQLite schema and persistent state
```

The planner and research-provider protocols separate reasoning and web access from orchestration.
Future capabilities can be added behind explicit adapters without rewriting memory, the ledger, or
the approval boundary.

## Installation

Python 3.11 or newer and an internet connection for the initial dependency download are required.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The project uses the official `openai-agents` Python package and OpenAI Responses API. The research
provider exposes only the hosted `web_search` tool—no browser, computer-use, shell, form,
messaging, payment, or write tool.

## API configuration

1. Copy the safe template: `cp .env.example .env` (Windows: `copy .env.example .env`).
2. Open `.env`, put your key after `OPENAI_API_KEY=`, and save it.
3. Never put a key in source code or commit `.env`; both `.env` and common credential files are
   ignored by Git.

An API key is required for **live Version 2 web research**, but not for an offline demonstration.
`MONEY_AGENT_MODEL` selects the model. Change the default if it is unavailable to your API project.
OpenAI calls may incur charges on your OpenAI account; those charges are not paid from or entered
into the simulated $100 business ledger.

## Run Version 2

```bash
money-agent
# equivalent after installation:
python -m money_agent
```

State is stored at `data/money_agent.db` by default and ignored by Git. Set
`MONEY_AGENT_DB=/some/path.db` to use another file. Back up that file to preserve progress.

## How web research works

The application selects its own bounded research tasks; the user does not supply queries. Each
hosted web-search request asks OpenAI to search broadly and follow relevant sources when useful,
prefer current/primary sources, and distinguish evidence from assumptions. Only results containing
attributable HTTP(S) source URLs are accepted. Empty or unattributed output becomes a recorded
research warning, not a fact.

Each `research` row stores:

- query, source URL, and source title;
- UTC retrieval time and relevant synthesized findings;
- related opportunity/research area;
- confidence and `verified`, `inferred`, or `uncertain` status; and
- a stable fingerprint for deduplication.

Source URL/title retrieval is directly observed. Finding text is a model synthesis, so Version 2
conservatively marks it `inferred` rather than treating a snippet or unsupported model statement as
verified fact. The decision must cite persisted record IDs and separate uncertainties. Unsupported
citation IDs are removed before persistence.

Fresh records satisfy the same research task without another call. After the staleness window, the
task is refreshed and an existing fingerprinted record is updated rather than duplicated. Provider
errors are contained and audited without deleting earlier research.

### Configurable research limits

```dotenv
MONEY_AGENT_RESEARCH_MAX_QUERIES=3
MONEY_AGENT_RESEARCH_MAX_SOURCES=12
MONEY_AGENT_RESEARCH_STALE_HOURS=168
MONEY_AGENT_MAX_TURNS=8
```

- `MAX_QUERIES` caps web-search requests per run.
- `MAX_SOURCES` caps sources supplied to decision-making and persisted per run.
- `STALE_HOURS` defaults to seven days before refresh.
- `MAX_TURNS` bounds the Agents SDK decision run.
- Set either numeric research limit to `0` to disable new research.

API-call count, cache hits, source count, errors, and run status are stored separately in
`research_runs`; they never affect business cash, expenses, revenue, or realized profit.

## Ledger rules

Money is stored as integer cents. The summary reports starting balance, current cash, realized
expenses/revenue/profit, and pending expenses. Projected revenue is rejected from the ledger and
belongs in research or memory. An expense larger than current cash is rejected, preventing debt.
Approval requests do not change cash. Every Version 2 transaction is simulated, and no command can
create a real transaction.

## Safety and approval boundaries

Hard checks reject gambling/betting, loans/debt/leverage, scams, fraud, misleading or impersonating
people, spam, review manipulation, illegal or platform-violating behavior, security bypass, and
unauthorized access. Enforcement does not rely only on a model prompt.

Approval requests persist and display `ACTION`, `COST`, `REASON`, `EXPECTED UPSIDE`, `RISKS`,
`CURRENT CASH`, and `CASH AFTER ACTION`. Spending, transactions, purchases, real-person messages,
public posts, paid accounts, agreements, important account changes, and other consequential actions
require approval. Even an approved record cannot execute an external action or charge the ledger.

Web access is read-only. The agent cannot submit forms, log in, buy anything, create accounts, send
messages/email, post content, alter external data, download or execute untrusted programs, bypass
restrictions, or use a general-purpose scraper. A useful future external action is proposed through
the approval boundary, not executed.

## Tests

```bash
pytest
ruff check .
mypy src/money_agent --ignore-missing-imports
pyright src/money_agent
```

External web/API calls are mocked in automated tests. Tests cover the complete Version 1 suite plus
research persistence, attribution, fresh-cache reuse, stale refresh, query/source limits, provider
failure, empty results, deduplication, and read-only tool exposure.

## Current capabilities

- Persistent strategies, decisions, experiments, memories, ledger, approvals, research, and
  research-run audits in SQLite.
- Live attributable read-only research with the hosted OpenAI `web_search` tool.
- Typed, research-aware decisions through the OpenAI Agents SDK.
- Source caching, staleness refresh, deduplication, failure handling, and configurable cost limits.
- Strict realized-vs-projected accounting, no-debt enforcement, and central approval safeguards.
- A transparent no-key offline mode.

## Current limitations

- No browser/computer control, code execution, general file/website creation, email, outreach,
  payments, form submission, authentication, public posting, or scheduler.
- No external executor exists, even after an approval record is marked approved.
- The offline planner is fixed logic and cannot create fresh web research.
- Findings are synthesized and conservatively marked inferred; claim-by-claim corroboration across
  independent primary sources is not implemented yet.
- The CLI performs one bounded cycle per invocation; it does not run unattended.
- Trusted result adapters for simulated realized revenue/expenses do not exist, so the CLI cannot
  fabricate revenue.

## Planned next steps (not implemented)

1. Add claim-level corroboration and source-quality scoring.
2. Add approval review with immutable audit events and expiration.
3. Add a capability registry and sandboxed local artifact tools.
4. Add experiment metrics and evidence-based strategy scoring.
5. Add a scheduler with run/time/token budgets and a reliable stop control.
6. Add specialized agents only after tracing and limits exist.
7. Add narrow external adapters one at a time, each default-denied and approval-gated.
