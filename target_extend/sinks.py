"""Sink classes for target-extend."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from singer_sdk import typing as th
from target_hotglue.sinks import HotglueSink

from target_extend.client import ExtendClient, extract_purchase_number


class ExtendValidationError(ValueError):
    """Raised when a BuyOrders record cannot be converted to Extend payload."""


def _is_blank(value: Any) -> bool:
    """Return whether a value should be treated as missing."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_line_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse and validate the line_items field from a BuyOrders record."""
    if "line_items" not in record or _is_blank(record.get("line_items")):
        raise ExtendValidationError(
            "line_items is required for target-extend BuyOrders"
        )

    raw_line_items = record["line_items"]
    if isinstance(raw_line_items, str):
        try:
            line_items = json.loads(raw_line_items)
        except json.JSONDecodeError as exc:
            raise ExtendValidationError(
                f"line_items must be valid JSON: {exc}"
            ) from exc
    else:
        line_items = raw_line_items

    if not isinstance(line_items, list):
        raise ExtendValidationError("line_items must be a list")

    if not line_items:
        raise ExtendValidationError("line_items must contain at least one line")

    for idx, line in enumerate(line_items):
        if not isinstance(line, dict):
            raise ExtendValidationError(
                f"Invalid BuyOrders line at index {idx}: expected object"
            )

    return line_items


def _format_datetime(value: Any) -> Any:
    """Return JSON-serializable date/datetime values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _validate_positive_number(
    order_id: Any,
    product_remote_id: Any,
    value: Any,
    field_name: str,
) -> float:
    """Validate and normalize a positive numeric line value."""
    if _is_blank(value):
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: {field_name} is required"
        )

    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: {field_name} must be numeric"
        ) from exc

    if normalized <= 0:
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: {field_name} must be > 0"
        )

    return normalized


def _validate_number(
    order_id: Any,
    product_remote_id: Any,
    value: Any,
    field_name: str,
) -> float:
    """Validate and normalize a numeric line value."""
    if _is_blank(value):
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: {field_name} is required"
        )

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: {field_name} must be numeric"
        ) from exc


def _numeric_string_to_int(value: Any) -> Any:
    """Preserve numeric Singer values where possible for Extend payload fields."""
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def build_purchase_order_payload(
    record: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build an Extend PurchaseOrder payload from a BuyOrders record."""
    order_id = record.get("id")
    reference = record.get("externalid") or order_id

    warehouse_code = record.get("Warehouse") or config.get("export_warehouse_code")

    supplier_agreement_number = record.get("supplierAgreementNumber")
    if _is_blank(supplier_agreement_number):
        raise ExtendValidationError(
            "supplierAgreementNumber is required for target-extend purchase orders"
        )

    line_items = parse_line_items(record)

    header: dict[str, Any] = {
        "supplier": {
            "supplierAgreementNumber": _numeric_string_to_int(supplier_agreement_number)
        },
        "reference": str(reference),
    }
    if not _is_blank(warehouse_code):
        header["warehouse"] = str(warehouse_code)

    rows = []
    for idx, line in enumerate(line_items):
        product_remote_id = line.get("product_remoteId")
        if _is_blank(product_remote_id):
            raise ExtendValidationError(
                f"Invalid BuyOrders line for order {order_id}: "
                f"missing product_remoteId at line index {idx}"
            )

        quantity = _validate_positive_number(
            order_id, product_remote_id, line.get("quantity"), "quantity"
        )
        unit_price = _validate_number(
            order_id, product_remote_id, line.get("unitPrice"), "unitPrice"
        )
        vat_percent = _validate_number(
            order_id, product_remote_id, line.get("vatPercent"), "vatPercent"
        )
        currency = line.get("currency") or record.get("currency")
        if _is_blank(currency):
            raise ExtendValidationError(
                f"Invalid BuyOrders line for order {order_id} product_remoteId "
                f"{product_remote_id}: currency is required"
            )

        purchase_unit = line.get("purchase_unit") or "ST"
        product_unit = line.get("product_unit") or purchase_unit
        expected_delivery_date = _format_datetime(
            line.get("expectedDeliveryDate") or record.get("created_at")
        )

        row: dict[str, Any] = {
            "productNumber": _numeric_string_to_int(product_remote_id),
            "purchaseDataPurchaseUnit": {
                "quantity": quantity,
                "unit": str(purchase_unit),
            },
            "purchaseDataProductUnit": {
                "quantity": quantity,
                "unit": str(product_unit),
                "unitPrice": unit_price,
                "vatPercent": vat_percent,
                "currency": str(currency),
            },
        }
        if not _is_blank(expected_delivery_date):
            row["expectedDeliveryDate"] = expected_delivery_date
        rows.append(row)

    return {"header": header, "rows": rows}


class BuyOrdersSink(HotglueSink):
    """Sink for creating Extend purchase orders from the BuyOrders stream."""

    name = "BuyOrders"  # type: ignore[assignment]
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("supplier_remoteId", th.StringType),
        th.Property("supplierAgreementNumber", th.IntegerType, required=True),
        th.Property("Warehouse", th.StringType),
        th.Property("currency", th.StringType),
        th.Property("created_at", th.StringType),
        th.Property("transaction_date", th.StringType),
        th.Property("externalid", th.StringType),
        th.Property(
            "line_items",
            th.ArrayType(
                th.ObjectType(
                    th.Property("product_remoteId", th.StringType, required=True),
                    th.Property("quantity", th.NumberType, required=True),
                    th.Property("unitPrice", th.NumberType, required=True),
                    th.Property("vatPercent", th.NumberType, required=True),
                    th.Property("currency", th.StringType),
                    th.Property("purchase_unit", th.StringType),
                    th.Property("product_unit", th.StringType),
                    th.Property("expectedDeliveryDate", th.StringType),
                )
            ),
            required=True,
        ),
    ).to_dict()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize sink and Extend API client."""
        super().__init__(*args, **kwargs)
        self.client = ExtendClient(dict(self.config))

    def preprocess_record(
        self,
        record: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build Extend payload before upsert."""
        return build_purchase_order_payload(record, dict(self.config))

    def upsert_record(
        self,
        record: dict[str, Any],
        context: dict[str, Any] | None = None,
    ):
        """POST one Extend purchase order."""
        state_updates: dict[str, Any] = {}
        try:
            response = self.client.post_purchase_order(record)
            purchase_number = extract_purchase_number(response)
            state_updates["success"] = True
            return (
                purchase_number or record.get("header", {}).get("reference"),
                True,
                state_updates,
            )
        except Exception as exc:
            self.logger.error(f"Failed to create Extend purchase order: {exc}")
            state_updates["success"] = False
            state_updates["error"] = str(exc)
            return record.get("header", {}).get("reference"), False, state_updates
