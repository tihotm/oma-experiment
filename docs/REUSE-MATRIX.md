# Reuse Matrix

| Capability | Donor | Primitive found | Decision | OMA7 code still needed | Reason |
| --- | --- | --- | --- | --- | --- |
| Subject identity | in-toto attestation | `Statement` + `ResourceDescriptor` | REFERENCE | minimal adapter | Model exists, but OMA7 needs a narrower subject contract |
| Evidence predicate | in-toto attestation | `Statement.predicate` | ADOPT | serialization glue | The upstream model already matches evidence-as-predicate |
| Provenance | in-toto attestation | `Statement.subject` + predicate typing | ADOPT | mapping | Direct model reuse is closer than custom schema |
| Attestation creation | Witness | CLI signing flow | REFERENCE | none yet | Useful, but too heavy to embed wholesale in this lot |
| Verification | Witness | `witness verify` policy flow | COMPOSE | local verifier wrapper | Reuse flow concepts, not the full CLI |
| Policy validation | Witness | OPA-backed policy checks | ADOPT | local policy surface | Mature primitive with direct applicability |
| Baseline/no-patch eval | SWE-bench | `run_instance(skip_patch=...)` | ADOPT | adapter contract | Semantics are explicit and benchmark-specific |
| Grading | SWE-bench | `get_eval_report` | REFERENCE | future adapter | Avoid reimplementing benchmark grading |
| Test outcomes | SWE-bench | `TestStatus` | ADOPT | normalization layer | Preserves PASS/FAIL/ERROR/SKIP/NOT_RUN/UNKNOWN |
| Snapshot identity | Git | tree/index/status semantics | ADOPT | snapshot wrapper | Git already covers path/content/mode/tree semantics |
| B0 observation | OMA7 | normalized facts | BUILD | minimal extractor | No donor provides this exact abstraction |
| Subject identity | OMA7 + Git | frozen logical subject | ADOPT | documentation + identity wrapper | Subject is Git-backed and kept distinct from materialization |
| Materialization identity | OMA7 | canonical materialization descriptor | BUILD | identity model | Needed to separate subject from observable runtime/materialization topology |
| Execution context | OMA7 | immutable execution context identity | BUILD | identity model | No donor provides this exact contract |
| Verification context | OMA7 + SWE-bench | verification inputs | COMPOSE | canonical identity model | Existing benchmark facts are adapted into a dedicated context identity |
| Scope policy | OMA7 | canonical scope policy identity | BUILD | identity model | No donor provides the required policy binding shape |
| Provenance anchor | OMA7 + in-toto/Witness | binding abstraction only | REFERENCE | interface only | Prepared for future composition without inventing custom attestations |
