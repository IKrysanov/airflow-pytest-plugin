SKILL: a digest of the runs in scope
Asked to summarise, write what somebody would say out loud at a standup: short, in the
user's language, and safe to repeat without opening the dashboard.
- Open with the shape of it: how many runs are in scope, how many were green, and whether
  that is better or worse than the earlier runs among them.
- Then what is broken, grouped by cause rather than listed by test: several tests failing on
  one error are one item, with the count and the `node_id`s that carry it, cited [R<n>].
- Name anything that changed status inside the scope -- newly failing, newly passing, newly
  slow -- because that is what a standup is for. If nothing changed, say that too.
- Close with what the runs cannot tell you, in one line: whoever hears this will ask.
Numbers come from the evidence and are quoted exactly; never round a count or estimate one
that is not there. No headings, no bullet list longer than the failures deserve, and no
advice about what to do next unless it was asked for -- that is `/priority`.
