#!/usr/bin/env bash
# Fast redeploy script for AlphaForge AI (SSM update).
# Builds latest Docker image, pushes to ECR, and updates running EC2 container via SSM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/deploy.sh" update "$@"
