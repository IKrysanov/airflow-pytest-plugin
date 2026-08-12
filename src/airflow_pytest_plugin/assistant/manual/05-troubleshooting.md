# Troubleshooting

## The dashboard page is empty

No archived run matches your access and your filters yet. Clear the filters, run the
`PytestOperator` task, then use Refresh. If colleagues can see runs and you cannot, you are
missing Airflow read permission on that DAG -- the plugin re-checks it on every request and
has no permission model of its own.

If nothing appears for anyone, the two sides are usually pointed at different directories:
the worker archived to its own local path and the API server is reading another. The report
root must be the same shared volume for both.

## Runs archive but the assistant is not there

The assistant appears only when a provider is named. With
`AIRFLOW_PYTEST_ASSISTANT_PROVIDER` unset there is no button, no dialog and no
`/api/assistant/*` routes at all -- a deployment that did not ask for the feature does not
get a broken one. Set the variable in the **API server** image, not the worker.

If the provider is set but its SDK is missing, the panel opens and says so, and the API
server logs the same line once at start-up.

## Chats are not being saved

Server-side chat needs the plugin's own tables. One command walks every precondition in
order and stops at the first that fails:

```bash
python -m airflow_pytest_plugin.db doctor
```

It checks the database URL, whether the server answers, whether the tables exist at the
version this build expects, whether history retention is switched on, whether the database
user may actually write, and what encryption is doing. If those pass and chats still do not
appear, open `/api/assistant/status` from the signed-in browser: `"history_server_side": true` means
that user's chats are being stored, `false` means their auth manager exposes no unique
account key, so their chat stays in the browser tab instead.

## A message reads "unreadable: encrypted with a Fernet key this server does not have"

Your chat is encrypted in the database with Airflow's Fernet key, and that message was written
with a key this server no longer has. The text itself is intact in the database -- listing
the old key again in `AIRFLOW__CORE__FERNET_KEY` (comma-separated, newest leading) brings it
straight back, and nothing was overwritten.

This is what a key rotation that skipped the plugin looks like. `airflow rotate-fernet-key`
re-encrypts Airflow's own connections and variables and knows nothing about this table, so
the chat has to be moved across separately, while both keys are still listed:

```bash
python -m airflow_pytest_plugin.db rotate-key
```

Restart every API server on the new key before running it: a server still using the old key
keeps writing rows the pass has already walked past, and those are the ones that go missing
when the old key is finally removed.

## After upgrading the plugin

Run `python -m airflow_pytest_plugin.db upgrade` again. A release that adds a column has to
alter the table that already exists; until it does, inserts fail where the failure is
deliberately swallowed, and chats simply stop being saved. The command is idempotent, keeps
existing rows, and can sit in a container start-up command.

## A test run is too large to open

A report above `AIRFLOW_PYTEST_MAX_REPORT_MIB` (64 MiB by default) still lists with its real
numbers, but opening it says so rather than loading it. Raise the limit if a suite really
archives more, or set it to `0` to remove the limit.
