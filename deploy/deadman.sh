#!/bin/bash
# Run every 5 minutes on the instance (systemd timer or cron). Stops the instance when the orchestrator has gone quiet:
# no job running, no authenticated API call for IDLE_LIMIT seconds, and no keep-awake tag. Covers an orchestrator crash.
set -euo pipefail
IDLE_LIMIT=${IDLE_LIMIT:-1200}
source /opt/docgen/.env
TOK=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOK" http://169.254.169.254/latest/meta-data/instance-id)
KEEP=$(aws ec2 describe-tags --region "${AWS_DEFAULT_REGION:-us-east-1}" --filters "Name=resource-id,Values=$IID" "Name=key,Values=keep-awake" --query 'Tags[0].Value' --output text)
[ "$KEEP" != "None" ] && exit 0
H=$(curl -s -m 10 -H "Authorization: Bearer $DOCGEN_API_TOKEN" -H "X-Origin-Verify: ${DOCGEN_ORIGIN_SECRET:-}" http://127.0.0.1:8080/v1/health || echo '{}')
BUSY=$(echo "$H" | jq -r '.busy // "unknown"'); IDLE=$(echo "$H" | jq -r '.idle_seconds // 0')
UP=$(awk '{print int($1)}' /proc/uptime)
# If the API is down, fall back to uptime so a broken container cannot keep the instance running for ever.
if { [ "$BUSY" = "false" ] && [ "$IDLE" -ge "$IDLE_LIMIT" ]; } || { [ "$BUSY" = "unknown" ] && [ "$UP" -ge 1800 ]; }; then
  logger -t docgen-deadman "stopping instance: busy=$BUSY idle=$IDLE uptime=$UP"
  aws ec2 stop-instances --region "${AWS_DEFAULT_REGION:-us-east-1}" --instance-ids "$IID"
fi
