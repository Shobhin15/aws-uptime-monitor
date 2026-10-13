from __future__ import annotations

from aws_cdk import CfnOutput, Duration, Stack, aws_iam as iam
from constructs import Construct

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"


class GithubOidcStack(Stack):
    """One-time setup: lets GitHub Actions deploy with short-lived credentials instead of stored AWS keys.

    The role can only be assumed by workflows running on `branch` of `github_repo`,
    and it can only assume the CDK bootstrap roles (cdk-*), so it cannot touch
    anything else in the account directly.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_repo: str,
        branch: str = "main",
        existing_provider_arn: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # An AWS account can only have one GitHub OIDC provider. Reuse it if it already exists.
        if existing_provider_arn:
            provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
                self, "GithubProvider", existing_provider_arn
            )
        else:
            provider = iam.OpenIdConnectProvider(
                self,
                "GithubProvider",
                url=GITHUB_OIDC_URL,
                client_ids=["sts.amazonaws.com"],
            )

        role = iam.Role(
            self,
            "DeployRole",
            description=f"Deploys CDK stacks from GitHub Actions ({github_repo}, {branch} branch only)",
            max_session_duration=Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repo}:ref:refs/heads/{branch}"
                    },
                },
            ),
        )

        # CDK deploys by assuming its bootstrap roles; that is all this role needs.
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:{self.partition}:iam::{self.account}:role/cdk-*"],
            )
        )

        CfnOutput(self, "DeployRoleArn", value=role.role_arn)
