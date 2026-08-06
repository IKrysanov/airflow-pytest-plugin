# Report assistant

The AI chat inside the Pytest Reports dashboard: what it does, how to switch it on, what it
sends to a provider, and every setting it reads.

Part of [`airflow-pytest-plugin`](../../../README.md) — the plugin's own README covers the
viewer, archiving, coverage, alerts and everything else. This file is only the assistant.

## Contents

- [Getting it running](#getting-it-running)
- [What the model is given](#what-the-model-is-given)
- [Limits, cost and audit](#limits-cost-and-audit)
- [Database](#database)
- [Environment variables](#environment-variables)

## What it is

The **AI assistant** button opens a chat window over the current report selection and answers
questions about it. Selected rows become the scope; otherwise the current DAG/task/run filters
are. Every request repeats Airflow's DAG read checks on the server, so an answer can only ever
be built from reports the asking user may already open.

It also knows what this product is: a short, curated description of the operator, the plugin
and the dashboard travels with every question, so "what does `airflow-pytest-operator` do?"
gets an answer instead of "no data". Point `AIRFLOW_PYTEST_ASSISTANT_DOCS` at your manuals —
this README, the operator's, your own runbook — and it can answer the detailed questions too:
"what parameters does `PytestOperator` take?" needs the operator's own documentation, which
lives in another package and which nothing here could tell you truthfully. Only the sections
a question actually matches are sent, so a question about your runs carries none of it, and
the **Documentation** row in the byte breakdown shows exactly what each answer cost.

Ask it to write tests and it will: paste code or describe behaviour, say how many cases you
want, and it returns runnable pytest — presented as a starting point it has never run, never
as evidence about your suite. Those facts are written in the source and covered by a
test that checks everything they name still exists — the model is *given* them rather than
recalling them, and it is told to send you to the Help page and the README for anything they
do not cover. A question asked with no report in scope is answered too: on a fresh install,
that is exactly when someone asks what the thing does.

Answers stream token by token, **Send** becomes **Stop** while one is being written, and each
answer shows the exact bytes and provider tokens it cost. In local mode the panel reports what
the reducer is doing — model loading, chunks read, seconds left of the budget — instead of
leaving a spinner for up to two minutes. The **Context overview** button on
your own message opens the precise `REPORT EVIDENCE` block that was sent — after RBAC
filtering and secret redaction — so nothing about what left the server is implicit.

> The outbound context can contain run summaries, case IDs, outcomes, durations, failure
> tracebacks, saved triage verdicts and up to 2 KiB of captured stdout/stderr per failure.
> Known secrets and values from the server environment are redacted first, but redaction is a
> guard rail, not a proof. Enable the assistant only where sending failure output to your
> chosen provider is allowed.

## Getting it running

Install a provider **in the API-server image** — not the worker — and name it. Nothing else is
required; the button appears on the next page load:

```bash
pip install 'airflow-pytest-plugin[assistant-anthropic]'
export AIRFLOW_PYTEST_ASSISTANT_PROVIDER=anthropic     # anthropic | openai | gigachat | fake
export ANTHROPIC_API_KEY=sk-ant-...
```

The adapters use the vendor SDKs directly and follow their native environment conventions
(`ANTHROPIC_*`, `OPENAI_*`, `GIGACHAT_*`); `AIRFLOW_PYTEST_ASSISTANT_MODEL` overrides the model
for chat only.

**With no provider set there is no assistant at all** — no button, no dialog, no client code
in the page, and no `/api/assistant/*` routes (they are absent from the schema too, not merely
refusing). Nothing connects to the database for it either. Creating the tables is a separate
operator decision: `db upgrade` works with or without a provider, and the empty tables sit
there until something writes to them.

If a provider *is* set but cannot start — SDK missing, GGUF path wrong — the endpoints stay,
the window opens and says why, and the same line is logged once by the API server at startup.

In Docker Compose, put everything on the service that runs the API server:

```yaml
services:
  airflow-api-server:
    environment:
      AIRFLOW_PYTEST_ASSISTANT_PROVIDER: "anthropic"
      ANTHROPIC_API_KEY: "sk-ant-..."
      AIRFLOW_PYTEST_ASSISTANT_DAILY_TOKEN_QUOTA: "200000"
```

Optionally create the plugin's own tables once. That turns the daily token quota **and** the
request rate limit into real shared limits, and stores each user's chats server-side so they
survive a closed tab (see [Database](#database)):

```bash
python -m airflow_pytest_plugin.db upgrade    # like `airflow db migrate`, once per database
python -m airflow_pytest_plugin.db status
```

`upgrade` is designed to sit in a container start-up command and run on **every** start.
It is idempotent, it never drops or rewrites a row, and replicas starting at the same
instant do not break each other: each step tolerates having lost the race, and the version
is recorded only once the tables genuinely match it. Chats, quotas and rate windows survive
every rebuild — they live in the database, not the image.

**Re-run `upgrade` after every plugin update.** A release that adds a column has to alter the
table that already exists, and until you do the older table stays as it was — inserts then
fail where the failure is deliberately swallowed (chat history is a convenience, never an
outage), so chats simply stop being saved. `upgrade` runs the pending migrations, keeps
existing rows, and records the new version **only if the tables really match it**; `status`
and `doctor` say plainly when a database is a version behind rather than pretending it is
uninitialised.

If chats are not being saved, one command walks every precondition in order and stops at the
first one that fails — wrong URL, unreachable server, missing tables, retention switched off,
or a write that the database user is not allowed to make:

```bash
python -m airflow_pytest_plugin.db doctor
```

```console
1. Database URL      : postgresql://postgres/airflow
2. Reachable         : yes
3. Tables            : present at version 3 (this build expects 3)
4. Chat history      : on, kept for 30 day(s)
5. Write probe       : wrote and read back a message, then removed it
```

If all five pass and chats still do not appear, the acting user is the last thing to check:
open `/api/assistant/status` from the signed-in browser. `"history_server_side": true` means
that user's chats are being saved; `false` means the auth manager gives no unique account key
for them — or there is none at all — so their chat stays in the browser.

If you install the plugin from a container `command:`, that is also where the table creation
belongs — after the install, before Airflow starts. It is idempotent, so it can stay there:

```yaml
    depends_on:
      postgres:
        condition: service_healthy      # the database must accept connections first
    command: >
      bash -c "
        pip install -e /opt/airflow-lib/airflow_pytest_plugin[dev,assistant-anthropic] &&
        python -m airflow_pytest_plugin.db upgrade &&
        exec airflow standalone
      "
```

Skipping it breaks nothing: the quota falls back to a per-process counter and chats stay in the
browser. `GET /api/assistant/status` reports `"quota_shared"` so you can tell which you have.

## What the model is given

Two modes, chosen by whether a local GGUF reducer is configured.

| | **Direct** (default) | **Local full tree** |
|:--|:--|:--|
| Scope read | newest 100 run summaries, then failure detail while the budget lasts | every report and every case in scope |
| Evidence sent | compact JSON Lines, one strict 48 KiB budget for the whole request | facts merged by an in-process GGUF, then sent |
| Costs | one provider call | one provider call **plus** API-server RAM, CPU and latency |
| Fidelity | exact, by construction | lossy — the reducer paraphrases |

The 48 KiB is a budget for the *whole request*, not per report. Records are appended whole and
collection stops when the next one will not fit; the answer is then marked context-limited
rather than the request failing. Chat history is capped separately (12 messages, 16 KiB) and
does not consume that budget. To reach older runs, narrow the filter or select rows explicitly.

Each question makes exactly one final provider call. Local map/reduce passes are in-process and
are not network requests.

<details id="optional-local-context-model">
<summary><strong>Optional local context model</strong> — full tree, at a real cost</summary>

```bash
# The SAME environment as the Airflow API server. The extra installs llama-cpp-python,
# not a model: download one GGUF file yourself.
pip install 'airflow-pytest-plugin[assistant-anthropic,assistant-local]'
curl -fL 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf?download=true' \
  -o /models/qwen2.5-1.5b-instruct-q4_k_m.gguf
export AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL=/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

The variable is a **path to the `.gguf` file** — not a URL, not a directory. Mount it read-only
in the API-server container and restart every API-server process. The model is loaded lazily
per process, so four workers mean four copies in memory.

**Measure your model before trusting this mode.** `scripts/grade_reducer.py` runs a fixed
corpus through the real pipeline and counts how many required facts (node ids, counts, error
strings) survived. Direct mode scores 100% by construction, so anything below ~80% is strictly
worse than not using one. Measured on an Apple M-series laptop:

| Model (Q4_K_M) | Size | RSS after load | Facts kept | Per chunk p50 |
|:--|--:|--:|--:|--:|
| Qwen2.5-0.5B | 469 MB | ~870 MiB | 24% | 0.8 s |
| **Qwen2.5-1.5B** | 1.0 GB | ~2.4 GiB | **76%** | 2.6 s |
| Qwen2.5-3B | 2.0 GB | ~4.5 GiB | 59% | 4.4 s |

Three things follow. Resident memory is roughly **2–2.4× the file size** per process. Bigger is
not better — 3B paraphrases more confidently and loses more identifiers. And even the best of
them drops about a quarter of the facts, so **direct mode remains the better default** unless
you have graded your own model on your own trees.

One pass runs per chunk (~350 chunks for 1,000 runs × 20 cases), a synchronous llama.cpp call
cannot be interrupted, and the request holds the process's only assistant slot. So the map
phase is bounded by `..._LOCAL_BUDGET_SECONDS` (120 s ≈ 30–60 runs); past it the remaining
chunks are skipped and the answer is marked context-limited. `[R1]` labels are restored
deterministically when the model drops them, and a reduction that returns mostly empty,
citation-free output is reported as context-limited rather than dressed up as grounded.

</details>

## What it can be asked

Beyond questions about your runs, it carries instructions for particular kinds of request.
Each arrives only when the question is about that subject, so an ordinary question pays for
none of them:

Type **`/`** in the question box and the commands appear; pick one and the skill is chosen
outright rather than guessed from your wording. Arrow keys move, Enter or Tab accepts,
Escape closes. The command is stripped before the question reaches the model — it tells the
server which rules to send, it is not part of what you asked.

| Command | Ask it to… | It will… |
|:--|:--|:--|
| `/bug` | **draft a bug report** — "оформи багрепорт по этому падению", "write this up as an issue" | produce summary, where, when, test, what happened, how to reproduce, and an explicit list of what the evidence does *not* establish — without inventing a cause, severity or owner |
| `/flaky` | **judge a flaky test** — "should I quarantine this?", "стоит ли скипнуть?" | separate a test that alternates from one that broke and stayed broken, show the pass/fail split, and weigh `@pytest.mark.flaky`, `skip` and this dashboard's quarantine — saying what each one hides |
| `/priority` | **prioritise** — "что чинить в первую очередь?" | rank by runs blocked, determinism, shared failure signature and duration cost, stating the rule it ranked by, and that this orders symptoms rather than causes |
| `/compare` | **compare runs** — "what changed since yesterday?" | list outcome changes, tests present on one side only, totals and durations — and refuse to narrate a cause the evidence does not contain |
| `/test` | **write tests** — "напиши три теста на эту функцию" | return runnable pytest, exactly as many cases as asked, presented as a starting point it has never run |
| `/docs` | **answer from the manuals** — "как запустить первый тест?" | quote the documentation you mounted (`AIRFLOW_PYTEST_ASSISTANT_DOCS`) and name the heading it came from. Without the command a vague question has to clear a relevance bar to pull any documentation at all, because most questions are about runs; the command says plainly that this one is not. If you mounted nothing, it promises nothing — the rules for quoting a manual are never sent when there is no manual |

The instructions live in [`prompts/`](prompts) as one Markdown file per subject, next to the
code. Reading them is the fastest way to know exactly what your assistant is told; changing
one is editing a file.

Two of these — `/test` and `/docs` — are not questions about your runs, so on an empty
dashboard they are answered instead of being met with "no report matched, widen your
filters". The rest still say so, because for them it is the answer.

## Limits, cost and audit

Each principal gets a request rate limit (60/hour by default — far beyond human use, enough to
stop a runaway script) and an optional daily token budget, off until you set one. A refused
request answers `429` with `Retry-After` before reaching any model, so it costs nothing. When a
provider returns no usage data the budget is charged an estimate rather than zero, so a gateway
that strips `usage` cannot silently switch the cap off.

**Both limits are only real limits once the tables exist.** Counted in memory they are per
worker, so four workers mean four times the allowance. With the tables, four workers share one.
`GET /api/assistant/status` reports `quota_shared` and `rate_shared` so you can see which you
have. Each worker still keeps its own sliding window in front of the shared counter, so a
runaway loop is stopped without a database round trip per attempt; the shared counter is a
fixed window, which can allow a burst across a window boundary. For a hard multi-tenant
guarantee, add a limiter at your ingress as well.

Every request writes one JSON record to the `airflow_pytest_plugin.assistant.audit` logger, so
you can reconstruct who sent report data to which provider:

```json
{"event":"assistant.query","principal":"alice","outcome":"answered","mode":"direct",
 "provider":"anthropic","model":"claude-sonnet-5","dags":["etl_daily","ml_train"],
 "reports_considered":30,"input_tokens":8240,"output_tokens":312,"total_tokens":8552,
 "latency_ms":4120,"context_limited":false,"question_chars":42,
 "question_sha256":"3f2a1c9d8b7e6f50","scope":"all readable reports","streamed":true}
```

It carries **no report content and no question text** — the digest lets you correlate the same
question across records without storing it. Outcomes include `forbidden` and `rate_limited`, so
refused attempts are recorded too. Set `..._AUDIT_LOG=0` to silence it.

`POST /api/assistant/health` proves the configured models actually answer, using one fixed
16-token probe with no report data. It is **off by default** (`..._HEALTHCHECK=1`) because the
probe is a real billable call; the result is cached for 60 s and takes the same model slot as a
question, so polling it cannot multiply cost.

## Database

The plugin's tables are always prefixed `pytest_assistant_` and live in their own SQLAlchemy
metadata — `airflow db` commands and autogenerate never see them. Creation is an explicit
operator step because Airflow has no migration hook for plugins.

| Setting | Default | Purpose |
|:--|:--|:--|
| *(nothing set)* | Airflow's metadata DB | tables go beside Airflow's own, on the connection Airflow already manages. Read through Airflow's config, so `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` and its `_CMD`/`_SECRET` forms all work |
| `AIRFLOW_PYTEST_ASSISTANT_DB_CONN_ID` | — | name of an **Airflow connection** to use instead; credentials stay in your secrets backend |
| `AIRFLOW_PYTEST_ASSISTANT_DB_URL` | — | a literal SQLAlchemy URL — any host, port or server, including a database entirely separate from Airflow's |

**Passing credentials**, in order of preference: leave both unset and reuse Airflow's
connection (no second credential to leak or rotate); or name an Airflow connection, so only the
*name* is in the environment:

```bash
airflow connections add pytest_assistant_db \
  --conn-uri 'postgresql://apx:PASSWORD@db.internal:5432/pytest_assistant'
export AIRFLOW_PYTEST_ASSISTANT_DB_CONN_ID=pytest_assistant_db
```

Only if neither fits, set `..._DB_URL` from a Kubernetes/Docker secret rather than a plain
`env:` line. A connection id that cannot be resolved is reported as an error — the plugin will
never quietly fall back to Airflow's database and write your data somewhere you did not ask.

`status` separates the states that need different fixes, and never prints credentials — not in
the CLI, not in logs, not in connection errors:

```console
$ python -m airflow_pytest_plugin.db status
Database postgresql://postgres/airflow is reachable but not initialised.
Run: python -m airflow_pytest_plugin.db upgrade
```
```console
Database postgresql://postgres/airflow could not be reached:
  OperationalError: could not translate host name "postgres" to address
```
```console
Database postgresql://postgres/airflow could not be reached:
  ModuleNotFoundError: No module named 'psycopg2'      # driver missing in this image
```
```console
No database is configured.                             # nothing to connect to at all
```

If the database becomes unreachable later the assistant keeps answering and logs one warning:
an unreachable metadata database means Airflow itself is in trouble, and refusing every
question would only add noise to that incident. A store whose statements actually fail then
reports itself unavailable for 30 seconds before trying again — so `GET /api/assistant/status`
turns `history_server_side` off, the chat list disappears rather than sitting permanently
empty, and the feature comes back on its own once the database does. No restart needed.

### Server-side chats

Once the tables exist, each completed exchange is stored for the asking user, so a chat
survives a closed tab and follows them to another browser. Only the **question and answer** are
kept, with `[R1]` evidence links and token usage; the `REPORT EVIDENCE` block is never written,
so tracebacks stay in the report archive they came from.

A **Chats** button then appears in the panel header: it lists that user's saved chats newest
first, titled by their opening question, and switching loads that transcript. **New chat** sits
in that window's header beside its close button and starts a fresh chat without deleting
anything. Deleting a chat asks first, and so does **Clear chat** — it removes the saved copy as
well as the one on screen, so it is never a single click. A refresh returns to whichever chat
the tab was reading. Without the tables the button stays hidden and the panel behaves exactly
as before — one transcript, kept in the tab.

Ownership is enforced in the query, not in the UI: every read, write and delete is filtered by
the acting principal. That principal is taken only from a unique account key (username, user
id) — never from a display name, which two colleagues can share. A user the auth manager does
not let us identify that way gets **no** server-side history, since a shared bucket would be a
cross-account leak; the same applies to a viewer running with no auth manager at all, where
every visitor would otherwise be one principal.

Two more rules follow from the same principle. The stored question is the **redacted** one the
model saw, so a value scrubbed on its way to a provider does not survive in the metadata
database instead. And the `[R1]` links in a restored answer are re-checked against your DAG
read permissions when the transcript is served: an answer written while you had access does
not keep naming a DAG after that access is withdrawn.

Chats expire after `HISTORY_DAYS` (dropped opportunistically, at most hourly per process).
**Clear chat** deletes the user's stored transcript as well as the local one, so nobody needs
an administrator to erase their own history.

```bash
python -m airflow_pytest_plugin.db purge                 # honours HISTORY_DAYS
python -m airflow_pytest_plugin.db purge --history-days 7
```

## Environment variables

Set these on the **API-server** container and restart it; they are resolved once at start-up.
A value above the documented maximum is clamped to it; one below the minimum, or one that is
not a number at all, falls back to the default. (The asymmetry matters for
`DAILY_TOKEN_QUOTA`, whose default is *unlimited*: falling back there would turn a too-large
cap into no cap.) Byte limits are binary
(`1 KiB = 1024 bytes`), so the defaults mean exactly 49,152 bytes of evidence, 3,072 per
traceback and 2,048 of captured output. The question/history envelope and the 100-ID selection
cap are fixed abuse-safety contracts, not tuning knobs.

| Environment variable | Default | Purpose |
|:--|:--|:--|
| `AIRFLOW_PYTEST_ASSISTANT_PROVIDER` | — | enables chat: `anthropic`, `openai`, `gigachat`, or `fake` |
| `AIRFLOW_PYTEST_ASSISTANT_MODEL` | provider default | final-answer model; overrides the provider-native model variable |
| `AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MODEL` | — | path to the local GGUF reducer; unset = direct bounded context |
| `AIRFLOW_PYTEST_ASSISTANT_CONTEXT_BYTES` | `49152` | total report-evidence budget per request (4 KiB–256 KiB) |
| `AIRFLOW_PYTEST_ASSISTANT_DIRECT_MAX_SUMMARIES` | `100` | newest summaries in direct mode (1–1000); no limit in local full-tree mode |
| `AIRFLOW_PYTEST_ASSISTANT_TRACEBACK_BYTES` | `3072` | traceback bytes kept per failed or errored test (0–65536) |
| `AIRFLOW_PYTEST_ASSISTANT_CAPTURE_BYTES` | `2048` | captured output bytes kept per failed or errored test (`0` disables) |
| `AIRFLOW_PYTEST_ASSISTANT_CONTEXT_N_CTX` | `16384` | local model context window; must fit prompts, question, output and a 4 KiB chunk |
| `AIRFLOW_PYTEST_ASSISTANT_CONTEXT_MAX_TOKENS` | `1024` | most tokens produced by the local reducer |
| `AIRFLOW_PYTEST_ASSISTANT_LOCAL_BUDGET_SECONDS` | `120` | wall clock one request may spend reducing locally (5–3600) |
| `AIRFLOW_PYTEST_ASSISTANT_MAX_OUTPUT_TOKENS` | `3072` | most tokens requested for the final answer (128–8192) |
| `AIRFLOW_PYTEST_ASSISTANT_TIMEOUT` | `45` | provider timeout in seconds |
| `AIRFLOW_PYTEST_ASSISTANT_MAX_CONCURRENT` | `4`, or `1` with a local model | simultaneous assistant calls in one API-server process (1–8). The local GGUF serialises on its own lock and each copy costs gigabytes, so that path gets one slot; direct mode costs ~0.15 MiB per extra request, and one slot there made the second person to ask wait |
| `AIRFLOW_PYTEST_ASSISTANT_HEALTHCHECK` | — | `1` enables `POST /api/assistant/health`; off because the probe is billable |
| `AIRFLOW_PYTEST_ASSISTANT_AUDIT_LOG` | on | one JSON audit record per request; `0` silences it |
| `AIRFLOW_PYTEST_ASSISTANT_RATE_LIMIT` | `60` | questions one principal may ask per window; `0` disables |
| `AIRFLOW_PYTEST_ASSISTANT_RATE_WINDOW` | `3600` | sliding window in seconds (1–86400) |
| `AIRFLOW_PYTEST_ASSISTANT_DAILY_TOKEN_QUOTA` | `0` | provider tokens one principal may spend per UTC day; `0` = unlimited |
| `AIRFLOW_PYTEST_ASSISTANT_DB_CONN_ID` | — | Airflow connection naming the database for the plugin's tables |
| `AIRFLOW_PYTEST_ASSISTANT_DB_URL` | Airflow's metadata DB | literal SQLAlchemy URL; wins over the connection id |
| `AIRFLOW_PYTEST_ASSISTANT_HISTORY_DAYS` | `30` | how long a stored chat is kept; `0` stores nothing server-side |
| `AIRFLOW_PYTEST_ASSISTANT_DOCS` | — | Markdown files or directories the assistant may quote when asked about the product; separate several with `,`, `:` or `;` |
| `AIRFLOW_PYTEST_ASSISTANT_DOCS_BYTES` | `4096` | how much of that documentation one question may carry (0–32768; `0` disables) |
