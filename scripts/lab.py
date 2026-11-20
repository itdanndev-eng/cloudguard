#!/usr/bin/env python3
"""CloudGuard load and recovery experiments; all raw evidence stays in output/."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:18000"
PROM = "http://127.0.0.1:19090"
AM = "http://127.0.0.1:19093"
PROBE = 'probe_success{job="servicedesk-http"}'


def utc(stamp=None):
    return datetime.fromtimestamp(time.time() if stamp is None else stamp, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def command(*args, check=True):
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=30)
    if check and result.returncode:
        raise RuntimeError(result.stdout)
    return result


def get(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def query(expression, at=None):
    payload = get(PROM + "/api/v1/query?" + urlencode({"query": expression, "time": time.time() if at is None else at}))
    if payload.get("status") != "success":
        raise RuntimeError(str(payload))
    return payload


def window(expression, start, finish):
    payload = query(expression + "[" + str(math.ceil(finish - start) + 10) + "s]", finish)
    rows = payload["data"]["result"]
    if len(rows) != 1:
        raise RuntimeError("Expected one independent HTTP probe series: " + expression)
    values = [point for point in rows[0]["values"] if start <= float(point[0]) <= finish]
    return payload, values


def probe_availability(points):
    passed = sum(value == "1" for _, value in points)
    return {"successful_probes": passed, "total_observed_probes": len(points),
            "availability_percent": 100 * passed / len(points) if points else None,
            "definition": "successful independent HTTP probes / observed probes in the stated UTC window",
            "limitation": "Short local observation; missing telemetry is not a success or proof of production SLA."}


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def evidence_folder(kind):
    path = ROOT / "output" / (kind + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    path.mkdir(parents=True)
    files = list((ROOT / "cloudguard").glob("*.py")) + list((ROOT / "config").rglob("*"))
    write(path / "source-sha256.json", {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in files if p.is_file()})
    (path / "compose.yaml").write_bytes((ROOT / "compose.yaml").read_bytes())
    return path


def snapshot():
    ids = command("docker", "compose", "ps", "-a", "-q").stdout.split()
    return json.loads(command("docker", "inspect", *ids).stdout)


def recovery_events():
    code = "from pathlib import Path; p=Path('/var/lib/cloudguard/events.jsonl'); print(p.read_text() if p.exists() else '')"
    raw = command("docker", "compose", "exec", "-T", "recovery", "python", "-c", code).stdout
    return raw, [json.loads(line) for line in raw.splitlines() if line]


def healthy_baseline(timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            health = get(API + "/health")
            rules = get(PROM + "/api/v1/rules?type=alert")
            rule = next(r for g in rules["data"]["groups"] for r in g["rules"] if r["name"] == "ServiceDeskUnavailable")
            targets = get(PROM + "/api/v1/targets?state=active")
            _, points = window(PROBE, time.time() - 18, time.time())
            active = get(AM + "/api/v2/alerts")
            if (health.get("status") == "ok" and health.get("service") == "cloudguard-servicedesk"
                    and rule["state"] == "inactive" and not any(a["labels"].get("alertname") == "ServiceDeskUnavailable" for a in active)
                    and len(points) >= 3 and all(p[1] == "1" for p in points[-3:])
                    and len(targets["data"]["activeTargets"]) == 3
                    and all(t["health"] == "up" for t in targets["data"]["activeTargets"])):
                return targets
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(2)
    raise RuntimeError("A healthy baseline was not established; no controlled stop was issued.")


def benchmark(args):
    baseline = healthy_baseline()
    output = evidence_folder("benchmark")
    write(output / "targets-before.json", baseline)
    endpoint = API + "/api/tickets?status=open&limit=20"
    parsed = urlsplit(endpoint)
    route = parsed.path + "?" + parsed.query
    start_wall, start_clock = time.time(), time.perf_counter()
    deadline = start_clock + args.duration

    def worker(number):
        rows = []
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
        while time.perf_counter() < deadline:
            clock, stamp = time.perf_counter(), time.time()
            status, error = None, None
            try:
                connection.request("GET", route, headers={"User-Agent": "CloudGuard-course-load/1", "Connection": "keep-alive"})
                response = connection.getresponse()
                status = response.status
                payload = json.loads(response.read())
                if status != 200 or payload.get("data_source") != "synthetic-demo" or payload.get("total") != 4:
                    error = "Unexpected HTTP status or synthetic data response"
            except Exception as exc:
                error = type(exc).__name__ + ": " + str(exc)
                connection.close()
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
            rows.append({"started_at_utc": utc(stamp), "worker": number, "status": status,
                         "latency_ms": (time.perf_counter() - clock) * 1000, "error": error})
        connection.close()
        return rows

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = [row for group in pool.map(worker, range(args.concurrency)) for row in group]
    finish_wall, elapsed = time.time(), time.perf_counter() - start_clock
    with (output / "requests.jsonl").open("w") as handle:
        for row in sorted(rows, key=lambda r: r["started_at_utc"]):
            handle.write(json.dumps(row) + "\n")
    time.sleep(6)  # Allow the last independent scrape in the benchmark window to commit.
    raw, points = window(PROBE, start_wall, finish_wall)
    write(output / "probe-samples.json", raw)
    latencies = [row["latency_ms"] for row in rows]
    result = {"endpoint": endpoint, "method": "GET", "data": "Synthetic read-only IT service tickets",
              "workload": "Closed-loop HTTP/1.1 keep-alive, no think time", "concurrency": args.concurrency,
              "requested_duration_seconds": args.duration, "measured_duration_seconds": elapsed,
              "started_at_utc": utc(start_wall), "finished_at_utc": utc(finish_wall),
              "requests": len(rows), "errors": sum(row["error"] is not None for row in rows),
              "throughput_requests_per_second": len(rows) / elapsed,
              "latency_ms": {"average": statistics.fmean(latencies),
                             "p95": percentile(latencies, .95), "p99": percentile(latencies, .99)},
              "latency_definition": "Client round-trip over all attempts; nearest-rank percentiles",
              "probe_availability": probe_availability(points), "environment": "Local Docker Desktop; AWS proposed only"}
    write(output / "summary.json", result)
    write(output / "containers.json", snapshot())
    logs = command("docker", "compose", "logs", "--no-color", "--since", utc(start_wall), "servicedesk").stdout
    (output / "application.log").write_text(logs)
    print(json.dumps({"output": str(output), **result}, indent=2), flush=True)
    return result, output


def trial(number, timeout):
    baseline = healthy_baseline()
    output = evidence_folder("recovery-" + str(number))
    write(output / "targets-before.json", baseline)
    before = snapshot()
    write(output / "containers-before.json", before)
    result = {"trial": number, "outcome": "failed", "manual_cleanup": False, "aws_status": "proposed only"}
    marker = None
    try:
        marker = time.time()
        write(output / "stop-marker.json", {"utc_immediately_before_stop": utc(marker),
              "unix_seconds": marker, "command": ["docker", "stop", "cloudguard-servicedesk"]})
        print(json.dumps({"trial": number, "stop_marker_utc": utc(marker)}), flush=True)
        stopped = command("docker", "stop", "cloudguard-servicedesk")
        (output / "stop-command.txt").write_text(stopped.stdout)
        deadline = time.monotonic() + timeout
        down = up = None
        while time.monotonic() < deadline:
            raw, points = window(PROBE, marker - 15, time.time())
            write(output / "probe-samples.json", raw)
            during = [p for p in points if p[0] >= marker]
            down = next((p for p in during if p[1] == "0"), None)
            up = next((p for p in during if down and p[0] > down[0] and p[1] == "1"), None)
            if down and not (output / "first-failure.json").exists():
                write(output / "first-failure.json", raw)
                write(output / "containers-during-outage.json", snapshot())
                print(json.dumps({"trial": number, "first_failed_probe_utc": utc(down[0])}), flush=True)
            if up:
                journal_raw, events = recovery_events()
                (output / "recovery-events.jsonl").write_text(journal_raw)
                new = [e for e in events if e["at_utc"] >= utc(marker)]
                finish = next((e for e in new if e["event"] == "remediation_finish" and e.get("outcome") == "success"), None)
                if finish:
                    incident = finish["incident"]
                    received = next(e for e in new if e["event"] == "alert_received" and e.get("incident") == incident)
                    action = next(e for e in new if e["event"] == "remediation_start" and e.get("incident") == incident)
                    result.update(outcome="automatic_recovery_verified", stop_marker_utc=utc(marker),
                        first_failed_probe_utc=utc(down[0]), first_successful_probe_utc=utc(up[0]),
                        alert_received_utc=received["at_utc"], remediation_started_utc=action["at_utc"],
                        remediation_finished_utc=finish["at_utc"],
                        stop_to_failed_probe_seconds=down[0] - marker,
                        scrape_observed_ttr_seconds=up[0] - down[0],
                        remediation_execution_seconds=finish["duration_seconds"])
                    break
            time.sleep(1)
        else:
            result["error"] = "Automatic HTTP recovery and a successful remediation record were not verified before timeout."
        finish_wall = time.time()
        raw, points = window(PROBE, marker - 15, finish_wall)
        write(output / "probe-samples-final.json", raw)
        result["observation_start_utc"], result["observation_finish_utc"] = utc(marker - 15), utc(finish_wall)
        result["probe_availability"] = probe_availability(points)
        monitor_raw = query('up{job=~"prometheus|servicedesk-http"}[' + str(math.ceil(finish_wall-marker)+20) + 's]', finish_wall)
        write(output / "monitoring-up-samples.json", monitor_raw)
        monitor_rows = monitor_raw["data"]["result"]
        result["monitoring_samples_all_up"] = (
            {r["metric"]["job"] for r in monitor_rows} == {"prometheus", "servicedesk-http"}
            and all(any(ts >= marker for ts, _ in row["values"]) for row in monitor_rows)
            and all(value == "1" for row in monitor_rows for ts, value in row["values"] if ts >= marker))
        if not result["monitoring_samples_all_up"]:
            result["outcome"] = "failed"
            result["error"] = "Independent monitoring availability was not verified from its samples."
    except (Exception, KeyboardInterrupt) as exc:
        result["error"] = str(exc) or "Interrupted"
    finally:
        current = json.loads(command("docker", "inspect", "cloudguard-servicedesk").stdout)[0]
        if not current["State"]["Running"]:
            # This is cleanup after a FAILED trial, never a successful automatic recovery.
            result["outcome"] = "failed"
            result["manual_cleanup"] = True
            command("docker", "start", "cloudguard-servicedesk")
        if marker:
            raw_journal, _ = recovery_events()
            (output / "recovery-events.jsonl").write_text(raw_journal)
            logs = command("docker", "compose", "logs", "--no-color", "--since", utc(marker),
                           "servicedesk", "recovery", "prometheus", "alertmanager", "probe").stdout
            (output / "services.log").write_text(logs)
            events = command("docker", "events", "--since", str(int(marker) - 1), "--until", str(int(time.time()) + 1),
                             "--filter", "container=cloudguard-servicedesk", "--format", "{{json .}}").stdout
            (output / "docker-events.jsonl").write_text(events)
        after = snapshot()
        write(output / "containers-after.json", after)
        retained = {r["Name"]: (r["Id"], r["State"]["StartedAt"]) for r in before
                    if r["Config"]["Labels"].get("com.docker.compose.service") != "servicedesk"}
        result["monitoring_containers_retained"] = all(retained.get(r["Name"]) == (r["Id"], r["State"]["StartedAt"])
            and r["State"]["Running"] for r in after if r["Name"] in retained)
        if result["outcome"] == "automatic_recovery_verified" and not result["monitoring_containers_retained"]:
            result["outcome"] = "failed"
            result["error"] = "A monitoring/recovery container was restarted during the experiment."
        result["output"] = str(output.relative_to(ROOT))
        write(output / "summary.json", result)
        print(json.dumps(result, indent=2), flush=True)
    return result, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    bench = sub.add_parser("benchmark")
    bench.add_argument("--duration", type=float, default=20)
    bench.add_argument("--concurrency", type=int, default=4)
    recover = sub.add_parser("recover")
    recover.add_argument("--trials", type=int, choices=(1, 2, 3), default=3)
    recover.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if args.mode == "benchmark":
        if args.duration < 5 or not 1 <= args.concurrency <= 16:
            parser.error("Use duration >= 5 seconds and concurrency 1–16.")
        benchmark(args)
    else:
        results = []
        for number in range(1, args.trials + 1):
            result, _ = trial(number, args.timeout)
            results.append(result)
            if result["outcome"] != "automatic_recovery_verified":
                break
        successful = [r["scrape_observed_ttr_seconds"] for r in results if r["outcome"] == "automatic_recovery_verified"]
        aggregate = {"attempted": len(results), "successful": len(successful),
                     "failed_trials": [r["trial"] for r in results if r["outcome"] != "automatic_recovery_verified"],
                     "mean_scrape_observed_ttr_seconds": statistics.fmean(successful) if successful else None,
                     "trials": results, "environment": "Local Docker Desktop; AWS proposed only"}
        path = evidence_folder("recovery-series")
        write(path / "summary.json", aggregate)
        print(json.dumps({"series_output": str(path), **aggregate}, indent=2), flush=True)
        return 0 if len(successful) == args.trials else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
