# Contributing

Thanks for helping. Boardcheck is small on purpose: the checks are plain Python with no dependencies, and they run
on your own machine without calling the network.

## Most useful right now

- **Field observations.** Saw a board whose numbers didn't add up, or a listing Boardcheck missed or flagged
  wrongly? Use the [field observation form](https://github.com/Echolonius/boardcheck/issues/new?template=field-observation.yml).
  Real cases are how the thresholds get better.
- **Bugs.** Use the [bug form](https://github.com/Echolonius/boardcheck/issues/new?template=bug.yml), with the
  listings (or a trimmed copy) that show the problem.
- **New checks.** Open an issue first. A new check needs a stable `AMS-*` ID, an entry in [SPEC.md](SPEC.md),
  evidence from a real board, and tests.

For a security problem, don't open an issue: see [SECURITY.md](SECURITY.md).

## Pull requests

- One change per pull request, with a test that fails without it.
- No new dependencies and no network access in the checks. The MCP server's `mcp` package stays the only optional
  extra.
- If a check's behaviour changes, update [SPEC.md](SPEC.md) and [CHANGELOG.md](CHANGELOG.md).
- AI-assisted pull requests are welcome. Say so in the description.

## Running the tests

```bash
python -m unittest discover -s tests -v
node --check docs/boardcheck.js
```

The test workflow runs the same commands on Python 3.9 to 3.12.
