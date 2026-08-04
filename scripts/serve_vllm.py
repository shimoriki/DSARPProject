"""HPC — launch a vLLM OpenAI-compatible server (thin wrapper).

Not executed on the laptop profile. Requires vLLM installed on the cluster.
"""
import argparse
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen2.5-Coder-32B-Instruct")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--tensor-parallel-size", type=int, default=2)
    args = ap.parse_args()
    cmd = [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
           "--model", args.model, "--port", str(args.port),
           "--tensor-parallel-size", str(args.tensor_parallel_size)]
    print("[vllm]", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print("[vllm] vLLM not installed on this node.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
