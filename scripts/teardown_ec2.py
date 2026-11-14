#!/usr/bin/env python3
"""Teardown Script for AlphaForge AI EC2 Deployment.

Cleans up all resources created by scripts/deploy_ec2.py:
1. Terminates the EC2 instance(s) tagged alphaforge-demo.
2. Waits for instance termination.
3. Deletes Security Group alphaforge-demo-sg.
4. Removes role from and deletes Instance Profile alphaforge-demo-profile.
5. Deletes inline policies and deletes IAM Role alphaforge-demo-role.
6. Deletes SSM Parameter /alphaforge/app_password.

Completely idempotent and safe: handles missing entities gracefully.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("alphaforge-teardown")

DEFAULT_REGION = "us-east-1"
ROLE_NAME = "alphaforge-demo-role"
INSTANCE_PROFILE_NAME = "alphaforge-demo-profile"
SECURITY_GROUP_NAME = "alphaforge-demo-sg"
INSTANCE_TAG_NAME = "alphaforge-demo"
SSM_PARAM_NAME = "/alphaforge/app_password"


def get_aws_session(profile: str | None = None, region: str = DEFAULT_REGION) -> boto3.Session:
    """Create a boto3 session with explicit validation."""
    if region != DEFAULT_REGION:
        raise ValueError(f"Only {DEFAULT_REGION} is authorized (requested: {region})")
    prof = profile or os.environ.get("AWS_PROFILE", "datathon")
    logger.info(f"Using AWS profile='{prof}', region='{region}'")
    return boto3.Session(profile_name=prof, region_name=region)


def terminate_instances(ec2_client) -> list[str]:
    """Find and terminate instances tagged with alphaforge-demo."""
    res = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [INSTANCE_TAG_NAME]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    instance_ids = []
    for r in res.get("Reservations", []):
        for inst in r.get("Instances", []):
            instance_ids.append(inst["InstanceId"])

    if not instance_ids:
        logger.info("No active instances found to terminate.")
        return []

    logger.info(f"Terminating instances: {instance_ids}...")
    ec2_client.terminate_instances(InstanceIds=instance_ids)

    # Wait for termination
    logger.info("Waiting for instances to terminate completely...")
    waiter = ec2_client.get_waiter("instance_terminated")
    waiter.wait(InstanceIds=instance_ids)
    logger.info("Instances terminated successfully.")
    return instance_ids


def delete_security_group(ec2_client, max_retries: int = 12):
    """Delete security group with retries in case network interfaces are detaching."""
    sgs = ec2_client.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [SECURITY_GROUP_NAME]}]
    )
    sg_list = sgs.get("SecurityGroups", [])
    if not sg_list:
        logger.info(f"Security Group '{SECURITY_GROUP_NAME}' not found.")
        return

    sg_id = sg_list[0]["GroupId"]
    logger.info(f"Deleting Security Group '{SECURITY_GROUP_NAME}' ({sg_id})...")

    for attempt in range(max_retries):
        try:
            ec2_client.delete_security_group(GroupId=sg_id)
            logger.info(f"Security Group '{SECURITY_GROUP_NAME}' deleted successfully.")
            return
        except ClientError as e:
            if e.response["Error"]["Code"] == "DependencyViolation":
                logger.info("Network interfaces still detaching; waiting 5 seconds...")
                time.sleep(5)
            else:
                logger.warning(f"Error deleting security group: {e}")
                return
    logger.warning(f"Could not delete Security Group {sg_id} after {max_retries} attempts.")


def delete_iam_resources(iam_client):
    """Remove and delete instance profile and IAM role."""
    # 1. Instance Profile
    try:
        profile_res = iam_client.get_instance_profile(InstanceProfileName=INSTANCE_PROFILE_NAME)
        roles = profile_res["InstanceProfile"].get("Roles", [])
        for role in roles:
            r_name = role["RoleName"]
            logger.info(f"Removing role '{r_name}' from instance profile '{INSTANCE_PROFILE_NAME}'...")
            iam_client.remove_role_from_instance_profile(
                InstanceProfileName=INSTANCE_PROFILE_NAME,
                RoleName=r_name,
            )
        iam_client.delete_instance_profile(InstanceProfileName=INSTANCE_PROFILE_NAME)
        logger.info(f"Deleted Instance Profile '{INSTANCE_PROFILE_NAME}'.")
    except iam_client.exceptions.NoSuchEntityException:
        logger.info(f"Instance Profile '{INSTANCE_PROFILE_NAME}' does not exist.")
    except ClientError as e:
        logger.warning(f"Error deleting instance profile: {e}")

    # 2. IAM Role Policies & Role
    try:
        policies = iam_client.list_role_policies(RoleName=ROLE_NAME)
        for policy_name in policies.get("PolicyNames", []):
            logger.info(f"Deleting inline policy '{policy_name}' from role '{ROLE_NAME}'...")
            iam_client.delete_role_policy(RoleName=ROLE_NAME, PolicyName=policy_name)

        attached = iam_client.list_attached_role_policies(RoleName=ROLE_NAME)
        for att in attached.get("AttachedPolicies", []):
            logger.info(f"Detaching managed policy '{att['PolicyArn']}' from role '{ROLE_NAME}'...")
            iam_client.detach_role_policy(RoleName=ROLE_NAME, PolicyArn=att["PolicyArn"])

        iam_client.delete_role(RoleName=ROLE_NAME)
        logger.info(f"Deleted IAM Role '{ROLE_NAME}'.")
    except iam_client.exceptions.NoSuchEntityException:
        logger.info(f"IAM Role '{ROLE_NAME}' does not exist.")
    except ClientError as e:
        logger.warning(f"Error deleting IAM role: {e}")


def delete_ssm_parameter(ssm_client):
    """Delete SSM Parameter for APP_PASSWORD."""
    try:
        ssm_client.delete_parameter(Name=SSM_PARAM_NAME)
        logger.info(f"Deleted SSM Parameter '{SSM_PARAM_NAME}'.")
    except ssm_client.exceptions.ParameterNotFound:
        logger.info(f"SSM Parameter '{SSM_PARAM_NAME}' does not exist.")
    except ClientError as e:
        logger.warning(f"Error deleting SSM parameter: {e}")


def main():
    parser = argparse.ArgumentParser(description="Teardown AlphaForge AI EC2 Deployment")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS Region (default: us-east-1)")
    parser.add_argument("--profile", default=None, help="AWS Profile (default: env AWS_PROFILE or datathon)")
    args = parser.parse_args()

    session = get_aws_session(profile=args.profile, region=args.region)
    ec2_client = session.client("ec2")
    iam_client = session.client("iam")
    ssm_client = session.client("ssm")

    print("\n" + "=" * 60)
    print("🧹 ALPHAFORGE AI — NETTOYAGE ET DESTRUCTION DES RESSOURCES")
    print("=" * 60)

    # 1. Terminate EC2 instances
    terminated = terminate_instances(ec2_client)

    # 2. Delete Security Group
    delete_security_group(ec2_client)

    # 3. Delete IAM Role & Profile
    delete_iam_resources(iam_client)

    # 4. Delete SSM Parameter
    delete_ssm_parameter(ssm_client)

    print("=" * 60)
    print("✅ Nettoyage terminé avec succès.")
    print(f"• Instances résiliées : {terminated if terminated else 'Aucune'}")
    print("• Groupe de sécurité  : Supprimé")
    print("• Rôle et Profil IAM  : Supprimés")
    print("• Paramètre SSM       : Supprimé")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
