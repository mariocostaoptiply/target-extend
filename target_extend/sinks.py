"""Sink classes for target-extend."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from singer_sdk import typing as th
from target_hotglue.sinks import HotglueSink

from target_extend.client import ExtendClient, extract_purchase_number


class ExtendValidationError(ValueError):
    """Raised when a BuyOrders record cannot be converted to Extend payload."""


def _is_blank(value: Any) -> bool:
    """Return whether a value should be treated as missing."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_line_items(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse and validate the line_items field from a BuyOrders record."""
    if "line_items" not in record or _is_blank(record.get("line_items")):
        raise ExtendValidationError("line_items is required for target-extend BuyOrders")

    raw_line_items = record["line_items"]
    if isinstance(raw_line_items, str):
        try:
            line_items = json.loads(raw_line_items)
        except json.JSONDecodeError as exc:
            raise ExtendValidationError(f"line_items must be valid JSON: {exc}") from exc
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


def _validate_quantity(order_id: Any, product_remote_id: Any, quantity: Any) -> float:
    """Validate and normalize line quantity."""
    if _is_blank(quantity):
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: quantity is required"
        )

    try:
        normalized = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: quantity must be numeric"
        ) from exc

    if normalized <= 0:
        raise ExtendValidationError(
            f"Invalid BuyOrders line for order {order_id} product_remoteId "
            f"{product_remote_id}: quantity must be > 0"
        )

    return normalized


def build_purchase_order_payload(
    record: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Build an Extend PurchaseOrder payload from a BuyOrders record."""
    order_id = record.get("id")

    warehouse_code = config.get("export_warehouse_code")

    supplier_remote_id = record.get("supplier_remoteId")
    if _is_blank(supplier_remote_id):
        raise ExtendValidationError(
            "supplier_remoteId is required for target-extend purchase orders"
        )

    line_items = parse_line_items(record)
    delivery_date = _format_datetime(record.get("created_at"))

    header: Dict[str, Any] = {
        "supplier": {"supplierNumber": str(supplier_remote_id)},
        "reference": str(order_id),
    }
    if not _is_blank(warehouse_code):
        header["warehouse"] = str(warehouse_code)
    if not _is_blank(delivery_date):
        header["requestedDeliveryDate"] = delivery_date

    rows = []
    for idx, line in enumerate(line_items):
        product_remote_id = line.get("product_remoteId")
        if _is_blank(product_remote_id):
            raise ExtendValidationError(
                f"Invalid BuyOrders line for order {order_id}: "
                f"missing product_remoteId at line index {idx}"
            )

        quantity = _validate_quantity(order_id, product_remote_id, line.get("quantity"))
        row: Dict[str, Any] = {
            "productNumber": str(product_remote_id),
            "purchaseDataProductUnit": {
                "quantity": quantity,
                "unit": "pcs",
            },
        }
        if not _is_blank(delivery_date):
            row["requestedDeliveryDate"] = delivery_date
            row["expectedDeliveryDate"] = delivery_date
        rows.append(row)

    return {"header": header, "rows": rows}


class BuyOrdersSink(HotglueSink):
    """Sink for creating Extend purchase orders from the BuyOrders stream."""

    name = "BuyOrders"
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("supplier_remoteId", th.StringType, required=True),
        th.Property("created_at", th.StringType),
        th.Property("transaction_date", th.StringType),
        th.Property("externalid", th.StringType),
        th.Property(
            "line_items",
            th.ArrayType(
                th.ObjectType(
                    th.Property("product_remoteId", th.StringType, required=True),
                    th.Property("quantity", th.NumberType, required=True),
                )
            ),
            required=True,
        ),
    ).to_dict()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize sink and Extend API client."""
        super().__init__(*args, **kwargs)
        self.client = ExtendClient(self.config)

    def preprocess_record(
        self,
        record: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build Extend payload before upsert."""
        return build_purchase_order_payload(record, self.config)

    def upsert_record(
        self,
        record: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ):
        """POST one Extend purchase order."""
        state_updates: Dict[str, Any] = {}
        try:
            response = self.client.post_purchase_order(record)
            purchase_number = extract_purchase_number(response)
            state_updates["success"] = True
            return purchase_number or record.get("header", {}).get("reference"), True, state_updates
        except Exception as exc:
            self.logger.error(f"Failed to create Extend purchase order: {exc}")
            state_updates["success"] = False
            state_updates["error"] = str(exc)
            return record.get("header", {}).get("reference"), False, state_updates
