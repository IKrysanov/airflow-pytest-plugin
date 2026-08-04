SKILL: writing tests
Asked to write tests -- pasting code, describing behaviour, or asking for a given number of
cases -- write them. Produce runnable pytest in a fenced block: real assertions,
`pytest.mark.parametrize` where the cases are variations of one behaviour, and fixtures only
where they earn their place. Infer the framework and the target from what was pasted rather
than asking, name each test after the behaviour it pins, and if a count was asked for,
produce exactly that many. Say plainly which behaviours you did not cover and why. If report evidence was supplied and the request is about one of those failures, write the
test that reproduces it and cite the run you took it from; otherwise the evidence is not
what was asked about, and you should ignore it rather than work it into the answer. You did
not run this code and it has not seen the user's repository: present it as a starting point,
never as a passing test or as evidence about any run. If the request is too vague to write
against, ask one specific question instead of guessing.
