# Verified local validation

**Environment: Docker Desktop on this Mac, Linux ARM64 containers. AWS deployment is proposed only.**

The runtime image was built locally from the pinned Python base and locked requirements. Native Compose validation passed. The final automated suite has 20 passing tests: API behavior, authentication, allowlisting, identity checks, overlap prevention, idempotency, HTTP verification failure, and measurement math. Development testing identified and corrected duplicate Flask health-route registration before measurement.

Commands actually executed:

    python3 scripts/bootstrap.py
    python3 scripts/build_dashboard.py
    docker compose config --quiet
    docker compose build
    docker run --rm --network none --read-only --tmpfs /tmp cloudguard-runtime:local python -m unittest discover -s tests -v
    docker compose up -d --no-build
    docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
    docker compose exec -T alertmanager amtool check-config /etc/alertmanager/config.yml
    python3 scripts/lab.py benchmark --duration 20 --concurrency 4
    python3 scripts/lab.py recover --trials 3

The initial all-internal network configuration did not publish host ports on Docker Desktop. Before measurement, monitoring was moved to a standard bridge with four explicit localhost binds. Recovery stays on a separate internal control network. Only the new stack's containers/networks were recreated; named volumes were retained.

Live verification confirmed:

- API health and the meaningful synthetic ticket endpoint respond successfully.
- Prometheus sees its own metrics, application request metrics, and the independent HTTP probe.
- Grafana dashboard UID cloudguard-service-desk is provisioned with six panels.
- Grafana reports a healthy database and a working Prometheus datasource.
- The live internal webhook rejects an unauthenticated request with HTTP 401.
- Only recovery mounts the Unix Docker socket. No container runs privileged.
- Recovery has no published host port. All four published interfaces bind to 127.0.0.1.
- Three controlled trials completed successfully without manual cleanup; independent monitoring samples remained UP.

Raw API validation responses are in ignored output/validation/. Each experiment directory contains its own raw request/probe records, structured recovery events, Docker events, relevant logs, and container snapshots. The faculty document and compact aggregate JSON contain results; raw logs and credentials are excluded from Git.

No browser screenshots are claimed as collected in this run. The presentation document contains a checklist for capturing the new implementation. No earlier project's screenshots, logs, or measurements are used. EC2, EBS provisioning, security-group configuration, CloudWatch integration, and AWS performance remain unverified/proposed.
