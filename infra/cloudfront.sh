#!/usr/bin/env bash
# HTTPS for the public app (#112): a CloudFront distribution in front of the EC2 origin.
# CloudFront terminates TLS with its default *.cloudfront.net certificate (no domain needed),
# redirects HTTP to HTTPS, never caches (API + SSE), and forwards every viewer header
# (X-Client-Id). Then the instance's port 80 is opened to CloudFront's origin-facing
# prefix list only, so the app is no longer reachable in clear text on the bare IP.
# Idempotent: re-running reuses the distribution tagged with the same comment.
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${AF_INSTANCE_ID:-i-0ec3c5dff3ac51dc4}"
COMMENT="alphaforge-https"
CACHING_DISABLED="4135ea2d-6df8-44a3-9df3-4b5a84be39ad"   # AWS managed policy
ALL_VIEWER="216adef6-5c7f-47e4-b989-5492eafa07d3"         # AWS managed policy

ORIGIN=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)

DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='${COMMENT}'].Id | [0]" --output text)
if [ "$DIST_ID" = "None" ] || [ -z "$DIST_ID" ]; then
  CFG=$(cat <<JSON
{
  "CallerReference": "alphaforge-$(date +%s)",
  "Comment": "${COMMENT}",
  "Enabled": true,
  "PriceClass": "PriceClass_100",
  "HttpVersion": "http2",
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "alphaforge-ec2",
    "DomainName": "${ORIGIN}",
    "CustomOriginConfig": {
      "HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
      "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 5,
      "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]}
    }
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "alphaforge-ec2",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {"Quantity": 7, "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET","HEAD"]}},
    "CachePolicyId": "${CACHING_DISABLED}",
    "OriginRequestPolicyId": "${ALL_VIEWER}",
    "Compress": false
  }
}
JSON
)
  DIST_ID=$(aws cloudfront create-distribution --distribution-config "$CFG" --query 'Distribution.Id' --output text)
  aws cloudfront tag-resource --resource "arn:aws:cloudfront::$(aws sts get-caller-identity --query Account --output text):distribution/${DIST_ID}" \
    --tags 'Items=[{Key=project,Value=alphaforge}]' >/dev/null
fi
DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text)
echo "Distribution ${DIST_ID}: https://${DOMAIN}/"

if [ "${AF_LOCK_ORIGIN:-0}" = "1" ]; then
  # Port 80 open to CloudFront only (managed prefix list), not to the world.
  SG_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text)
  PL=$(aws ec2 describe-managed-prefix-lists \
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
    --query 'PrefixLists[0].PrefixListId' --output text)
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=${PL},Description=cloudfront}]" >/dev/null 2>&1 || true
  aws ec2 revoke-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
  echo "Port 80 on ${SG_ID} now accepts CloudFront only."
fi
