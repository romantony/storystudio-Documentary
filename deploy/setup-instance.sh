#!/bin/bash
# First-boot setup of the EC2 instance (Ubuntu 24.04 arm64). Used as user data; safe to run again as root.
# The instance profile must allow: SSM core, pull from the docgen ECR repository, read parameters under /docgen/,
# ec2:DescribeTags, and ec2:StopInstances on itself.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 jq git
snap install aws-cli --classic || snap refresh aws-cli
ln -sf /snap/bin/aws /usr/local/bin/aws
mkdir -p /opt/docgen /data/docgen/data /data/docgen/home
chown -R 1000:1000 /data/docgen
rm -rf /opt/docgen/src
git clone --depth 1 https://github.com/romantony/storystudio-Documentary.git /opt/docgen/src
cd /opt/docgen/src/deploy
install -m 644 docker-compose.yml /opt/docgen/
install -m 755 fetch-env.sh deadman.sh /opt/docgen/
install -m 644 docgen.service docgen-deadman.service docgen-deadman.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now docker
systemctl enable docgen.service docgen-deadman.timer
systemctl start docgen-deadman.timer
systemctl start docgen.service
