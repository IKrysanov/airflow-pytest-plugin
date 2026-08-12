SKILL: flaky tests and quarantine
A test is flaky when the same `node_id` both passes and fails across the runs in evidence,
not when it merely fails often. Say which of the two the evidence supports, and give the
pass/fail split you counted it from. Distinguish a test that alternates from one that broke
at a point in time and stayed broken -- the second is a regression, and calling it flaky
sends the reader down the wrong path.
When asked what to do about it, offer the mechanisms this project actually has, and be plain
that each hides a real signal:
- `@pytest.mark.flaky` on the test, if the suite has a rerun plugin;
- `@pytest.mark.skip(reason=...)` with a link to the issue, for a test that cannot be fixed
  now;
- the dashboard's own quarantine, which keeps the test running and its history visible while
  taking it out of the pass-rate that decides whether a run counts as successful.
Recommend quarantine over skipping when the test still carries information. Never suggest
deleting a test.
