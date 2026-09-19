# FinQA audited benchmark — independent code/protocol preflight review

**Verdict: NOT READY for protocol freeze or paid runs. Five Major findings; no Critical finding established.**

Reviewed on 2026-09-19 in `/tmp/llm-benchmark-finqa-audited`, against base/HEAD `4aaee63ec2b2657347b7fc544fa288d15d1eea27`. The reviewed implementation is an uncommitted working-tree change, including new untracked files. This is **not** the latest-exact-HEAD AI review required before merge.

Read-only review of the requested code, prompt, rubric and preparation script. No repository code changes, commits, model API calls, dataset freeze, or report publication were performed. Temporary fixtures and review artifacts are under `/tmp`. UI and independent selected-question semantic review are excluded.

Separate dataset gate update from the parent: **PASS — 20 included, 38 inspected, 18 excluded; independently fetched upstream source hash matches.** This is attributed to that separate review, not an additional semantic review here.

## Major findings

### M1 — Audited CLI cannot start a run: `str` passed to a `Path` reader

**Location:** `bench/finqa_audited.py:204`; downstream `bench/finqa.py:57`, `bench/finqa.py:319`.

`run_candidates()` sets `args.dataset = str(DATASET)`. The shared runner passes that value to `read_rows()`, which invokes `path.exists()`. Every audited run therefore raises `AttributeError: 'str' object has no attribute 'exists'` before candidate execution.

**Reproduction:** Invoke the real audited wrapper with `Namespace(models="nova-lite", run_id="entry")`, a stubbed successful freeze verification, a temporary results root, and a client factory that raises if reached. It raises the above AttributeError without reaching the client.

**Required correction:** Keep `DATASET` as a `Path`, or normalize the shared reader's input explicitly. Add an offline smoke check through the **audited wrapper**, including manifest creation and a mocked successful candidate response. Existing tests exercise the legacy wrapper and serializers separately, so they do not catch this integration failure.

### M2 — Short numeric literals and Fraction intermediates are not resource bounded

**Location:** `bench/finqa_audited.py:62–72`; `bench/finqa.py:162–230`.

The 128-character literal limit plus `finqa.number()` validation does not bound the size of an exact rational. `float("1e-1000000000")` underflows to finite `0.0`, passes validation, and `Fraction` then attempts to construct a denominator of `10**1000000000`. A short candidate program such as `add(1e-1000000000,0)` can consume excessive CPU/memory during evaluation. Repeated `multiply(#N,#N)` also grows exact integers without a magnitude/bit-length limit even within the 64-step limit.

**Reproduction:** After importing the evaluator, a subprocess evaluating `rational_number("1e-1000000000")` was restricted to two CPU seconds and 64 MiB additional virtual address space. It printed that the float validator accepts `0.0`, then was killed with return code `-9`. Normal inputs and imports completed before these limits were installed. This is not a network or sandbox self-pipe issue.

**Impact:** One malformed answer can prevent evaluation of an entire paid batch. Length/step limits do not make this interpreter bounded after moving arithmetic to `Fraction`.

**Required correction:** Validate exponent/decimal scale before constructing `Fraction`; specify and enforce rational numerator/denominator bit budgets at each operation. Reject oversized operations before allocating their result, or isolate evaluation with a hard resource budget. Add offline rejection checks for tiny literals with enormous negative exponents and repeated squaring. Preserve legitimate exact arithmetic within the declared budget.

### M3 — Large exact results become infinity and break strict JSON reporting

**Location:** `bench/finqa_audited.py:126–130`; inherited finite-result check at `bench/finqa.py:229`.

`multiply(1e308,10)` is accepted by the audited executor. Its `Fraction` and rounded `Decimal` results are finite, but `_score()` converts the latter to a Python float, producing `inf`. The evaluator returns `status="scored", execution_result=inf`. Report writing uses `allow_nan=False`, so a single such wrong answer aborts JSON output for the batch.

**Reproduction:** `evaluate_one()` with this program and `unit="ratio"` returns `inf`; `json.dumps(result, allow_nan=False)` raises `ValueError: Out of range float values are not JSON compliant: inf`.

**Required correction:** Keep exact/decimal execution results in a JSON-safe representation or explicitly classify values outside the supported output range without emitting infinity. Ensure every evaluation result is strict-JSON serializable, including extreme intermediate/final values. Do not silently impose early rounding to address this.

### M4 — Frozen protocol does not freeze the selected model execution settings

**Location:** `bench/finqa_audited.py:151–166`, `bench/finqa_audited.py:202–210`; configuration loaded in `bench/finqa.py:309`.

`protocol_identity()` includes dataset/prompt/code/units, but does not include the selected roster, model IDs/routes, model reasoning/template settings, scenario concurrency, or relevant model configuration. Runs load current `config.toml` after verification. Changing those settings after freeze therefore passes verification and allows new runs under the original freeze timestamp. A per-run manifest records the setting eventually used, but does not prove it was the setting selected before candidate answers were observed.

**Reproduction:** Replace the loaded configuration with one containing a changed model ID and audited concurrency `19`; `verify_freeze()` accepts the unchanged frozen identity. The identity function does not read configuration at all.

**Impact:** The promised pre-call, immutable experimental protocol does not bind the candidate roster or generation settings. Changing all runs consistently can still satisfy cross-model comparison checks.

**Required correction:** Freeze the selected roster and resolved generation-affecting configuration, then validate requested models and effective run settings against it before each run. Preserve the user's selected models/reasoning settings; do not “fix” this by selecting different ones. Pricing metadata may be tracked separately with explicit historical policy. Add mutation tests for reasoning, model ID/route, templates, concurrency and roster.

### M5 — Audited report trusts a freeze attachment without binding actual inputs to it

**Location:** `bench/finqa_audited.py:224–235`; comparison identity checks at `bench/finqa_compare.py:128–142`.

The audited report checks that `contract.evaluation_protocol` equals the current freeze, but never compares the contract's actual dataset/prompt/runner/DSL hashes against the corresponding hashes inside that freeze. The shared comparison checks actual snapshots against their own contracts and checks agreement between models; those are different checks. Consistently wrong snapshots/contracts carrying a valid freeze attachment are accepted as audited.

**Reproduction:** Using the real shared comparison and audited `compose()` with one temporary model, attach the current genuine protocol identity to a contract containing a different one-question dataset, different prompt, different runner/DSL hashes and output cap `17`. Keep the local snapshots consistent with that contract. Audited composition succeeds, reports `dataset.questions=20` while its aggregate has one question, and displays `request_settings.max_output_tokens=4096` while `generation_parameters.max_output_tokens=17`.

This fixture changes roster/config only to make the reproduction small; the same missing binding applies when every model in the full roster shares the altered inputs. It demonstrates a validation gap, not a claim that the normal wrapper currently generates such snapshots.

**Required correction:** Before evaluating source rows, require actual contract/snapshot identities and resolved generation settings to match the frozen protocol, including exact dataset identity/cardinality. Derive displayed settings from the verified historical contract. Add negative composition tests for a valid freeze attachment coupled to altered dataset, prompt, evaluator/runner identity or generation cap.

## Minor findings and limitations

**N1 — Truncation diagnostics are incomplete across failure shapes.** At `bench/finqa_audited.py:109–114`, empty text or an existing request error returns before checking `finish_reason`. A row with empty text and `finish_reason="max_tokens"` is a request failure but has no truncation code. Mantle incomplete responses are rejected in `bench/run.py:483–489`; `incomplete_details.reason` and partial usage/text are not preserved in the saved row, so the new truncated aggregate cannot identify those cap hits either. Valid nonempty JSON with `finish_reason="max_tokens"` is correctly rejected and counted as truncated. Primary accuracy remains conservative and failed/missing cost suppression works; this is a diagnostic/provenance limitation, partly inherited. Preserve bounded finish/incomplete metadata across the failure path and classify known truncation before generic failures.

**N2 — Advertised boolean unit cannot be scored successfully.** The prompt permits `greater` and `boolean`, and `convert()` returns `"yes"`/`"no"`, but `_score()` always parses the expected answer as a `Fraction` and converts the execution result to `float`. A correct `greater(2,1)` with boolean unit is reported as an invalid program. No boolean question was found in the selected numeric sample, so this is Minor for this pilot; either remove unsupported boolean protocol claims or implement a typed comparison branch before adding boolean questions.

**N3 — The rubric and preparation implementation are not bound by the freeze.** `rubric.txt` and `prepare.py` are requested review artifacts but absent from `protocol_identity()`. The in-code `POLICY`, prompt, selected data and selection audit are bound, so this is not an immediate scoring change. Bind these artifacts if the frozen protocol is intended to cover its published rubric and reproducible preparation procedure.

**N4 — “28 actual request serializers” overstates test coverage.** Mantle uses `httpx.MockTransport` and inspects serialized request bytes. Bedrock replaces `client.converse`, and OpenAI replaces `chat.completions.create`, so those paths inspect call arguments before SDK serialization. All 28 configured model cases pass their checks; this does not validate provider acceptance or effective provider defaults. No live checks were performed or are requested by this review.

## Offline verification

All checks used `UV_PROJECT_ENVIRONMENT=/home/atomoh/llm-benchmark/.venv`, `UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache` and `uv run --offline`. Later invocations used `--no-sync` to avoid modifying/re-resolving the shared environment.

The following passed outside the sandbox, with mocked transports and a 45-second process timeout:

```bash
timeout 45s env \
  UV_PROJECT_ENVIRONMENT=/home/atomoh/llm-benchmark/.venv \
  UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache \
  PYTHONDONTWRITEBYTECODE=1 \
  uv run --offline --no-sync python -u -c \
  'from bench import finqa_audited, finqa_compare, finqa, report; finqa_audited.selfcheck(); finqa_compare.selfcheck(); finqa.selfcheck(); report._selfcheck()'
```

Results:

- Audited arithmetic/unit/negative-control/leakage/reference selfcheck: PASS.
- 28 configured mocked request checks: PASS.
- Legacy FinQA end-to-end mocked run/cache/evaluate/report selfcheck: PASS.
- Comparison normalization/provenance selfcheck: PASS.
- Translation report cost/aggregation selfcheck: PASS.
- Direct `prepare(Path("/tmp/finqa-upstream/dataset/dev.json"))` exactly reproduces the current 20 prepared records: PASS. This checks reproducibility, not the independently reviewed financial semantics.
- Independent exact `1/7 × 7`, rational table average, money scaling and negative half-even rounding checks: PASS.
- Invalid DSL still retains successful transport cost: with 1,000 input tokens at $2/M and 500 output tokens at $4/M, estimated cost is `$0.004`; request failure withholds the estimate: PASS.
- Missing, wrong-unit, valid, truncated and incomplete classifications were probed.
- 2,000-level JSON nesting did not crash this Python build; no unconfirmed recursion finding is asserted.

The sandboxed request check stalled in the asyncio selector after a worker finished. A timed traceback and successful identical escalated execution establish this as the reported sandbox self-pipe issue, not a product defect.

Independent reproducible probes: `/tmp/finqa-audited-review-checks.py`.
Captured output: `/tmp/finqa-audited-review-checks.log`.
The probes intentionally reproduce existing failures and do not constitute passing regression tests for fixes.

## Exact reviewed file SHA-256

The seven requested file hashes were captured during inspection and rechecked after all probes; they remained identical. Config, roster, dataset, selection and dependency hashes below provide supporting context. Dataset hash capture is not a semantic approval.

```text
e7614905a533934182d1eed806dfb24c1a987ff99285757b54a869a1ec6fd960  bench/finqa_audited.py
bd4b05630aa05d80eecc3d9045f6c7465aa81041239df9dfeca661f08eb0cda8  bench/finqa.py
8b3eeb66dcbe0347d114eb99fcc976f7f09b370eae145591bb1a119f64cdecd4  bench/finqa_compare.py
2354b658cc6381c8ef62033b941e245a9a85e0774224a1f32a782d41833ff10c  bench/run.py
723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7  scenarios/finqa_audited/prompt.txt
6cc4081bd68c91f9401b9b59163e20e3fceb900604fcce1c4aa3cc9efd7d5fd4  scenarios/finqa_audited/rubric.txt
71a0be6a9ea5deb49c21405c30a21822cc3e7eddac8f481610a62f26bc3d4c25  scenarios/finqa_audited/prepare.py
daf08588d7d27771456028d4e20041533b62ca3f4c6b05f6dec33602162ba745  scenarios/finqa_audited/selection-audit.json
db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6  data/finqa-audited-dev.jsonl
0b461a8840b002343f80ab79db2662d5e92ba6019f25adf79d603d747846d683  config.toml
4c845d91260ce5bbf2d23ad88a6ce6cc510807ba1647fc095b031720024e10dc  bench/report.py
0e4d261662ef0b363d43aefe6164ad1998f67f510f027ca105210ea676bfd32d  uv.lock
5355821d0bdfb592cbfc2ea116b7c4d518d1900a7ffd3e93b44f65f24b310c01  docs/results/integrated-2026-09-17.json
```

Before paid runs, correct M1–M5, repeat the targeted offline checks, retain the separately passed dataset gate, and freeze the corrected artifacts. Before merge, obtain an AI review of the latest exact PR HEAD and satisfy the repository's required checks; this preflight does not waive that requirement.

---

# Exact-HEAD re-review — ec077826c6d35f11a8a1bdc184727174d6c9d31e

**2026-09-19 verdict: PASS for the reviewed code/protocol preflight. Zero unresolved Critical or Major findings in scope. M1–M5 are resolved; N1–N4 are addressed.** This verdict supersedes the original code preflight verdict above for the exact bytes listed below. Live GPU serving verification remains a separate operational prerequisite, described under R1.

Reviewed the committed fixes in `/tmp/llm-benchmark-finqa-audited`, reran all five offline selfcheck suites, and added independent probes. HEAD remained `ec077826c6d35f11a8a1bdc184727174d6c9d31e`. The reviewed code/config/protocol files match that commit. Concurrent edits observed in `docs/finqa.html` and `scenarios/finqa_audited/README.md` are outside this exact-code verdict; no reviewer changes were made to the repository. No paid requests, live provider calls, deployment commands, or real protocol freeze were performed.

## Disposition of previous findings

| Finding | Disposition and verified evidence |
| --- | --- |
| M1 — path-type crash | **Resolved.** The audited wrapper passes `DATASET` as a `Path`. The real audited wrapper runs all 20 mocked requests, creates the manifest/cache, and resumes without initializing a client. |
| M2 — unbounded rationals | **Resolved.** Exponents are checked before `Fraction` allocation, including whitespace-before-percent and `const_` forms. `BoundedFraction` checks conservative operand/result bit budgets for all four arithmetic operations and reverse operations, including table `sum()`/average. Original exponent and repeated-squaring attacks reject promptly. The budget can conservatively reject an operation whose reduced result would fit; that is a bounded-policy choice, not silent numerical rounding. |
| M3 — infinity breaks reporting | **Resolved.** The original `multiply(1e308,10)` result becomes `invalid_program` with `numeric_range`, and serializes with strict JSON. A large *intermediate* followed by exact cancellation still scores correctly, confirming that the fix did not introduce early rounding or reject all large intermediates merely because they exceed float range. |
| M4 — settings absent from freeze | **Resolved for configuration identity.** The freeze includes the selected generation-model roster/settings, scenario config, AWS region, output cap, timeout, temperature exceptions, vLLM image and context. Mutating model ID/route/reasoning/template/concurrency/enabled status, extra vLLM arguments, scenario concurrency/image/context or AWS region invalidates verification. Mutable price-only metadata remains intentionally outside generation identity. See R1 for the distinction between configured and live serving state. |
| M5 — detached freeze attachment | **Resolved.** Before scoring, composition binds contract dataset/prompt/runner/DSL hashes, request settings, model settings, concurrency and actual dataset/prompt snapshots to the freeze, and requires 20 records. It also checks the resulting roster. All 28 model fixtures / 560 answers compose correctly; attached-freeze fixtures with changed contract fields or changed actual snapshots fail. Displayed cap/default concurrency derive from the verified protocol. |
| N1 — incomplete truncation evidence | **Addressed.** Known cap termination is classified before blank/error handling. Mantle incomplete reason plus partial text/usage are retained; failed OpenAI/Bedrock-style results retain their partial fields. An independent end-to-end blank `length` response preserved the failed 4,096 output tokens under `failed_response`, kept successful-token fields null, and evaluated as `truncated`. |
| N2 — boolean scoring | **Addressed.** Boolean scoring compares the typed `"yes"`/`"no"` answer without forcing it through `Fraction` or float conversion. The boolean scoring selfcheck passes. The selected prepared dataset remains numeric; this does not claim that all dataset-preparation paths now support boolean audit references. |
| N3 — missing rubric/preparation binding | **Addressed.** The rubric, preparation script and dataset-review artifact hashes are now included in the protocol identity. |
| N4 — serializer wording | **Addressed.** The request check now accurately identifies Mantle serialized JSON versus Bedrock/OpenAI SDK arguments. It continues to cover all 28 configured models without claiming provider acceptance. |

## R1 — Minor operational limitation: live serving checks occur at report time

`bench/finqa_audited.py:288` verifies the frozen **configuration** before invoking a model. It does not validate `serving.json` or query the live vLLM endpoint/deployment. Model/instance/TP checks in the shared comparison and image/context checks in audited `compose()` occur after responses have been collected.

Independent reproduction: with a genuine temporary frozen configuration, place a `serving.json` containing the wrong model, image and context in the temporary run directory, then call the real audited wrapper with a mocked vLLM transport. All 20 calls are issued successfully. The later report checks would reject the mismatched serving evidence.

This does **not** reopen M4/M5: configured generation settings and accepted report inputs now bind correctly, and no mismatched published report was demonstrated. It means this offline code pass does not establish that a currently running GPU service matches the frozen experiment. Before GPU calls, verify the deployed model, image digest, context, TP/instance and applicable vLLM arguments and retain serving evidence. A shared pre-call serving validator would reduce the risk of collecting unusable responses. No live state was inspected in this review.

## Re-review verification

The following command completed successfully with escalation solely to avoid the known sandbox asyncio self-pipe issue:

```bash
timeout 60s env \
  UV_PROJECT_ENVIRONMENT=/home/atomoh/llm-benchmark/.venv \
  UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache \
  PYTHONDONTWRITEBYTECODE=1 \
  uv run --offline --no-sync python -u -c \
  'from bench import finqa_audited, finqa_compare, finqa, report, run; finqa_audited.selfcheck(); finqa_compare.selfcheck(); finqa.selfcheck(); report._selfcheck(); run._selfcheck()'
```

**PASS:** audited, legacy FinQA, comparison, cost/report and runner reliability selfchecks. This includes the 28 request paths, real audited 20-question wrapper/cache, 28-model/560-answer composition, freeze/contract/snapshot mutations, and partial Mantle-response retention. Log: `/tmp/finqa-ec07782-selfchecks.log`.

Independent probes also passed:

- Original huge-exponent and nonfinite-final regressions, repeated-squaring rejection, strict JSON error results.
- Exact `1/7 × 7`, `1/3 × 3`, table averaging, and a large intermediate followed by cancellation.
- 500 deterministic rational pairs × four arithmetic operations compared exactly against standard `Fraction` (2,000 comparisons).
- Table summation under an intentionally reduced bit budget rejects before exceeding that budget.
- Additional vLLM arguments/image/context and region mutations invalidate the freeze; a price-only mutation does not.
- End-to-end blank truncated transport response preserves failed usage and receives the correct evaluation classification.

Probe source: `/tmp/finqa-ec07782-independent.py`.
Log: `/tmp/finqa-ec07782-independent.log`.
All probe writes are temporary fixtures outside the repository; transport calls are mocked. The R1 observation is explicitly logged separately from passing gates.

## Exact re-reviewed SHA-256

```text
5c3bebb856196c593e4273a8283c0402bf9def4c14c5d6ed6cb1954caf03997a  bench/finqa_audited.py
bd4b05630aa05d80eecc3d9045f6c7465aa81041239df9dfeca661f08eb0cda8  bench/finqa.py
8b3eeb66dcbe0347d114eb99fcc976f7f09b370eae145591bb1a119f64cdecd4  bench/finqa_compare.py
6c6e4738b13b447b417b6a651ef51499bff2fd5bf2875fda7f1940c737c0fe5c  bench/run.py
723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7  scenarios/finqa_audited/prompt.txt
6cc4081bd68c91f9401b9b59163e20e3fceb900604fcce1c4aa3cc9efd7d5fd4  scenarios/finqa_audited/rubric.txt
71a0be6a9ea5deb49c21405c30a21822cc3e7eddac8f481610a62f26bc3d4c25  scenarios/finqa_audited/prepare.py
5467817b170ab052679260379f91c7d3e084e39cf33be6699c68239ea520402f  scenarios/finqa_audited/dataset-review.md
daf08588d7d27771456028d4e20041533b62ca3f4c6b05f6dec33602162ba745  scenarios/finqa_audited/selection-audit.json
db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6  data/finqa-audited-dev.jsonl
02e5e0ff6397ce2310c2dfd84fe2e7f4da1765611f078c6a65d575b3f8c78fef  config.toml
4c845d91260ce5bbf2d23ad88a6ce6cc510807ba1647fc095b031720024e10dc  bench/report.py
0e4d261662ef0b363d43aefe6164ad1998f67f510f027ca105210ea676bfd32d  uv.lock
5355821d0bdfb592cbfc2ea116b7c4d518d1900a7ffd3e93b44f65f24b310c01  docs/results/integrated-2026-09-17.json
```

The separately approved dataset and selection bytes are unchanged. This scoped exact-HEAD preflight permits proceeding with the corrected freeze workflow and the separately verified runtime setup; it does not replace the later full final-HEAD review covering raw results and the completed PR. No merge approval is issued here.
