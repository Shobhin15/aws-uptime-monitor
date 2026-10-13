#!/usr/bin/env python3
import os

import aws_cdk as cdk

from uptime_monitor.github_oidc_stack import GithubOidcStack
from uptime_monitor.monitor_stack import UptimeMonitorStack

app = cdk.App()
env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

UptimeMonitorStack(
    app,
    "UptimeMonitorStack",
    target_url=app.node.try_get_context("targetUrl") or "https://shobhin15.github.io",
    expected_text=app.node.try_get_context("expectedText") or "Shobhin Gowrisankar",
    alert_email=app.node.try_get_context("alertEmail") or None,
    env=env,
)

GithubOidcStack(
    app,
    "GithubOidcStack",
    github_repo=app.node.try_get_context("githubRepo") or "shobhin15/aws-uptime-monitor",
    existing_provider_arn=app.node.try_get_context("githubOidcProviderArn") or None,
    env=env,
)

cdk.Tags.of(app).add("project", "aws-uptime-monitor")
app.synth()
