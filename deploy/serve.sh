#!/usr/bin/env bash
# Deploy one vLLM model to the gpu-bench NodePool on the shared mall-apne2-mgmt
# EKS cluster (ap-northeast-2), wait for it to become ready, then port-forward
# it to localhost:8000 for bench/run.py.
#
# Usage: deploy/serve.sh <model-short-name> [tensor-parallel-size] [instance-type]
#   deploy/serve.sh llama-3.1-8b              # model_id/TP/instance type all read from config.toml
#   deploy/serve.sh qwen3.6-27b 1 g7e.4xlarge  # override TP and/or instance type
#   deploy/serve.sh some-other/hf-model-id 2 g7e.4xlarge   # raw HF id: instance type required (3rd arg)
#
# First run needs HF_TOKEN exported (creates the k8s secret once); the model
# must have its gated-repo terms accepted on huggingface.co under that token.
#
# This is a SHARED cluster with other live tenants — every kubectl call below
# hardcodes --context mall-apne2-mgmt rather than trusting the ambient
# current-context, which another session has changed before (see
# ../aws-ec2-benchmark/CLAUDE.md's documented incident). Don't remove this.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

CTX=mall-apne2-mgmt
NS=llm-bench
kubectl() { command kubectl --context "$CTX" -n "$NS" "$@"; }

MODEL_ARG="${1:?usage: deploy/serve.sh <model> [tensor-parallel-size] [instance-type]}"

# config.toml is the single source of truth for model_id/TP/instance type (see
# CLAUDE.md) — look them up by name rather than duplicating them in a second
# case statement here, which would silently drift out of sync.
CONFIG_LOOKUP="$(uv run python3 -c "
import tomllib
cfg = tomllib.load(open('config.toml', 'rb'))
m = next((m for m in cfg['models'] if m['name'] == '$MODEL_ARG'), None)
if m:
    print(f'MODEL_ID={m[\"model_id\"]}')
    print(f'CFG_TP={m.get(\"tensor_parallel_size\", 1)}')
    print(f'CFG_INSTANCE={m.get(\"gpu_instance_type\", \"\")}')
    extra = m.get('extra_vllm_args', [])
    lines = chr(10).join(f'            - {a}' for a in extra)
    print(\"CFG_EXTRA_ARGS='\" + lines.replace(\"'\", \"'\\\\''\") + \"'\")
")"

if [ -n "$CONFIG_LOOKUP" ]; then
  eval "$CONFIG_LOOKUP"
  MODEL="$MODEL_ID"
  TP="${2:-$CFG_TP}"
  INSTANCE_TYPE="${3:-$CFG_INSTANCE}"
  EXTRA_VLLM_ARGS_YAML="${CFG_EXTRA_ARGS:-}"
else
  MODEL="$MODEL_ARG"
  TP="${2:-1}"
  INSTANCE_TYPE="${3:?raw HF model id $MODEL_ARG is not in config.toml -- pass the GPU instance type as a 3rd argument, e.g. g7e.4xlarge}"
  EXTRA_VLLM_ARGS_YAML=""
fi

# Required, not defaulted: Kubernetes' nvidia.com/gpu resource is a bare GPU
# *count*, so a request for "1 GPU" is satisfied equally by a 22GB g6.4xlarge
# or a 96GB g7e.4xlarge — Karpenter will silently pick the cheaper (too-small)
# one unless the exact instance type is pinned in the pod's nodeSelector. This
# OOM'd a 27B model onto a 22GB GPU on the first deploy; see deploy/vllm.yaml.
if [ -z "$INSTANCE_TYPE" ]; then
  echo "ERROR: no gpu_instance_type for '$MODEL_ARG' in config.toml, and none passed as a 3rd argument." >&2
  exit 1
fi

export MODEL TP INSTANCE_TYPE EXTRA_VLLM_ARGS_YAML
echo "serving $MODEL (tensor-parallel-size=$TP, instance-type=$INSTANCE_TYPE) on $CTX/$NS"

command kubectl --context "$CTX" get namespace "$NS" >/dev/null 2>&1 || \
  command kubectl --context "$CTX" create namespace "$NS"

# Idempotent: (re)creates the gpu-bench NodePool/EC2NodeClass if missing, e.g.
# after another team's cleanup pass. Safe to run every time.
command kubectl --context "$CTX" apply -f deploy/karpenter-gpu.yaml

# No nvidia-device-plugin runs on this cluster yet (verified against the live
# cluster — see CLAUDE.md) — install one scoped to gpu-bench nodes only, so it
# doesn't touch other teams' nodes.
command kubectl --context "$CTX" -n kube-system apply -f - <<'YAML'
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-gpu-bench
  namespace: kube-system
spec:
  selector: { matchLabels: { name: nvidia-device-plugin-gpu-bench } }
  template:
    metadata:
      labels: { name: nvidia-device-plugin-gpu-bench }
    spec:
      nodeSelector: { node-pool: gpu-bench }
      tolerations:
        - key: gpu-bench
          operator: Equal
          value: "true"
          effect: NoSchedule
      priorityClassName: system-node-critical
      containers:
        - name: nvidia-device-plugin-ctr
          image: nvcr.io/nvidia/k8s-device-plugin:v0.16.2
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            - name: device-plugin
              mountPath: /var/lib/kubelet/device-plugins
      volumes:
        - name: device-plugin
          hostPath: { path: /var/lib/kubelet/device-plugins }
YAML

if ! kubectl get secret hf-token >/dev/null 2>&1; then
  : "${HF_TOKEN:?export HF_TOKEN before first run — needed to create the hf-token k8s secret}"
  kubectl create secret generic hf-token --from-literal=token="$HF_TOKEN"
fi

envsubst < deploy/vllm.yaml | kubectl apply -f -
echo "waiting for rollout (model download + load can take several minutes for 30B+)..."
kubectl rollout status deployment/vllm --timeout=20m

echo "ready — port-forwarding localhost:8000 (Ctrl-C to stop, then run the next model)"
echo "(the gpu-bench node auto-terminates ~60s after you delete the deployment — see deploy/karpenter-gpu.yaml)"
kubectl port-forward svc/vllm 8000:8000
