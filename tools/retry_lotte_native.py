"""Run one authorized retry per native author on the existing GPU NodePool."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
KUBE = ["kubectl", "--context", "mall-apne2-mgmt", "-n", "llm-bench"]
RESOURCE_NAMES = ["deployment/vllm-model-pages", "service/vllm-model-pages"]
PORT = 18003


def command(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def render(model, cfg, target):
    text = (ROOT / "deploy/vllm.yaml").read_text()
    values = {
        "MODEL": model["model_id"],
        "TP": str(model["tensor_parallel_size"]),
        "INSTANCE_TYPE": model["gpu_instance_type"],
        "EXTRA_VLLM_ARGS_YAML": "\n".join(
            "            - " + value for value in model.get("extra_vllm_args", [])
        ),
    }
    for key, value in values.items():
        text = text.replace("$" + key, value)
    text = (
        text.replace("name: vllm\n", "name: vllm-model-pages\n")
        .replace("app: vllm }", "app: vllm-model-pages }")
        .replace("vllm/vllm-openai:latest", cfg["scenario"]["finqa_audited"]["vllm_image"])
    )
    assert "--max-model-len=8192" in text and "enableServiceLinks: false" in text
    assert "key: gpu-bench" in text and "effect: NoSchedule" in text
    assert "node.kubernetes.io/instance-type: " + model["gpu_instance_type"] in text
    target.write_text(text)


def stop_forward(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def diagnose():
    snapshot = {"cache_kib": None, "cpu_percent": None}
    try:
        pods = command(
            KUBE + ["get", "pods", "-l", "app=vllm-model-pages", "-o", "json"],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print("STARTUP_DIAGNOSIS_UNAVAILABLE", flush=True)
        return snapshot
    for pod in json.loads(pods.stdout).get("items", []):
        if pod["metadata"].get("deletionTimestamp") or pod.get("status", {}).get("phase") != "Running":
            continue
        name = pod["metadata"]["name"]
        print("STARTUP_DIAGNOSIS", name, pod.get("status", {}).get("phase"), flush=True)
        for args in [
            ["du", "-sk", "/root/.cache/huggingface"],
            ["ps", "-eo", "pcpu,comm"],
        ]:
            try:
                result = subprocess.run(KUBE + ["exec", name, "--", *args],
                                        capture_output=True, text=True, timeout=20)
            except subprocess.TimeoutExpired:
                print("STARTUP_DIAGNOSIS_TIMEOUT", name, args[0], flush=True)
                continue
            print(result.stdout[-1800:] or result.stderr[-300:], flush=True)
            if result.returncode == 0 and args[0] == "du":
                snapshot["cache_kib"] = (snapshot["cache_kib"] or 0) + int(result.stdout.split()[0])
            if result.returncode == 0 and args[0] == "ps":
                snapshot["cpu_percent"] = snapshot["cpu_percent"] or 0.0
                for line in result.stdout.splitlines()[1:]:
                    fields = line.split()
                    if len(fields) >= 2 and fields[1] not in {"ps", "sh", "bash"}:
                        snapshot["cpu_percent"] += float(fields[0])
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--prompt-file")
    args = parser.parse_args()
    if not args.episode.replace("-", "").isalnum():
        parser.error("Unsafe episode")
    directory = ROOT / "validation/model-tasks" / args.episode
    plan = json.loads((directory / "plan.json").read_text())
    cfg = tomllib.loads((ROOT / "config.toml").read_text())
    configured = {model["name"]: model for model in cfg["models"]}
    selected = [row for row in plan["models"] if row["native"]]
    env = {**os.environ, "UV_CACHE_DIR": "/tmp/llm-benchmark-uv-cache"}
    feedback = json.loads((directory / "feedback.json").read_text())
    compact = {
        row["model"]: {
            "이전 검수 수정 사항": [
                {"severity": item["severity"], "action": item["action"][:260]}
                for item in feedback[row["model"]].get("이전 독립 검수 지적 원문", [])
            ],
            "필수 구현": [
                "배치·기준층 평면·입면·단면 도면 4종, 단위·개념 추정의 근거를 실제로 표시하세요.",
                "서로 다른 설계 단계별 3D와 전체 완성 타워를 구현하고, 도면 선택·단계와 연결하세요.",
                "초기 시점에 전체 형상이 보이며 회전·줌·초기화를 포인터와 키보드로 조작할 수 있어야 합니다.",
                "허용된 로컬 전역 THREE 런타임만 사용하세요. 글자·버튼은 19px 이상이며 휴대폰에서 접근 가능해야 합니다.",
                "표현은 스스로 결정하세요. 간결한 코드로 출력 한도 안에 완결된 HTML을 작성하세요.",
            ],
        } for row in selected
    }
    compact_path = directory / "native-feedback.json"
    compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n")
    receipts_path = directory / "native-runtime.json"
    receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else []
    forward = None
    try:
        for row in selected:
            model = configured[row["model"]]
            assert model.get("base_url") and model.get("enabled", True)
            assert model["model_id"] == row["model_id"]
            record_path = ROOT / "results/model-lotte-towers/lotte-tower-models-20261013" / row["model"] / "record.json"
            old = json.loads(record_path.read_text())
            if old.get("retry_episode") == args.episode:
                print("ALREADY_ATTEMPTED", row["model"], flush=True)
                continue
            manifest = directory / (row["model"] + "-runtime.yaml")
            render(model, cfg, manifest)
            began = time.monotonic()
            print("NATIVE_START", row["model"], model["gpu_instance_type"], flush=True)
            command(KUBE + ["apply", "-f", str(manifest)])
            last_diagnosis = began
            prior_snapshot = None
            stagnant = 0
            while True:
                if forward is None or forward.poll() is not None:
                    stop_forward(forward)
                    forward = subprocess.Popen(
                        KUBE + ["port-forward", "service/vllm-model-pages",
                                f"{PORT}:8000", "--address", "127.0.0.1"],
                        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                try:
                    with urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=5) as response:
                        ids = {item["id"] for item in json.load(response)["data"]}
                    if model["model_id"] in ids:
                        break
                except Exception:
                    pass
                elapsed = time.monotonic() - began
                print("NATIVE_LOADING", row["model"], int(elapsed), "seconds", flush=True)
                if time.monotonic() - last_diagnosis >= 600:
                    snapshot = diagnose()
                    stagnant = stagnant + 1 if (
                        prior_snapshot is not None
                        and snapshot["cache_kib"] is not None
                        and snapshot["cpu_percent"] is not None
                        and snapshot["cache_kib"] == prior_snapshot["cache_kib"]
                        and snapshot["cpu_percent"] == 0
                    ) else 0
                    prior_snapshot = snapshot
                    last_diagnosis = time.monotonic()
                if elapsed > 3600 and stagnant >= 2:
                    raise RuntimeError("Native startup made no cache/CPU progress across repeated diagnostics.")
                time.sleep(30)
            ready = time.monotonic()
            print("NATIVE_IDENTITY_VERIFIED", row["model"], model["model_id"], flush=True)
            output_cap = row["output_cap"]
            generation_args = ["--feedback", str(compact_path), "--fresh-repair"]
            if args.prompt_file:
                text = Path(args.prompt_file).read_text().replace("{name}", row["model"]).replace("{model_id}", model["model_id"])
                payload = {
                    "model": model["model_id"], "messages": [{"role": "user", "content": text}],
                    "add_generation_prompt": True,
                    "chat_template_kwargs": model.get("chat_template_kwargs", {}),
                }
                request = Request(
                    f"http://127.0.0.1:{PORT}/tokenize",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=30) as response:
                    count = json.load(response)["count"]
                output_cap = min(output_cap, 8192 - count - 64)
                assert output_cap >= 4096, "Compact prompt still leaves insufficient output room"
                budget = {"model": row["model"], "input_tokens": count,
                          "context_tokens": 8192, "output_cap": output_cap, "safety_tokens": 64}
                (directory / "native-token-budget.json").write_text(json.dumps(budget, indent=2) + "\n")
                print("MEASURED_NATIVE_BUDGET", json.dumps(budget), flush=True)
                generation_args = ["--prompt-file", args.prompt_file]
            command(
                ["uv", "run", "--no-sync", "python3", "tools/generate_lotte_towers.py",
                 "--models", row["model"], "--max-output-tokens", str(output_cap),
                 "--native-port", str(PORT), *generation_args,
                 "--repair-language", "ko", "--retry-episode", args.episode], env=env,
            )
            receipts.append({"model": row["model"], "startup_seconds": ready - began,
                             "active_seconds": time.monotonic() - began})
            (directory / "native-runtime.json").write_text(json.dumps(receipts, indent=2) + "\n")
            stop_forward(forward)
            forward = None
            command(KUBE + ["delete", *RESOURCE_NAMES, "--ignore-not-found"])
    finally:
        stop_forward(forward)
        subprocess.run(KUBE + ["delete", *RESOURCE_NAMES, "--ignore-not-found"], cwd=ROOT, check=False)
        print("TASK_NATIVE_RUNTIME_REMOVED", flush=True)


if __name__ == "__main__":
    main()
