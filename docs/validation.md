# Local validation

**Recorded environment:** Docker Desktop on macOS with Linux ARM64 containers, **20 November 2026**. **AWS deployment is proposed.**

## Automated coverage

The runtime image uses a pinned Python base and locked Python dependencies. The local suite completed with **20 passing tests**.

| Area | Tests | Coverage |
|---|---:|---|
| [Service Desk API](../tests/test_api.py) | 5 | Health identity, synthetic ticket filtering, input validation, read-only behavior, and request metrics |
| [Recovery handler](../tests/test_recovery.py) | 10 | Authentication, target allowlisting, container identity, idempotency, overlap prevention, invalid batches, and failed health verification |
| [Measurements](../tests/test_measurement.py) | 5 | Nearest-rank percentiles, probe availability, raw timestamp windows, and missing telemetry |

## Configuration and integration checks

| Check | Recorded outcome |
|---|---|
| Compose configuration | Valid |
| Prometheus configuration and two alert rules | Valid |
| Alertmanager configuration and routing | Valid |
| API health and synthetic ticket endpoint | Successful responses |
| Prometheus targets | All three UP: self-monitoring, API metrics, and HTTP probe |
| Grafana provisioning | Dashboard `cloudguard-service-desk` present with six panels |
| Grafana connectivity | Healthy database and working Prometheus datasource |
| Recovery authentication | Unauthenticated internal webhook request rejected with HTTP 401 |
| Container access | No privileged containers; Unix Docker socket mounted only by recovery |
| Published interfaces | Four localhost bindings; no published recovery port |
| Controlled recovery | Three automatic successes; no manual cleanup contributed |
| Monitoring continuity | Monitoring samples remained UP and container identities/start times were retained during each trial |

The monitoring bridge supports localhost access. A separate internal control network carries recovery traffic. The live recovery identity check also matched the Compose labels of the intended Service Desk container.

## Validation workflow

Build and start the stack:

```bash
python3 scripts/bootstrap.py
python3 scripts/build_dashboard.py
docker compose config --quiet
docker compose build
docker compose up -d --no-build
```

Run the isolated test suite and native configuration validators:

```bash
docker run --rm --network none --read-only --tmpfs /tmp   cloudguard-runtime:local python -m unittest discover -s tests -v
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec -T alertmanager amtool check-config /etc/alertmanager/config.yml
```

Collect load and controlled recovery measurements:

```bash
python3 scripts/lab.py benchmark --duration 20 --concurrency 4
python3 scripts/lab.py recover --trials 3
```

The scripts establish a healthy baseline before load or a controlled stop. Raw Prometheus range-vector samples retain the scrape timestamps used to identify the first failed and first subsequent successful HTTP probe. A failed trial is reported explicitly; any manual start is cleanup and is excluded from the successful-trial mean.

## Evidence and verification limits

[Measured results](presentation-results.md) and the [machine-readable summary](measured-local.json) are tracked in Git. Raw requests, probe samples, logs, container snapshots, and checksums are retained locally under ignored `output/`. Integration responses are in `output/validation/`. Experiment records include configuration fingerprints and checksum manifests to identify the evidence collected for each run.

The measurements cover a short local load test and three controlled stops on one host. Other container platforms, host/daemon failure recovery, long-running SLA compliance, AWS EC2 deployment, and CloudWatch integration remain unverified. Screenshots are listed as pending in the [presentation checklist](presentation-results.md#presentation-capture-checklist).
