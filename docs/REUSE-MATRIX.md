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

