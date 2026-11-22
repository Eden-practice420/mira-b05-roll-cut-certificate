"""Run the scientific programs in a temporary workspace and print the measured evidence."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(directory, script, *args):
    print("RUN  " + " ".join([script, *args]), flush=True)
    completed = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", script, *args],
        cwd=directory, check=True, capture_output=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return completed.stdout

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def main():
    with tempfile.TemporaryDirectory(prefix="mira-replay-") as scratch:
        work = Path(scratch) / "附件"
        shutil.copytree(ROOT / "附件", work)
        review = work / "复核实验"
        base = json.loads(run(work, "run.py"))
        for example in base["runs"][:2]:
            print(f"刀缝 {example['kerf']} mm | 最优 {len(example['optimum'])} 卷")
            print("配料 |", " / ".join("+".join(map(str, roll)) for roll in example["optimum"]))
        run(work, "robust_audit.py", "--audit", "audit.json", "--certs", "certs.json")
        audit = read(work / "audit.json")
        s = audit["summary"]["all"]
        print(f"独立求解一致 | {s['exact_matches']}/{s['n']} 单")
        print(f"只查端点低估 {s['endpoints_understate']} 单 | 忽略尾刀不安全 {s['tail_ignored_unsafe']} 单")
        print("被拒篡改证书 |", len(audit["tamper_checks"]))


if __name__ == "__main__":
    main()
