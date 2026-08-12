SKILL: drafting a bug report
Asked to write up a failure as an issue, produce something a maintainer can act on without
opening the dashboard. Use these headings, in the user's language, and leave out any you
genuinely cannot fill from the evidence:
- **Summary** -- one sentence naming the behaviour, not the stack frame.
- **Where** -- DAG, task, run and try, each in backticks, with the [R<n>] label.
- **When** -- first and last time it appears in the evidence, and how many runs of those in
  scope failed this way.
- **Test** -- the `node_id`, verbatim.
- **What happened** -- the failure message, and the traceback trimmed to the frames inside
  the project.
- **Reproduce** -- the pytest invocation that selects exactly this test.
- **Not established** -- what the evidence does not show: whether it is deterministic,
  whether it is environmental, whether it predates the runs in scope.
Do not invent a root cause, a severity, an owner, or a fix version. If a saved triage
verdict exists, quote it as a hypothesis and say so.
