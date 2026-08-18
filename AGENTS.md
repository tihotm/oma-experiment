# OMA7 Operational Rules

You are working on OMA7.

OMA7 is a control layer above existing coding agents, not a replacement coding agent.

Required order: `ADOPT > COMPOSE > ADAPT > BUILD`

Do not silently expand scope.
Do not weaken tests, oracles, CI, or policies to obtain PASS.
Acceptance boundaries MUST fail closed.

Evidence levels are distinct and must not be conflated:

- `DOCUMENTED`
- `CODE_CONFIRMED`
- `TEST_CONFIRMED`
- `EXECUTED`
- `MEASURED`

`TEST_CONFIRMED` is not `EXECUTED`.

Do not claim measured product advantage without real causal evidence.

Canonical docs:

- [docs/SPEC.md](docs/SPEC.md)
- [docs/INVARIANTS.md](docs/INVARIANTS.md)
- [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)

Canonical test command:

`python -m unittest discover -s tests -v`

