# CloudGuard — presentation results

**Verified local implementation. AWS deployment is proposed only.**

GitHub repository: [itdanndev-eng/cloudguard](https://github.com/itdanndev-eng/cloudguard) (private), branch `main`.

## Slide-ready project statement

CloudGuard demonstrates reliability engineering for a small IT Service Desk. An original read-only API serves explicitly synthetic incident tickets. Independent HTTP probes detect an outage; Prometheus and Alertmanager route it to an authenticated internal handler, which starts only the allowlisted demo container and verifies HTTP health.

## Verified implementation

- Original application, configuration, recovery handler, dashboard, tests, and measurement tools.
- 20 automated tests pass. Compose, Prometheus, and Alertmanager configuration validation passes.
- Dashboard provisioning and Prometheus datasource connectivity verified through authenticated Grafana APIs.
- Internal recovery rejects unauthenticated requests; no published recovery port or TCP Docker socket.

## Measured local HTTP load test

- Endpoint: http://127.0.0.1:18000/api/tickets?status=open&limit=20 (synthetic open tickets).
- Workload: 4 closed-loop HTTP/1.1 keep-alive workers, no think time.
- UTC window: 2026-11-20T09:21:21.237588Z to 2026-11-20T09:21:41.267885Z.
- Measured duration: **20.031 seconds**.
- Requests: **25,641**. Errors: **0**.
- Throughput: **1280.08 requests/second**.
- Client latency: average **3.123 ms**, p95 **3.575 ms**, p99 **44.010 ms** (nearest-rank percentiles).
- Independent availability probes: **4/4 successful**, **100.0%** in this short window.

The client ran on the Mac host; the API had a 0.75-CPU container limit. These results are a short local workload measurement, not production capacity, monthly SLA compliance, or an AWS benchmark.

## Controlled recovery results

| Trial | Pre-stop → failed probe | Failed → successful probe (TTR) | Remediation execution | Result |
|---|---:|---:|---:|---|
| 1 | 4.491 s | 19.999 s | 0.803 s | Automatic success |
| 2 | 4.032 s | 19.994 s | 0.900 s | Automatic success |
| 3 | 4.162 s | 20.004 s | 0.838 s | Automatic success |

**Successful trials: 3/3. Failed trials: none. Mean scrape-observed TTR: 19.999 seconds.**

No manual restart/cleanup contributed to these successes. Monitoring containers retained their identities/start times and monitoring samples remained UP during each workload outage. All UTC timestamps—pre-stop marker, failed probe, alert receipt, remediation start/finish, successful probe—are in the raw evidence.

Each deliberate recovery observation window contains 4 successful probes out of 8 (50%). These windows intentionally include an outage; they do not establish production SLA compliance.

## Proposed objectives and limitations

- Proposed availability objective: 99.9% successful monthly HTTP probes, not a demonstrated contractual SLA.
- Proposed controlled-stop TTR objective: at most 45 seconds; all three local trials meet this limited scenario.
- Proposed p95 objective: below 250 ms for the stated light workload; the local short-run result meets it.
- Single host and workload; host/daemon failures, deleted containers, and running-unhealthy processes are outside this recovery action.
- Five-second probe sampling limits transition precision. Three trials do not establish a robust tail distribution.
- EC2, EBS, VPC/security groups, and CloudWatch are proposed only. No AWS resources were created.

## Raw evidence locations

- Benchmark: output/benchmark-20261120T092121231834Z/
- Series: output/recovery-series-20261120T092425185747Z/
- Trial 1: output/recovery-1-20261120T092247818387Z/
- Trial 2: output/recovery-2-20261120T092323263396Z/
- Trial 3: output/recovery-3-20261120T092358253468Z/

- API/dashboard/exposure verification: output/validation/
- Raw output/ is ignored by Git. The tracked aggregate is docs/measured-local.json.

## Screenshot checklist for the faculty PPT

No screenshots are presented as collected in this run. Capture new images from this implementation:

- [ ] API response showing synthetic-demo and filtered ticket records.
- [ ] Healthy Prometheus targets and successful independent HTTP probes.
- [ ] Provisioned Grafana dashboard showing availability, latency, and request rate.
- [ ] During a new controlled trial, failed HTTP probes and ServiceDeskUnavailable firing.
- [ ] Alertmanager routing and structured recovery events for that same trial.
- [ ] Recovered probe plus the actual UTC timing table.
- [ ] Confirmed GitHub repository/commit after publication.

Keep genuine captures under ignored output/. Never reuse earlier implementation screenshots or label a local image as an AWS deployment.
