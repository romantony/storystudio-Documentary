#!/bin/bash
# Run at every boot before the container starts: write /opt/docgen/.env from SSM Parameter Store.
# Every parameter under /docgen/ becomes NAME=value (see .env.example for the names). If the fetch fails, the old file stays.
set -euo pipefail
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
umask 077
T=$(mktemp /opt/docgen/.env.XXXXXX)
trap 'rm -f "$T"' EXIT
{
  echo "DOCGEN_IMAGE_URI=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/docgen:latest"
  echo "AWS_DEFAULT_REGION=$REGION"
  echo "ANTHROPIC_MODEL=claude-sonnet-5-5"
  # later lines win, so a parameter with one of the names above overrides it
  aws ssm get-parameters-by-path --region "$REGION" --path /docgen/ --with-decryption --output json \
    | jq -r '.Parameters[] | "\(.Name | sub(".*/"; ""))=\(.Value)"'
} > "$T"
mv "$T" /opt/docgen/.env
