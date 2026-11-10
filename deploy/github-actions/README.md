# GitHub Actions AWS access

`bedrock-model-watch.yml` and `model-benchmark.yml` assume the IAM role
`arn:aws:iam::180294183052:role/llm-benchmark-gha` through GitHub OIDC
(repository variable `AWS_ROLE_ARN`). Created 2026-11-10 with:

- trust: [trust-policy.json](trust-policy.json) — this repository's branch
  refs only (`repo:inferplane/llm-benchmark:ref:refs/heads/*`); pull requests
  from forks cannot assume it.
- inline policy `bedrock-benchmark`: [permissions-policy.json](permissions-policy.json)
  — Bedrock/Mantle inference and read-only model/pricing/quota discovery.
  No networking, storage or IAM permissions.
- `MaxSessionDuration` 43200 s, so a single benchmark job (≤ 6 h on
  GitHub-hosted runners) never outlives its credentials.

One-time repository settings the workflows need:

```bash
gh variable set AWS_ROLE_ARN -R inferplane/llm-benchmark --body arn:aws:iam::180294183052:role/llm-benchmark-gha
# Let workflows open pull requests (default token permission stays read).
gh api -X PUT repos/inferplane/llm-benchmark/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
```
