SKILL: comparing runs
Comparing two runs or two periods, report only differences the evidence establishes:
- tests that changed outcome, each with its `node_id` and both outcomes;
- tests present in one side and absent from the other -- added, removed or not collected,
  and say which of those the evidence can distinguish;
- totals on each side, and the difference between them;
- durations only when the same test ran on both sides.
Two runs failing the same way is not evidence that one caused the other, and a change that
coincides with a deploy is not evidence the deploy caused it. If asked why something
changed, say what changed and name what would settle the question -- do not narrate a cause
the evidence does not contain.
