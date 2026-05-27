"""Target Extend class."""

from __future__ import annotations

from singer_sdk import typing as th
from target_hotglue.target import TargetHotglue

from target_extend.sinks import BuyOrdersSink


class TargetExtend(TargetHotglue):
    """Hotglue Singer target for Extend Commerce."""

    name = "target-extend"  # type: ignore[assignment]

    config_jsonschema = th.PropertiesList(
        th.Property(
            "api_url",
            th.StringType,
            required=True,
            description="Extend REST API base URL, e.g. https://example.extend.local/RESTAPI",
        ),
        th.Property(
            "client",
            th.StringType,
            required=True,
            description="Extend client path segment, e.g. DEMO_CLIENT",
        ),
        th.Property(
            "username",
            th.StringType,
            required=True,
            description="Extend username used for Basic authentication",
        ),
        th.Property(
            "password",
            th.StringType,
            required=True,
            description="Extend password used for Basic authentication",
        ),
        th.Property(
            "export_warehouse_code",
            th.StringType,
            required=False,
            description="Optional warehouse code to send on created purchase orders",
        ),
        th.Property(
            "timeout",
            th.IntegerType,
            default=300,
            description="HTTP request timeout in seconds",
        ),
    ).to_dict()

    SINK_TYPES = [BuyOrdersSink]  # type: ignore[assignment]


if __name__ == "__main__":
    TargetExtend.cli()  # type: ignore[operator]
