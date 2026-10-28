# Bedrock model exclusions — 2026-10-28

The user supplied a Bedrock deprecation list without a notice URL or effective
date. Nine configured API models match that list, including the `us.` inference
profiles for the listed Meta foundation model IDs. They are now `enabled = false`
for new runs. Model IDs, prices and all historical observations remain intact.
This is a repository exclusion policy; it does not assert that these endpoints
are already unavailable.

| Config name | Config model ID | Documentation checked 2026-10-28 |
| --- | --- | --- |
| nemotron-nano-3-30b | nvidia.nemotron-nano-3-30b | Card: Active; EOL N/A |
| glm-4.7-flash | zai.glm-4.7-flash | Legacy 2026-09-30; EOL 2027-03-30 |
| qwen3-32b | qwen.qwen3-32b-v1:0 | Card: Active; EOL N/A |
| nemotron-super-3-120b | nvidia.nemotron-super-3-120b | Card: Active; EOL N/A |
| llama4-scout | us.meta.llama4-scout-17b-instruct-v1:0 | Legacy 2026-09-30; EOL 2027-03-30 |
| ministral-14b | mistral.ministral-3-14b-instruct | Card: Active; EOL N/A |
| qwen3-235b-a22b | qwen.qwen3-235b-a22b-2507-v1:0 | Card: Active; EOL N/A |
| llama4-maverick | us.meta.llama4-maverick-17b-instruct-v1:0 | Legacy 2026-09-30; EOL 2027-03-30 |
| llama-3.3-70b-bedrock | us.meta.llama3-3-70b-instruct-v1:0 | Legacy 2026-09-30; EOL 2027-03-30 |

The [AWS lifecycle table](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html)
lists the four dated transitions for `us-west-2`, the configured Converse region.
The five remaining model cards still state Active and EOL N/A. Source URLs and
table rows are saved in [documentation-evidence.json](documentation-evidence.json).
The same day's read-only `aws bedrock list-foundation-models --region us-west-2`
query returned ACTIVE for all nine foundation models, including the four marked
Legacy by the documentation. The raw filtered response is saved in
[aws-lifecycle-us-west-2.json](aws-lifecycle-us-west-2.json). These conflicting
signals are preserved separately; no candidate inference was performed.

The remaining list entries are not configured as matching Bedrock endpoints.
Self-hosted Llama 3.1/3.3 use downloadable weights and are unaffected by Bedrock
lifecycle changes. The new TAT-QA API cohort contains 26 models, down from 35.

Published 35-model TAT-QA results retain their frozen roster and scores. Existing
manifests, grading code, frozen contracts and website files are unchanged. Old
TAT-QA runs can still be loaded and reported from their frozen contracts; a new
collection must use a new run ID rather than mutate a historical cohort.

The legacy `bench.finqa_audited` entrypoint includes the current enabled roster
in `protocol_identity()`, so its historical freeze check rejects this reduced
roster. Reproduce that historical protocol at its original Git revision (as
already required for its frozen collector), with the original config; do not
rewrite `freeze.json` or change the grader to bypass this check. This exclusion
does not alter published audited FinQA reports. For the immediately preceding
configuration and 35-model TAT-QA cohort, use revision
`d8478791d16c0eceeb9506905c1a3ffa94df75d8`.

Validation results are recorded in [verification.json](verification.json).
The prior website content review remains applicable because `docs/` is unchanged;
its reviewed source hashes are checked against
`validation/tatqa-200/content-review.json` (100/100, threshold 85).
