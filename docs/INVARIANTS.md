# Invariant Registry

Canonical 1:1 registry:

- [CANONICAL-INVARIANT-REGISTRY.md](CANONICAL-INVARIANT-REGISTRY.md)

Current registry is versioned here. IDs MUST remain stable.

Format per entry:
- ID
- Statement
- Origin / rationale
- Current evidence level
- Implementation status
- Runtime confirmation status
- Related implementation/tests if known

I1
- Statement: OMA7 is a control layer above existing coding agents, not a replacement coding agent.
- Origin / rationale: project mission
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/SPEC.md, AGENTS.md

I2
- Statement: Reuse-first ordering is ADOPT > COMPOSE > ADAPT > BUILD.
- Origin / rationale: operating rule
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/SPEC.md, AGENTS.md, docs/REUSE-MATRIX.md

I3
- Statement: Silent scope expansion is prohibited.
- Origin / rationale: governance control
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md, PLANS.md

I4
- Statement: Tests, oracles, CI, and policies MUST NOT be weakened to obtain PASS.
- Origin / rationale: fail-closed governance
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md

I5
- Statement: `TEST_CONFIRMED` is not `EXECUTED`.
- Origin / rationale: evidence hierarchy
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NO
- Related implementation/tests if known: AGENTS.md, docs/SPEC.md

I6
- Statement: Acceptance boundaries MUST fail closed.
- Origin / rationale: scientific safety
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md, docs/EVIDENCE-MODEL.md

I7
- Statement: OMA7 MUST NOT claim measured product advantage without real causal evidence.
- Origin / rationale: scientific discipline
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md, docs/SPEC.md

I8
- Statement: SubjectIdentity is Git-backed.
- Origin / rationale: reuse Git primitives
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I9
- Statement: SubjectIdentity describes the logical frozen subject and is not sufficient for full materialization/runtime topology.
- Origin / rationale: identity/materialization separation
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/IDENTITY-MODEL.md

I10
- Statement: MaterializationIdentity is distinct from SubjectIdentity.
- Origin / rationale: current contract
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I11
- Statement: MaterializationIdentity binds observable materialization topology.
- Origin / rationale: contract field set
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I12
- Statement: ExecutionContextIdentity is distinct from VerificationContextIdentity.
- Origin / rationale: current contract
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I13
- Statement: ExecutionContextIdentity MUST fail closed when mandatory immutable fields are missing.
- Origin / rationale: immutable execution identity
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I14
- Statement: VerificationContextIdentity canonicalizes benchmark verification inputs.
- Origin / rationale: evidence binding
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I15
- Statement: ScopePolicyIdentity is a first-class identity.
- Origin / rationale: scope control integrity
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I16
- Statement: ProvenanceAnchorIdentity is a binding abstraction, not a custom attestation system.
- Origin / rationale: reuse in-toto/Witness
- Current evidence level: DOCUMENTED
- Implementation status: PARTIAL
- Runtime confirmation status: NO
- Related implementation/tests if known: docs/IDENTITY-MODEL.md, docs/REUSE-MATRIX.md

I17
- Statement: Evidence binds subject, materialization, execution, verification, scope, provenance, result, and schema_version.
- Origin / rationale: current contract
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, tests/test_oma7_core.py

I18
- Statement: Evidence applicability requires PASS.
- Origin / rationale: acceptance rule
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/models.py, src/oma7/verifier.py

I19
- Statement: Missing required evidence identities are not applicable.
- Origin / rationale: fail-closed acceptance
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I20
- Statement: Unsupported evidence schema is invalid / not applicable.
- Origin / rationale: schema evolution safety
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/swebench_adapter.py, tests/test_oma7_core.py

I21
- Statement: Unknown acceptance-relevant enum/value fails closed.
- Origin / rationale: fail-closed acceptance
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/swebench_adapter.py, tests/test_oma7_core.py

I22
- Statement: Dictionary ordering must not alter identity.
- Origin / rationale: canonical serialization
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I23
- Statement: Semantically identical normalized structures produce equal identities.
- Origin / rationale: canonical serialization
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I24
- Statement: Material changes must produce unequal identities.
- Origin / rationale: mutation staleness
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I25
- Statement: Subject mutation invalidates acceptance evidence.
- Origin / rationale: stale evidence
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I26
- Statement: Materialization mutation invalidates acceptance evidence.
- Origin / rationale: stale evidence
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I27
- Statement: Execution context mutation invalidates acceptance evidence.
- Origin / rationale: stale evidence
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I28
- Statement: Verification context mutation invalidates acceptance evidence.
- Origin / rationale: stale evidence
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I29
- Statement: Scope policy mutation invalidates acceptance evidence.
- Origin / rationale: stale evidence
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py, src/oma7/lifecycle.py

I30
- Statement: Provenance anchor mutation invalidates acceptance evidence.
- Origin / rationale: provenance binding
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I31
- Statement: Fail evidence never authorizes acceptance.
- Origin / rationale: acceptance rule
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I32
- Statement: Snapshot materialization must be a distinct copy from source workspace.
- Origin / rationale: immutable submission
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I33
- Statement: Git identity changes on content mutation.
- Origin / rationale: content-addressed subject identity
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I34
- Statement: `skip_patch=True` suppresses the effective model patch.
- Origin / rationale: SWE-bench no-patch contract
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/swebench_contract.py, tests/test_oma7_core.py

I35
- Statement: B0 adapter extracts facts only.
- Origin / rationale: adapter layering
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NO
- Related implementation/tests if known: docs/EVIDENCE-MODEL.md, tests/test_oma7_core.py

I36
- Statement: Qualification is separate from observation extraction.
- Origin / rationale: layer separation
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: src/oma7/qualifier.py, tests/test_oma7_core.py

I37
- Statement: GOVERNANCE artifacts live in-repository instead of chat memory.
- Origin / rationale: durable knowledge
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/SPEC.md, docs/CURRENT-STATE.md

I38
- Statement: Current state docs MUST reflect factual repository state only.
- Origin / rationale: truthfulness
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md

I39
- Statement: Experimental lots MUST record baseline HEAD.
- Origin / rationale: reproducibility
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: PLANS.md

I40
- Statement: Experimental lots MUST record excluded scope.
- Origin / rationale: scope control
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: PLANS.md

I41
- Statement: Experimental lots MUST record claims promoted and claims left open.
- Origin / rationale: evidence tracking
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: PLANS.md

I42
- Statement: Current real execution counters remain zero until actual executions exist.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I43
- Statement: `REAL_CODEX_EXEC = 0`.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I44
- Statement: `REAL_CONTAINER_G0 = 0`.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I45
- Statement: `REAL_A1 = 0`.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I46
- Statement: `REAL_QUALIFIED_PAIRS = 0`.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I47
- Statement: `MEASURED_PRODUCT_EFFECT = NO`.
- Origin / rationale: scientific state
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I48
- Statement: Current test command is `python -m unittest discover -s tests -v`.
- Origin / rationale: canonical validation
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md, docs/CURRENT-STATE.md

I49
- Statement: Current discovered test count is recorded in current-state documentation.
- Origin / rationale: auditability
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-STATE.md

I50
- Statement: Documentation and policy artifacts are canonical for governance.
- Origin / rationale: source-of-truth control
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/SPEC.md, docs/CURRENT-STATE.md, PLANS.md

I51
- Statement: `docs/CURRENT-CONTRACT-GAP-AUDIT.md` remains useful evidence.
- Origin / rationale: historical audit preservation
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/CURRENT-CONTRACT-GAP-AUDIT.md

I52
- Statement: `docs/IDENTITY-MODEL.md` is canonical for identity terminology.
- Origin / rationale: terminology freeze
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/IDENTITY-MODEL.md

I53
- Statement: `docs/EVIDENCE-MODEL.md` is canonical for evidence binding rules.
- Origin / rationale: acceptance semantics
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/EVIDENCE-MODEL.md

I54
- Statement: `docs/REUSE-MATRIX.md` is canonical for donor reuse decisions.
- Origin / rationale: reuse-first policy
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/REUSE-MATRIX.md

I55
- Statement: `AGENTS.md` is the persistent operational instruction file.
- Origin / rationale: agent governance
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: AGENTS.md

I56
- Statement: The governance freeze does not freeze the final architecture.
- Origin / rationale: roadmap separation
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/ROADMAP.md

I57
- Statement: The engineering roadmap and experimental roadmap are separate.
- Origin / rationale: causal discipline
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/ROADMAP.md

I58
- Statement: E2+ experimental stages are not justified merely by supporting primitives existing in code.
- Origin / rationale: causal evidence separation
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/ROADMAP.md

I59
- Statement: Governance validation tests provide real enforcement value only.
- Origin / rationale: avoid brittle prose tests
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: tests/test_oma7_core.py

I60
- Statement: AGENTS.md references the canonical SPEC, INVARIANTS, CURRENT-STATE, and ROADMAP docs.
- Origin / rationale: discoverability
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I61
- Statement: experiment-policy preserves scientific-state counters as zero.
- Origin / rationale: machine-readable governance
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: policies/experiment-policy.yaml

I62
- Statement: experiment-policy forbids interpreting TEST_CONFIRMED as EXECUTED.
- Origin / rationale: evidence hierarchy
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: policies/experiment-policy.yaml, tests/test_oma7_core.py

I63
- Statement: evidence-policy declares required identities declaratively.
- Origin / rationale: machine-readable acceptance rules
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: policies/evidence-policy.yaml

I64
- Statement: scope-policy defaults unknown sensitive role behavior to REVIEW or BLOCK, not ALLOW.
- Origin / rationale: fail-closed scope control
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: policies/scope-policy.yaml

I65
- Statement: evidence schema versioning is explicit.
- Origin / rationale: schema evolution safety
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: schemas/evidence.schema.json

I66
- Statement: policy schema validates governance structures introduced in this lot.
- Origin / rationale: machine-readable governance
- Current evidence level: CODE_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: schemas/policy.schema.json

I67
- Statement: required evidence identities cannot be omitted.
- Origin / rationale: acceptance safety
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I68
- Statement: invalid policy enum/value fails validation.
- Origin / rationale: fail-closed policy handling
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I69
- Statement: CURRENT-STATE counters agree with machine-readable policy counters.
- Origin / rationale: consistency
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py, docs/CURRENT-STATE.md, policies/experiment-policy.yaml

I70
- Statement: invariant IDs are unique.
- Origin / rationale: registry integrity
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I71
- Statement: invariant registry includes I1 through I74 with no gaps or renumbering.
- Origin / rationale: stable registry
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I72
- Statement: provenance anchor/root mismatch invalidates acceptance. [legacy, non-canonical; see I30]
- Origin / rationale: provenance binding
- Current evidence level: TEST_CONFIRMED
- Implementation status: PARTIAL
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I73
- Statement: canonical policy ordering differences do not change identity.
- Origin / rationale: canonicalization
- Current evidence level: TEST_CONFIRMED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: YES
- Related implementation/tests if known: tests/test_oma7_core.py

I74
- Statement: current runtime implementation remains provisional and may be extended only by evidence-derived lots.
- Origin / rationale: scientific method
- Current evidence level: DOCUMENTED
- Implementation status: IMPLEMENTED
- Runtime confirmation status: NOT_REQUIRED
- Related implementation/tests if known: docs/ROADMAP.md, docs/CURRENT-STATE.md
