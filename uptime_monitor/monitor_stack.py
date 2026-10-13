from __future__ import annotations

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
from constructs import Construct

LAMBDA_DIR = Path(__file__).resolve().parent.parent / "lambda" / "checker"
METRIC_NAMESPACE = "UptimeMonitor"


class UptimeMonitorStack(Stack):
    """Scheduled Lambda health check with CloudWatch metrics, alarms, a dashboard, and SNS alerts."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        target_url: str,
        expected_text: str = "",
        alert_email: str | None = None,
        check_interval_minutes: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "CheckerLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        checker = _lambda.Function(
            self,
            "Checker",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="handler.handler",
            code=_lambda.Code.from_asset(str(LAMBDA_DIR)),
            timeout=Duration.seconds(30),
            memory_size=128,
            log_group=log_group,
            description="Checks the portfolio site and emits uptime and latency metrics",
            environment={
                "TARGET_URL": target_url,
                "EXPECTED_TEXT": expected_text,
                "METRIC_NAMESPACE": METRIC_NAMESPACE,
                "TIMEOUT_SECONDS": "10",
            },
        )

        events.Rule(
            self,
            "Schedule",
            description=f"Run the uptime check every {check_interval_minutes} minutes",
            schedule=events.Schedule.rate(Duration.minutes(check_interval_minutes)),
            targets=[targets.LambdaFunction(checker)],
        )

        period = Duration.minutes(check_interval_minutes)
        up_metric = cw.Metric(
            namespace=METRIC_NAMESPACE,
            metric_name="Up",
            dimensions_map={"Url": target_url},
            statistic=cw.Stats.MINIMUM,
            period=period,
        )
        latency_metric = cw.Metric(
            namespace=METRIC_NAMESPACE,
            metric_name="LatencyMs",
            dimensions_map={"Url": target_url},
            statistic=cw.Stats.AVERAGE,
            period=period,
        )

        topic = sns.Topic(self, "AlertTopic", display_name="Portfolio uptime alerts")
        if alert_email:
            topic.add_subscription(subs.EmailSubscription(alert_email))

        # Two failed checks in a row = down. Missing data counts as failing,
        # so we also hear about it if the checker itself stops running.
        site_down = cw.Alarm(
            self,
            "SiteDownAlarm",
            alarm_description=f"{target_url} failed two health checks in a row",
            metric=up_metric,
            threshold=1,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            treat_missing_data=cw.TreatMissingData.BREACHING,
        )
        site_down.add_alarm_action(cw_actions.SnsAction(topic))
        site_down.add_ok_action(cw_actions.SnsAction(topic))

        checker_errors = cw.Alarm(
            self,
            "CheckerErrorsAlarm",
            alarm_description="The uptime checker Lambda itself is erroring",
            metric=checker.metric_errors(period=period),
            threshold=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        checker_errors.add_alarm_action(cw_actions.SnsAction(topic))

        cw.Dashboard(
            self,
            "Dashboard",
            dashboard_name="portfolio-uptime",
            widgets=[
                [
                    cw.GraphWidget(title="Up (1 = healthy)", left=[up_metric], width=12),
                    cw.GraphWidget(title="Latency (ms)", left=[latency_metric], width=12),
                ],
                [cw.AlarmStatusWidget(title="Alarms", alarms=[site_down, checker_errors], width=24)],
            ],
        )

        CfnOutput(self, "CheckerFunctionName", value=checker.function_name)
        CfnOutput(self, "AlertTopicArn", value=topic.topic_arn)
