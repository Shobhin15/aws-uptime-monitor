import pytest

cdk = pytest.importorskip("aws_cdk")
from aws_cdk.assertions import Match, Template  # noqa: E402

from uptime_monitor.github_oidc_stack import GithubOidcStack  # noqa: E402
from uptime_monitor.monitor_stack import UptimeMonitorStack  # noqa: E402


@pytest.fixture(scope="module")
def monitor_template():
    app = cdk.App()
    stack = UptimeMonitorStack(
        app, "TestMonitor", target_url="https://example.com", expected_text="hello", alert_email="me@example.com"
    )
    return Template.from_stack(stack)


def test_checker_lambda(monitor_template):
    monitor_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Handler": "handler.handler",
            "Architectures": ["arm64"],
            "Environment": {"Variables": Match.object_like({"TARGET_URL": "https://example.com"})},
        },
    )


def test_runs_every_five_minutes(monitor_template):
    monitor_template.has_resource_properties("AWS::Events::Rule", {"ScheduleExpression": "rate(5 minutes)"})


def test_alarms_and_email_alerts(monitor_template):
    monitor_template.resource_count_is("AWS::CloudWatch::Alarm", 2)
    monitor_template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {"MetricName": "Up", "Namespace": "UptimeMonitor", "EvaluationPeriods": 2, "TreatMissingData": "breaching"},
    )
    monitor_template.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "me@example.com"}
    )


def test_logs_expire(monitor_template):
    monitor_template.has_resource_properties("AWS::Logs::LogGroup", {"RetentionInDays": 7})


def test_no_email_subscription_without_address():
    app = cdk.App()
    stack = UptimeMonitorStack(app, "NoEmail", target_url="https://example.com")
    Template.from_stack(stack).resource_count_is("AWS::SNS::Subscription", 0)


def test_oidc_role_is_locked_to_repo_and_branch():
    app = cdk.App()
    stack = GithubOidcStack(app, "TestOidc", github_repo="shobhin15/aws-uptime-monitor")
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sts:AssumeRoleWithWebIdentity",
                                    "Condition": {
                                        "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                                        "StringLike": {
                                            "token.actions.githubusercontent.com:sub": "repo:shobhin15/aws-uptime-monitor:ref:refs/heads/main"
                                        },
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
