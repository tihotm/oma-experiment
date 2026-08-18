# Decisions

Append-only decision log.

## D1

- Decision: OMA7 does not build a replacement coding agent.
- Status: ACTIVE
- Evidence/rationale: project mission and governance docs
- Alternatives considered: replacement coding agent, hybrid agent stack
- Consequences: reuse-first control-layer scope

## D2

- Decision: ADOPT > COMPOSE > ADAPT > BUILD.
- Status: ACTIVE
- Evidence/rationale: reuse-first policy in governance docs
- Alternatives considered: BUILD-first development
- Consequences: donor reuse is preferred before custom construction

## D3

- Decision: property/unit tests do not equal benchmark execution.
- Status: ACTIVE
- Evidence/rationale: evidence hierarchy and scientific-state rules
- Alternatives considered: treating test confirmation as execution
- Consequences: test results do not increment real execution counters

## D4

- Decision: SWE-bench Verified is calibration, not the primary causal benchmark.
- Status: ACTIVE
- Evidence/rationale: roadmap separation
- Alternatives considered: using Verified as the primary causal benchmark
- Consequences: primary causal work remains separate from calibration

## D5

- Decision: SWE-bench-Live is the current primary causal candidate.
- Status: ACTIVE
- Evidence/rationale: roadmap framing
- Alternatives considered: only offline benchmarks
- Consequences: future causal claims must reference live-style evaluation

## D6

- Decision: ProMax is the current long-horizon candidate.
- Status: ACTIVE
- Evidence/rationale: roadmap framing
- Alternatives considered: single-shot evaluation only
- Consequences: long-horizon experiments remain deferred

## D7

- Decision: Claw clean_patch is rejected as-is.
- Status: ACTIVE
- Evidence/rationale: reuse/rejection history
- Alternatives considered: direct reuse without adaptation
- Consequences: requires adaptation if revisited

## D8

- Decision: Claw resume semantics are rejected as-is and require adaptation.
- Status: ACTIVE
- Evidence/rationale: reuse/rejection history
- Alternatives considered: direct reuse without adaptation
- Consequences: future reuse must redefine resume behavior

## D9

- Decision: Codex Exec is P0 experimental executor.
- Status: ACTIVE
- Evidence/rationale: roadmap framing
- Alternatives considered: immediate production executor
- Consequences: execution work stays experimental

## D10

- Decision: App Server is a future candidate.
- Status: ACTIVE
- Evidence/rationale: roadmap framing
- Alternatives considered: forcing app-server scope now
- Consequences: not part of current governance freeze

## D11

- Decision: Multi-agent remains deferred to E8.
- Status: ACTIVE
- Evidence/rationale: experimental ablation roadmap
- Alternatives considered: early multi-agent build
- Consequences: no multi-agent runtime in current lots

## D12

- Decision: custom attestation protocol is rejected in favor of reuse/composition.
- Status: ACTIVE
- Evidence/rationale: donor reuse policy and attestation reuse
- Alternatives considered: building an OMA7-specific attestation stack
- Consequences: in-toto/Witness remain reuse targets

## D13

- Decision: governance is versioned in-repository instead of relying on chat memory.
- Status: ACTIVE
- Evidence/rationale: repository-owned docs and policies
- Alternatives considered: chat-only governance
- Consequences: docs and policies are canonical sources

