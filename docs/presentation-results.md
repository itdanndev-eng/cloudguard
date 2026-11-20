# CloudGuard: demo and measured results

**Environment:** Docker Desktop, Linux ARM64 containers. Measurements recorded on **20 November 2026**. **AWS deployment is proposed.**

Repository: [itdanndev-eng/cloudguard](https://github.com/itdanndev-eng/cloudguard), branch `main`.

## Project overview

CloudGuard demonstrates availability monitoring and automated recovery for a small IT Service Desk. A read-only API serves synthetic incident tickets. Independent HTTP probes detect an outage, Prometheus and Alertmanager route it to an authenticated internal handler, and the handler starts only the allowlisted demo container before verifying HTTP health.

The local validation includes 20 passing tests, validated monitoring configuration, a provisioned Grafana dashboard, and a recovery endpoint reachable only within the stack. See [validation details](validation.md).

## HTTP load test

| Parameter | Recorded value |
|---|---|
| Endpoint | `http://127.0.0.1:18000/api/tickets?status=open&limit=20` |
| Data | Synthetic open service tickets |
| Workload | 4 closed-loop HTTP/1.1 keep-alive workers, no think time |
| UTC start | `2026-11-20T09:21:21.237588Z` |
| UTC finish | `2026-11-20T09:21:41.267885Z` |
| Measured duration | 20.031 s |
| Completed requests / errors | 25,641 / 0 |
| Throughput | 1,280.08 requests/s |
| Average client latency | 3.123 ms |
| p95 / p99 client latency | 3.575 ms / 44.010 ms |
| Successful availability probes | 4/4 (100% of observed probes) |

The load client ran on the Mac host, with a 0.75-CPU limit on the API container. Latency measures client round trips; percentiles use nearest rank over all attempts. This short workload does not establish production capacity, monthly SLA compliance, or AWS performance.

## Controlled recovery trials

| Trial | Pre-stop marker to failed probe | Failed to successful probe (TTR) | Remediation execution | Result |
|---|---:|---:|---:|---|
| 1 | 4.491 s | 19.999 s | 0.803 s | Automatic success |
| 2 | 4.032 s | 19.994 s | 0.900 s | Automatic success |
| 3 | 4.162 s | 20.004 s | 0.838 s | Automatic success |

**Automatic successes: 3/3. Failed trials: 0. Mean scrape-observed TTR: 19.999 s.**

Each trial began from a verified healthy baseline. No manual restart or cleanup contributed to a success. Monitoring containers retained their identities and start times, and independent monitoring samples remained UP while the workload was stopped.

The [measurement summary](measured-local.json) records the UTC pre-stop marker, first failed probe, alert receipt, remediation start and finish, and first successful probe for each trial.

### Measurement definitions

| Measurement | Definition |
|---|---|
| Detection interval | UTC marker immediately before `docker stop` to first failed HTTP probe sample |
| Scrape-observed TTR | First failed HTTP probe sample to first subsequent successful sample |
| Remediation execution | Handler's remediation start to verified HTTP health |
| Observed availability | Successful independent HTTP probe samples divided by all observed probe samples within the stated window |

Probe sampling occurs every five seconds. Outage boundaries between samples remain uncertain; missing telemetry is not a successful probe.

### Recovery observation windows

All times below are **UTC on 20 November 2026**. Each window includes the deliberate outage.

| Trial | Window start | Window finish | Successful / observed probes |
|---|---|---|---|
| 1 | 09:22:33.111655 | 09:23:13.744742 | 4/8 (50%) |
| 2 | 09:23:08.571304 | 09:23:49.893092 | 4/8 (50%) |
| 3 | 09:23:43.435242 | 09:24:23.556598 | 4/8 (50%) |

These are controlled failure windows, not representative production availability measurements.

## Proposed service objectives

| Objective | Proposed target | Local evidence |
|---|---|---|
| Monthly availability | 99.9% successful HTTP probes | Monthly compliance unmeasured; 4/4 successful probes during the benchmark |
| Controlled-stop TTR | At most 45 s | All three local trials met this scenario's target |
| Client p95 latency | Below 250 ms under the stated light workload | 3.575 ms in the short local test |

The demo covers a single stopped container on one healthy Docker host. Host/daemon failures, deleted containers, and running-unhealthy processes are outside this action's scope. Three trials do not establish a recovery tail distribution. EC2 deployment and CloudWatch integration remain proposed.

## Evidence

The public repository contains the [aggregate results and trial timestamps](measured-local.json). Raw experiment files are retained locally under ignored `output/`; they are not included in the repository. Run the [experiment commands](../README.md#run-the-experiments) to collect a new evidence set.

| Evidence | Local directory |
|---|---|
| Benchmark | `output/benchmark-20261120T092121231834Z/` |
| Recovery series | `output/recovery-series-20261120T092425185747Z/` |
| Trial 1 | `output/recovery-1-20261120T092247818387Z/` |
| Trial 2 | `output/recovery-2-20261120T092323263396Z/` |
| Trial 3 | `output/recovery-3-20261120T092358253468Z/` |
| Initial API/dashboard/exposure checks | `output/validation/` |

Raw packets contain request records, timestamped probe samples, structured recovery events, Docker events, service logs, container snapshots, configuration fingerprints, and checksum manifests as applicable to each experiment.

## Presentation capture checklist

Screenshots have not been collected for this evidence set. Capture the following from a matching demo run:

- [ ] API response showing the `synthetic-demo` label and filtered tickets.
- [ ] Healthy Prometheus targets and successful HTTP probes.
- [ ] Grafana availability, latency, and request-rate panels.
- [ ] A controlled outage with failed probes and `ServiceDeskUnavailable` firing.
- [ ] Alertmanager routing and recovery events for the same trial.
- [ ] Recovered probes and the corresponding UTC timing table.
- [ ] GitHub source and the commit used for that demo.

Store captures under ignored `output/`, keep credentials out of view, and label the deployment environment accurately.
