# TAT-QA official-rule subset

Source: Zhu et al., **TAT-QA: A Question Answering Benchmark on a Hybrid of
Tabular and Textual Content in Finance**, ACL 2021,
https://aclanthology.org/2021.acl-long.254/.

The official released test gold is pinned to NExTplusplus/TAT-QA revision
`870accc41953dcde885aabeb963d94aabdc0fbc3`:
https://github.com/NExTplusplus/TAT-QA/tree/870accc41953dcde885aabeb963d94aabdc0fbc3.
The dataset is licensed **CC BY 4.0**, as declared in the upstream README:
https://creativecommons.org/licenses/by/4.0/. The upstream evaluator code is
separately MIT licensed; its original license is in `bench/vendor/tatqa/LICENSE`.
Only the evaluator's `tatqa_utils` import is changed to a relative import.

`source-test-gold.json` is the unmodified source file. `prepare` selects 200
questions from 200 distinct table contexts using seed 20261027,
with 86 span, 84 arithmetic, 25 multi-span and 5 count questions. Type quotas
approximate the original test proportions. Questions are selected without
candidate answers, rarest type first, from seeded permutations of sorted IDs.
The released data and all selected gold remain local; candidate inputs contain
only the table, paragraph text and question, without gold type or scale.

This is a published official-rule test subset, **not** the official full
leaderboard. Numeric scaling, rounding, percent handling, span normalization
and multi-span matching follow the pinned upstream evaluator unchanged.
Only an outer JSON fence may be stripped; invalid, missing, failed and
truncated responses score zero in the full 200-question denominator.

```bash
uv run python -m bench.tatqa --selfcheck
uv run python -m bench.tatqa prepare
uv run python -m bench.tatqa run --run-id tatqa-20261027 --freeze-only
uv run python -m bench.tatqa run --run-id tatqa-20261027
uv run python -m bench.tatqa report --run-id tatqa-20261027
```

All enabled generative API models without a `base_url` are frozen before calls.
`--models name1,name2` executes a subset of that frozen roster; it never edits
the cohort. `--parallel-models 4` bounds simultaneous model batches across
local run processes and is frozen; each model retains its configured request concurrency/reasoning.
Separate processes may execute disjoint model subsets of the same frozen run.
Overlapping model execution is rejected by a local exclusive lock. A resume
skips successful requests, including syntactically invalid answers; failed,
truncated or missing requests are retried on explicit resume. Every attempt is retained in append-only JSONL.
Use a new run ID when any frozen code, data, prompt or settings change.

Reports retain all frozen models, including models whose requests never ran.
Costs are configured-rate estimates for complete successful response sets;
expired pricing is withheld. Retry/failed-call costs and infrastructure costs
are excluded. Cost and latency appear only at the whole-model level.
