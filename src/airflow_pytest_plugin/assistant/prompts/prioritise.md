SKILL: what to fix first
Rank by what the evidence supports, and show the ranking as a short ordered list with the
reason on each line. Order by, in this order: how many distinct runs the failure blocks;
whether it fails deterministically (a flaky test is usually not the first thing to fix);
how many other tests fail with the same message or in the same frame, which suggests one
cause; and the duration cost when a slow test is what the question is about.
State the rule you ranked by, so the reader can disagree with it. Say plainly that this is
an ordering of symptoms: the evidence shows what failed and how often, never which cause is
cheapest to fix, and never business impact. Do not assign story points, severities or
owners.
