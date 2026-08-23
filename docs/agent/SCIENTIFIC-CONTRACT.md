# Scientific Contract

OMA7 records facts at four different levels:

- `CODE_CONFIRMED`: the code path exists and was inspected
- `TEST_CONFIRMED`: a test asserts the behavior
- `EXECUTED`: a real runtime path was exercised
- `MEASURED`: a runtime result was observed and counted

Rules:

- never promote a lower evidence level to a higher one
- never claim execution from tests alone
- never claim measurement without a real counted run
- keep current state in [docs/CURRENT-STATE.md](../CURRENT-STATE.md)
- keep work-in-progress state in [docs/agent/CURRENT-WORK.md](CURRENT-WORK.md)

