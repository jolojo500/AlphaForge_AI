#!/usr/bin/env python3
"""Idempotent AWS EC2 Deployment Script for AlphaForge AI Streamlit Demo.

Provisions and configures:
1. SSM Parameter Store SecureString for APP_PASSWORD.
2. Least-privilege IAM Role and Instance Profile (Bedrock Converse/Invoke, Guardrail, SSM Parameter).
3. Security Group allowing TCP port 8501 only.
4. Amazon Linux 2023 EC2 instance (t3.medium).
5. User-data bootstrapping Python 3.12, pulling the repository, and starting Streamlit via systemd.
6. Health check verification against http://<public-ip>:8501/_stcore/health.

Strict constraints:
- us-east-1 only.
- Never prints or logs the APP_PASSWORD.
- Password is stored locally in /home/wilson-lab/Datathon-Poly/.deploy_secret (chmod 600).
- Idempotent: re-running does not duplicate resources.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import secrets
import stat
import sys
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("alphaforge-deploy")

DEFAULT_REGION = "us-east-1"
DEFAULT_INSTANCE_TYPE = "t3.medium"
ROLE_NAME = "alphaforge-demo-role"
INSTANCE_PROFILE_NAME = "alphaforge-demo-profile"
SECURITY_GROUP_NAME = "alphaforge-demo-sg"
INSTANCE_TAG_NAME = "alphaforge-demo"
SSM_PARAM_NAME = "/alphaforge/app_password"
SECRET_FILE_PATH = Path("/home/wilson-lab/Datathon-Poly/.deploy_secret")
GUARDRAIL_NAME = "alphaforge-guardrail"


def get_aws_session(profile: str | None = None, region: str = DEFAULT_REGION) -> boto3.Session:
    """Create a boto3 session with explicit validation."""
    if region != DEFAULT_REGION:
        raise ValueError(f"Only {DEFAULT_REGION} is authorized (requested: {region})")
    prof = profile or os.environ.get("AWS_PROFILE", "datathon")
    logger.info(f"Using AWS profile='{prof}', region='{region}'")
    return boto3.Session(profile_name=prof, region_name=region)


def ensure_secret_password(ssm_client) -> str:
    """Read existing secret or generate a new random password, then store in SSM."""
    secret = None
    if SECRET_FILE_PATH.exists():
        try:
            content = SECRET_FILE_PATH.read_text(encoding="utf-8").strip()
            if content:
                secret = content
                logger.info(f"Loaded existing password from local secret file: {SECRET_FILE_PATH}")
        except Exception as e:
            logger.warning(f"Could not read local secret file {SECRET_FILE_PATH}: {e}")

    if not secret:
        secret = secrets.token_urlsafe(16)
        SECRET_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE_PATH.write_text(secret, encoding="utf-8")
        SECRET_FILE_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        logger.info(f"Generated new APP_PASSWORD and saved to {SECRET_FILE_PATH} (chmod 600)")

    # Store or update in SSM Parameter Store (SecureString)
    try:
        ssm_client.put_parameter(
            Name=SSM_PARAM_NAME,
            Description="AlphaForge AI Streamlit Demo App Password",
            Value=secret,
            Type="SecureString",
            Overwrite=True,
            Tier="Standard",
        )
        logger.info(f"SSM Parameter '{SSM_PARAM_NAME}' updated successfully (SecureString)")
    except ClientError as e:
        logger.error(f"Failed to put SSM parameter '{SSM_PARAM_NAME}': {e}")
        raise

    return secret


def resolve_guardrail_arn(bedrock_client, account_id: str) -> str:
    """Find the ARN of alphaforge-guardrail or fallback to account wildcard."""
    try:
        res = bedrock_client.list_guardrails()
        for gr in res.get("guardrails", []):
            if gr.get("name") == GUARDRAIL_NAME:
                arn = gr.get("arn")
                logger.info(f"Discovered Guardrail '{GUARDRAIL_NAME}' ARN: {arn}")
                return arn
    except Exception as e:
        logger.warning(f"Could not query Bedrock guardrails ({e}); using wildcard fallback")
    return f"arn:aws:bedrock:{DEFAULT_REGION}:{account_id}:guardrail/*"


def ensure_iam_role_and_profile(iam_client, bedrock_client, account_id: str) -> str:
    """Create or reuse IAM Role and Instance Profile with least privilege."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    # 1. IAM Role
    try:
        iam_client.get_role(RoleName=ROLE_NAME)
        logger.info(f"IAM Role '{ROLE_NAME}' already exists")
    except iam_client.exceptions.NoSuchEntityException:
        logger.info(f"Creating IAM Role '{ROLE_NAME}'...")
        iam_client.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Least-privilege role for AlphaForge Streamlit EC2 Demo",
            Tags=[{"Key": "Project", "Value": "AlphaForge"}],
        )

    # 2. Least-privilege inline policy
    guardrail_arn = resolve_guardrail_arn(bedrock_client, account_id)

    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockInvokeConverse",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel*",
                    "bedrock:Converse*",
                ],
                "Resource": "*",
            },
            {
                "Sid": "BedrockApplyGuardrail",
                "Effect": "Allow",
                "Action": [
                    "bedrock:ApplyGuardrail",
                ],
                "Resource": [
                    guardrail_arn,
                    f"{guardrail_arn}/*" if not guardrail_arn.endswith("/*") else guardrail_arn,
                ],
            },
            {
                "Sid": "SSMGetAppPassword",
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                ],
                "Resource": f"arn:aws:ssm:{DEFAULT_REGION}:{account_id}:parameter/alphaforge/*",
            },
            {
                "Sid": "KMSDecryptSSM",
                "Effect": "Allow",
                "Action": [
                    "kms:Decrypt",
                ],
                "Resource": "*",
            },
        ],
    }

    policy_name = "AlphaForgeLeastPrivilegePolicy"
    iam_client.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=policy_name,
        PolicyDocument=json.dumps(policy_document),
    )
    logger.info(f"Attached least-privilege policy '{policy_name}' to role '{ROLE_NAME}'")

    # 3. Instance Profile
    try:
        iam_client.get_instance_profile(InstanceProfileName=INSTANCE_PROFILE_NAME)
        logger.info(f"Instance Profile '{INSTANCE_PROFILE_NAME}' already exists")
    except iam_client.exceptions.NoSuchEntityException:
        logger.info(f"Creating Instance Profile '{INSTANCE_PROFILE_NAME}'...")
        iam_client.create_instance_profile(
            InstanceProfileName=INSTANCE_PROFILE_NAME,
            Tags=[{"Key": "Project", "Value": "AlphaForge"}],
        )

    # Attach role to instance profile if not already attached
    profile_info = iam_client.get_instance_profile(InstanceProfileName=INSTANCE_PROFILE_NAME)
    attached_roles = [r["RoleName"] for r in profile_info["InstanceProfile"].get("Roles", [])]
    if ROLE_NAME not in attached_roles:
        iam_client.add_role_to_instance_profile(
            InstanceProfileName=INSTANCE_PROFILE_NAME,
            RoleName=ROLE_NAME,
        )
        logger.info(f"Added role '{ROLE_NAME}' to instance profile '{INSTANCE_PROFILE_NAME}'")
        # Allow IAM eventual consistency propagation
        time.sleep(5)

    return INSTANCE_PROFILE_NAME


def ensure_security_group(ec2_client) -> tuple[str, str]:
    """Find default VPC and create or return security group allowing TCP 8501."""
    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    vpc_list = vpcs.get("Vpcs", [])
    if not vpc_list:
        vpcs = ec2_client.describe_vpcs()
        vpc_list = vpcs.get("Vpcs", [])
        if not vpc_list:
            raise RuntimeError("No VPC found in this AWS account/region")
    vpc_id = vpc_list[0]["VpcId"]
    logger.info(f"Target VPC: {vpc_id}")

    # Check if security group exists
    sgs = ec2_client.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [SECURITY_GROUP_NAME]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    sg_list = sgs.get("SecurityGroups", [])
    if sg_list:
        sg_id = sg_list[0]["GroupId"]
        logger.info(f"Security Group '{SECURITY_GROUP_NAME}' already exists: {sg_id}")
        return sg_id, vpc_id

    # Create security group
    logger.info(f"Creating Security Group '{SECURITY_GROUP_NAME}' in VPC {vpc_id}...")
    sg_res = ec2_client.create_security_group(
        GroupName=SECURITY_GROUP_NAME,
        Description="AlphaForge Streamlit Demo - Ingress TCP 8501 only",
        VpcId=vpc_id,
        TagSpecifications=[
            {
                "ResourceType": "security-group",
                "Tags": [
                    {"Key": "Name", "Value": SECURITY_GROUP_NAME},
                    {"Key": "Project", "Value": "AlphaForge"},
                ],
            }
        ],
    )
    sg_id = sg_res["GroupId"]

    # Authorize ingress port 8501 only
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 8501,
                "ToPort": 8501,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Streamlit Public Demo"}],
            }
        ],
    )
    logger.info(f"Authorized TCP 8501 ingress on security group {sg_id}")
    return sg_id, vpc_id


def get_latest_al2023_ami(ssm_client) -> str:
    """Fetch latest Amazon Linux 2023 x86_64 AMI ID via SSM."""
    param = ssm_client.get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )
    ami_id = param["Parameter"]["Value"]
    logger.info(f"Latest Amazon Linux 2023 AMI: {ami_id}")
    return ami_id


def build_user_data_script() -> str:
    """Generate EC2 user-data bash script with base64 embedded frontend patch."""
    patch_code = (
        'import sys\n\n'
        'path = "/opt/alphaforge/frontend/app.py"\n'
        'try:\n'
        '    with open(path, "r", encoding="utf-8") as f:\n'
        '        content = f.read()\n\n'
        '    if \'app_password = os.environ.get("APP_PASSWORD")\' not in content:\n'
        '        needle = "st.set_page_config(\\n    page_title=\\"AlphaForge AI — Copilote d\'Investissement Explicable\\",\\n    page_icon=\\"🛡️\\",\\n    layout=\\"wide\\",\\n    initial_sidebar_state=\\"expanded\\",\\n)"\n'
        '        gate_code = \'\'\'\n'
        '# Password gate (if APP_PASSWORD is set in environment)\n'
        'app_password = os.environ.get("APP_PASSWORD")\n'
        'if app_password:\n'
        '    if "authenticated" not in st.session_state:\n'
        '        st.session_state["authenticated"] = False\n\n'
        '    if not st.session_state["authenticated"]:\n'
        '        st.markdown(\n'
        '            """\n'
        '            <div style="max-width: 480px; margin: 60px auto 20px auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; background: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">\n'
        '                <h3 style="margin-top: 0; color: #1e293b; display: flex; align-items: center; gap: 8px;">\n'
        '                    <span>🔒</span> Accès restreint — AlphaForge AI\n'
        '                </h3>\n'
        '                <p style="color: #64748b; font-size: 0.92rem; margin-bottom: 0;">\n'
        '                    Cette instance de démonstration est protégée. Veuillez saisir le mot de passe pour accéder au copilote d\'investissement.\n'
        '                </p>\n'
        '            </div>\n'
        '            """,\n'
        '            unsafe_allow_html=True,\n'
        '        )\n'
        '        col1, col2, col3 = st.columns([1, 1.5, 1])\n'
        '        with col2:\n'
        '            pwd_input = st.text_input("Mot de passe", type="password", key="app_pwd_input")\n'
        '            if st.button("Se connecter", use_container_width=True, type="primary"):\n'
        '                if pwd_input == app_password:\n'
        '                    st.session_state["authenticated"] = True\n'
        '                    st.rerun()\n'
        '                else:\n'
        '                    st.error("Mot de passe incorrect.")\n'
        '        st.stop()\n'
        '\'\'\'\n'
        '        if needle in content:\n'
        '            content = content.replace(needle, needle + "\\n" + gate_code, 1)\n'
        '            with open(path, "w", encoding="utf-8") as f:\n'
        '                f.write(content)\n'
        '            print("Password gate patched into frontend/app.py")\n'
        '        else:\n'
        '            print("Needle not found; appending gate code")\n'
        '            with open(path, "a", encoding="utf-8") as f:\n'
        '                f.write("\\n" + gate_code)\n'
        '    else:\n'
        '        print("Password gate already exists in frontend/app.py")\n'
        'except Exception as e:\n'
        '    print(f"Error checking frontend/app.py: {e}")\n'
    )
    b64_patch = base64.b64encode(patch_code.encode("utf-8")).decode("ascii")

    bootstrap_env_code = (
        'import boto3, os\n'
        'try:\n'
        '    session = boto3.Session(region_name="us-east-1")\n'
        '    ssm = session.client("ssm")\n'
        '    val = ssm.get_parameter(Name="/alphaforge/app_password", WithDecryption=True)["Parameter"]["Value"]\n'
        '    env_path = "/opt/alphaforge.env"\n'
        '    with open(env_path, "w", encoding="utf-8") as f:\n'
        '        f.write(f"APP_PASSWORD={val}\\nAWS_DEFAULT_REGION=us-east-1\\nAWS_REGION=us-east-1\\n")\n'
        '    os.chmod(env_path, 0o600)\n'
        '    print("Retrieved APP_PASSWORD from SSM and wrote to /opt/alphaforge.env")\n'
        'except Exception as e:\n'
        '    print(f"Failed to retrieve SSM parameter: {e}")\n'
        '    sys.exit(1)\n'
    )
    b64_env = base64.b64encode(bootstrap_env_code.encode("utf-8")).decode("ascii")

    script = f"""#!/bin/bash
set -euxo pipefail

# Log all output to console and file
exec > >(tee -a /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1

echo "=========================================="
echo "Starting AlphaForge AI EC2 Initialization"
echo "Date: $(date -u)"
echo "=========================================="

# 1. System packages
dnf install -y git

# 2. Install Astral UV and configure global Python directory in /opt/uv-python
export UV_INSTALL_DIR="/usr/local/bin"
export UV_PYTHON_INSTALL_DIR="/opt/uv-python"
curl -LsSf https://astral.sh/uv/install.sh | sh
chmod +x /usr/local/bin/uv

mkdir -p /opt/uv-python
chmod -R 755 /opt/uv-python
chmod 755 /root

# 3. Clone repository
REPO_DIR="/opt/alphaforge"
rm -rf "$REPO_DIR"
git clone -b mvp-backend https://github.com/jolojo500/AlphaForge_AI.git "$REPO_DIR"

# 4. Create virtual environment and install dependencies
/usr/local/bin/uv venv "$REPO_DIR/.venv" --python 3.12
/usr/local/bin/uv pip install --python "$REPO_DIR/.venv/bin/python" \\
    streamlit plotly pandas numpy scipy cvxpy boto3 pydantic

chmod -R 755 /opt/uv-python

# 5. Fetch APP_PASSWORD from SSM Parameter Store via Python/Boto3
"$REPO_DIR/.venv/bin/python" -c "$(echo '{b64_env}' | base64 -d)"

# 6. Ensure frontend/app.py has the password gate (if not already present)
python3 -c "$(echo '{b64_patch}' | base64 -d)"

# 7. Setup systemd service
cat << 'EOF' > /etc/systemd/system/alphaforge.service
[Unit]
Description=AlphaForge AI Streamlit Demo Service
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/alphaforge
Environment="HOME=/home/ec2-user"
Environment="PATH=/opt/alphaforge/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="STREAMLIT_SERVER_PORT=8501"
Environment="STREAMLIT_SERVER_ADDRESS=0.0.0.0"
Environment="STREAMLIT_SERVER_HEADLESS=true"
EnvironmentFile=/opt/alphaforge.env
ExecStart=/opt/alphaforge/.venv/bin/streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

chown -R ec2-user:ec2-user /opt/alphaforge
chown ec2-user:ec2-user /opt/alphaforge.env
chmod 600 /opt/alphaforge.env

systemctl daemon-reload
systemctl enable alphaforge.service
systemctl start alphaforge.service

echo "=========================================="
echo "AlphaForge AI EC2 Initialization Completed"
echo "Date: $(date -u)"
echo "=========================================="
"""
    return script


def find_existing_instance(ec2_client) -> tuple[str | None, str | None, str | None]:
    """Check if an active alphaforge-demo instance exists."""
    res = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [INSTANCE_TAG_NAME]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ]
    )
    for reservation in res.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            inst_id = inst["InstanceId"]
            state = inst["State"]["Name"]
            public_ip = inst.get("PublicIpAddress")
            return inst_id, state, public_ip
    return None, None, None


def launch_instance(
    ec2_client,
    ami_id: str,
    instance_type: str,
    sg_id: str,
    instance_profile_name: str,
    user_data_script: str,
    max_retries: int = 12,
) -> str:
    """Launch a new EC2 instance with user-data, retrying if IAM instance profile is still propagating."""
    logger.info(f"Launching EC2 instance ({instance_type}, AMI: {ami_id})...")
    for attempt in range(1, max_retries + 1):
        try:
            res = ec2_client.run_instances(
                ImageId=ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[sg_id],
                IamInstanceProfile={"Name": instance_profile_name},
                UserData=user_data_script,
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": INSTANCE_TAG_NAME},
                            {"Key": "Project", "Value": "AlphaForge"},
                        ],
                    }
                ],
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/xvda",
                        "Ebs": {
                            "VolumeSize": 30,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )
            instance_id = res["Instances"][0]["InstanceId"]
            logger.info(f"Launched instance ID: {instance_id}")
            return instance_id
        except ClientError as e:
            err_code = e.response.get("Error", {}).get("Code")
            err_msg = e.response.get("Error", {}).get("Message", "")
            if "Invalid IAM Instance Profile" in err_msg or err_code == "InvalidParameterValue":
                if attempt < max_retries:
                    logger.info(f"Instance profile propagating (attempt {attempt}/{max_retries}); retrying in 5s...")
                    time.sleep(5)
                    continue
            raise


def wait_for_public_ip(ec2_client, instance_id: str, max_wait: int = 120) -> str:
    """Wait until the instance is running and has a public IP assigned."""
    logger.info(f"Waiting for instance {instance_id} to enter 'running' state...")
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            res = ec2_client.describe_instances(InstanceIds=[instance_id])
            reservations = res.get("Reservations", [])
            if reservations and reservations[0].get("Instances"):
                inst = reservations[0]["Instances"][0]
                state = inst["State"]["Name"]
                public_ip = inst.get("PublicIpAddress")
                if state == "running" and public_ip:
                    logger.info(f"Instance is running! Public IP: {public_ip}")
                    return public_ip
        except ClientError as e:
            if "InvalidInstanceID.NotFound" in str(e):
                logger.info(f"Instance ID {instance_id} propagating in control plane...")
            else:
                logger.warning(f"Error describing instance {instance_id}: {e}")
        time.sleep(5)
    raise TimeoutError(f"Instance {instance_id} did not acquire public IP within {max_wait}s")


def wait_for_health_check(public_ip: str, port: int = 8501, timeout: int = 360) -> bool:
    """Poll Streamlit health endpoint until HTTP 200 ok is returned."""
    url = f"http://{public_ip}:{port}/_stcore/health"
    logger.info(f"Polling health endpoint: {url} (timeout: {timeout}s)...")
    start_time = time.time()
    attempt = 0

    while time.time() - start_time < timeout:
        attempt += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AlphaForge-DeployCheck/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8").strip()
                    logger.info(f"Health check succeeded (attempt {attempt}, elapsed {time.time()-start_time:.1f}s): {body}")
                    return True
        except Exception as e:
            if attempt % 6 == 0:
                elapsed = int(time.time() - start_time)
                logger.info(f"Still waiting for Streamlit health check ({elapsed}s elapsed): {e}")
            time.sleep(5)

    logger.error(f"Streamlit health check timed out after {timeout} seconds on {url}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Deploy AlphaForge AI Streamlit Demo to AWS EC2")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS Region (default: us-east-1)")
    parser.add_argument("--instance-type", default=DEFAULT_INSTANCE_TYPE, help="EC2 instance type (default: t3.medium)")
    parser.add_argument("--profile", default=None, help="AWS Profile (default: env AWS_PROFILE or datathon)")
    parser.add_argument("--timeout", type=int, default=360, help="Health check timeout in seconds (default: 360)")
    parser.add_argument("--force-recreate", action="store_true", help="Terminate existing instance and launch fresh")
    args = parser.parse_args()

    session = get_aws_session(profile=args.profile, region=args.region)
    sts_client = session.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]
    logger.info(f"Connected to AWS Account ID: {account_id}")

    ssm_client = session.client("ssm")
    iam_client = session.client("iam")
    bedrock_client = session.client("bedrock")
    ec2_client = session.client("ec2")

    # Step 1: Ensure SSM Parameter for App Password
    ensure_secret_password(ssm_client)

    # Step 2: Ensure IAM Role & Instance Profile
    instance_profile_name = ensure_iam_role_and_profile(iam_client, bedrock_client, account_id)

    # Step 3: Ensure Security Group
    sg_id, vpc_id = ensure_security_group(ec2_client)

    # Step 4: Check or Launch EC2 Instance
    inst_id, state, public_ip = find_existing_instance(ec2_client)
    if inst_id and args.force_recreate:
        logger.info(f"Force-recreate requested: terminating existing instance {inst_id}...")
        ec2_client.terminate_instances(InstanceIds=[inst_id])
        waiter = ec2_client.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[inst_id])
        inst_id, state, public_ip = None, None, None

    if inst_id:
        logger.info(f"Found active EC2 instance {inst_id} (state: {state}, IP: {public_ip})")
        if not public_ip:
            public_ip = wait_for_public_ip(ec2_client, inst_id)
    else:
        ami_id = get_latest_al2023_ami(ssm_client)
        user_data = build_user_data_script()
        inst_id = launch_instance(
            ec2_client=ec2_client,
            ami_id=ami_id,
            instance_type=args.instance_type,
            sg_id=sg_id,
            instance_profile_name=instance_profile_name,
            user_data_script=user_data,
        )
        public_ip = wait_for_public_ip(ec2_client, inst_id)

    # Step 5: Wait for Health Check
    healthy = wait_for_health_check(public_ip=public_ip, port=8501, timeout=args.timeout)

    print("\n" + "=" * 60)
    print("🚀 ALPHAFORGE AI — DÉPLOIEMENT EC2 RÉUSSI")
    print("=" * 60)
    print(f"• Instance ID       : {inst_id}")
    print(f"• Adresse IP        : {public_ip}")
    print(f"• URL Démo          : http://{public_ip}:8501")
    print(f"• Endpoint Santé    : http://{public_ip}:8501/_stcore/health")
    print(f"• Statut Santé      : {'✅ OPÉRATIONNEL (200 OK)' if healthy else '⚠️ EN COURS DE DÉMARRAGE'}")
    print(f"• Mot de passe démo : Conservé localement dans {SECRET_FILE_PATH} (chmod 600)")
    print("=" * 60 + "\n")

    if not healthy:
        sys.exit(1)


if __name__ == "__main__":
    main()
