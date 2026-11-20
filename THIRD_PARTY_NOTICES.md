# Third-party dependencies and notices

CloudGuard application, recovery, configuration, tests, scripts, and dashboard are original project code. Standard dependencies are installed or pulled from upstream distributions rather than copied into this repository. Their own license and NOTICE files are retained in installed packages and official container images; the Dockerfile does not remove distribution metadata or license files.

| Dependency | License | Upstream |
|---|---|---|
| Python | PSF license | https://docs.python.org/3/license.html |
| Flask, Werkzeug, Jinja2, MarkupSafe, Click, ItsDangerous | BSD-3-Clause | https://palletsprojects.com/ |
| Blinker | MIT | https://github.com/pallets-eco/blinker |
| Gunicorn | MIT | https://github.com/benoitc/gunicorn |
| prometheus-client | Apache-2.0 | https://github.com/prometheus/client_python |
| Prometheus, Alertmanager, Blackbox Exporter | Apache-2.0 | https://github.com/prometheus |
| Grafana OSS | AGPL-3.0-only | https://github.com/grafana/grafana |

`requirements.lock` records tested Python dependency versions. Compose pins monitoring image versions. No monitoring product's source is modified or bundled into the original application source. Refer to each linked upstream license for its complete terms before redistributing dependency binaries or modified products. AWS deployment is proposed only.
