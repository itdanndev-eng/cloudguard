#!/usr/bin/env python3
"""Check tracked and staged source for accidental secrets and raw evidence."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def names(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).splitlines()


def main():
    tracked = set(names("ls-files"))
    staged = set(names("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
    paths = sorted(tracked | staged)
    if not paths:
        raise SystemExit("Stage the intended source before running this check.")
    patterns = [rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", rb"\bAKIA[0-9A-Z]{16}\b",
                rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b", rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"]
    secrets = [p.read_bytes().strip() for p in (ROOT / "secrets").glob("*") if p.is_file()]
    problems = []
    for name in paths:
        path = Path(name)
        if (path.parts[0] in ("output", "secrets", ".venv", ".git") or
            (path.name.startswith(".env") and path.name != ".env.example") or
            path.suffix.lower() in (".pem", ".key", ".log", ".jsonl", ".pyc")):
            problems.append(name + ": prohibited source/evidence path")
        data = (ROOT / name).read_bytes()
        staged_data = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT) if name in staged else data
        for content in (data, staged_data):
            if any(re.search(pattern, content) for pattern in patterns):
                problems.append(name + ": credential/private-key pattern")
            if any(value and value in content for value in secrets):
                problems.append(name + ": contains a generated runtime secret")
    if problems:
        raise SystemExit("\n".join(sorted(set(problems))))
    print(f"Checked {len(paths)} tracked/staged files: no prohibited paths, known runtime secrets, token patterns, or private keys.")
    print("This scoped scan complements manual diff review; it cannot recognize every possible secret format.")


if __name__ == "__main__":
    main()
