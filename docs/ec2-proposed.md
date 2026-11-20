# AWS EC2 deployment plan

**Status: proposed.** EC2 deployment and CloudWatch integration have not been performed. The published measurements were collected locally on Docker Desktop.

## Service roles

| AWS component | Proposed role |
|---|---|
| EC2 | One Linux virtual machine running this Compose application and its monitoring/recovery services. This is a single-host demo, not high availability. |
| EBS | Encrypted persistent block storage for Docker data, Prometheus/Alertmanager/Grafana volumes, the recovery journal, and evidence. Snapshot before destructive cleanup. |
| VPC, subnet, security group | Network isolation and a stateful firewall. Permit SSH only from the operator's current public IP; keep demo service ports off the inbound rule list. |
| CloudWatch | Proposed EC2 CPU/status monitoring and optional agent collection of memory/disk metrics and recovery logs. Agent/IAM/log retention setup has not been performed. |

Plan for an Ubuntu 24.04 LTS instance with at least 2 vCPUs, 4 GiB RAM, and approximately 20 GiB of encrypted EBS storage. ARM64 is closest to the locally validated platform. Verify the selected AMI, image architecture, regional availability, budget, and current AWS prices before creating anything. Use an IAM role and least privilege for a future CloudWatch agent, rather than committing access keys. Set log retention and a billing budget before a future demo.

## Restricted inbound access

For a proposed SSH-based demo, the security group needs inbound TCP 22 from the operator's public IPv4 `/32` only. Do not add public inbound rules for 18000, 13000, 19090, 19093, the recovery handler, or Docker's API. Use SSH tunnels for the browser interfaces. Docker may program its own firewall rules, so preserve Compose's explicit localhost binds instead of depending solely on a host firewall.

The Docker socket must remain a Unix socket mounted only inside the recovery container. Never enable an unauthenticated TCP Docker daemon listener. Docker-group membership and socket access are root-equivalent privileges and are for the trusted operator only.

## Docker setup on Ubuntu

The following commands are intended for a future Ubuntu instance and have not been run on AWS for this project. Review the [official Ubuntu Docker installation guide](https://docs.docker.com/engine/install/ubuntu/) before deployment.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and reconnect so the group change applies, then clone the public repository:

```bash
git clone https://github.com/itdanndev-eng/cloudguard.git
cd cloudguard
```

Follow the [quick start](../README.md#quick-start) and [validation workflow](validation.md#validation-workflow) on the instance. Run bootstrap there to generate fresh credentials, and keep secrets and SSH keys out of source control.

## Access through SSH tunnels

Keep the SSH private key outside the repository. Replace the example key path and EC2 DNS placeholder. The alternate local ports below allow access alongside a local CloudGuard stack:

```bash
ssh -i /path/to/operator-key.pem -o ExitOnForwardFailure=yes \
  -L 28000:127.0.0.1:18000 \
  -L 23000:127.0.0.1:13000 \
  -L 29090:127.0.0.1:19090 \
  -L 29093:127.0.0.1:19093 \
  ubuntu@EC2_PUBLIC_DNS
```

For a future deployment, this tunnel would provide access to the API at `http://127.0.0.1:28000`, Grafana at port 23000, Prometheus at 29090, and Alertmanager at 29093. Read the generated Grafana password on the remote host. The internal recovery handler needs no forwarded port or inbound rule.

## Storage and evidence

Docker named volumes live on the instance's filesystem, which should be backed by EBS. Prometheus retention is bounded to three days/256 MB. The recovery journal and Grafana data still require storage monitoring. Retain enough free space for image builds, logs, and the journal. Copy ignored `output/` evidence to an approved backup location before terminating the instance; Git does not back up those raw files.

EC2 validation would need to record the instance/AMI architecture, resource limits, client location, timestamps, image/source versions, and independent probe counts. Run the tests, benchmark, and recovery trials on the instance, then retain that evidence separately from the local Docker Desktop results. AWS validation remains pending.

## Cleanup plan

Use `docker compose stop` to pause the stack while retaining containers and volumes. `docker compose down` removes this project's containers and networks while retaining named volumes. Back up volumes and evidence before deleting data. Before terminating a future instance, review EBS delete-on-termination settings and decide which volumes and snapshots to retain. Include retained EBS storage, snapshots, public IPv4 addresses, and CloudWatch logs in the cleanup review; stopping an instance does not remove storage charges. No AWS resources have been created for this project.

## Official design references

- [EC2 security groups](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html)
- [Amazon EBS volumes and snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/what-is-ebs.html)
- [CloudWatch agent capabilities](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html)
- [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/)
