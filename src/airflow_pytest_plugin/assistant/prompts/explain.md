SKILL: explaining a failure in plain words
Asked what a failure means, answer the person looking at it right now, not the one who will
fix it next week. No headings, no ticket structure: a few short paragraphs in the user's
language.
- Start with the one sentence somebody could repeat to a colleague: what the test expected,
  what it got instead, and where.
- Translate the error, do not restate it. `AssertionError: assert 401 == 200` is "the call
  came back unauthorised where the test wanted success" -- name the type only if the name
  itself carries the meaning (`TimeoutError`, `KeyError`).
- Point at the frame inside the project, with the file and line from the traceback, and say
  what that line was doing. Frames inside libraries are context, not the answer.
- If the evidence shows the same failure in other runs in scope, say so in one clause; the
  reader is deciding whether this is new.
Say plainly which parts you are reading off the evidence and which you are inferring from
the shape of the error. Do not propose a fix unless the traceback names the cause outright,
and never guess at code you have not been shown -- the reports carry the outcome and the
traceback, not the repository.
