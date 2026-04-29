import json

import pytest

from target_extend.sinks import ExtendValidationError, build_purchase_order_payload


CONFIG = {
    "api_url": "https://example.extend.local/RESTAPI",
    "client": "DEMO_CLIENT",
    "username": "demo-user@example.com",
    "password": "demo-password",
    "export_warehouse_code": "DEMO_WAREHOUSE",
}


def valid_record(**overrides):
    record = {
        "id": "12345",
        "supplier_remoteId": "SUP-1",
        "created_at": "2026-05-15T00:00:00Z",
        "line_items": json.dumps(
            [
                {"product_remoteId": "PROD-1", "quantity": 2},
                {"product_remoteId": "PROD-2", "quantity": "3"},
            ]
        ),
    }
    record.update(overrides)
    return record


def test_builds_valid_purchase_order_payload():
    payload = build_purchase_order_payload(valid_record(), CONFIG)

    assert payload == {
        "header": {
            "warehouse": "DEMO_WAREHOUSE",
            "supplier": {"supplierNumber": "SUP-1"},
            "reference": "12345",
            "requestedDeliveryDate": "2026-05-15T00:00:00Z",
        },
        "rows": [
            {
                "productNumber": "PROD-1",
                "purchaseDataProductUnit": {"quantity": 2.0, "unit": "pcs"},
                "requestedDeliveryDate": "2026-05-15T00:00:00Z",
                "expectedDeliveryDate": "2026-05-15T00:00:00Z",
            },
            {
                "productNumber": "PROD-2",
                "purchaseDataProductUnit": {"quantity": 3.0, "unit": "pcs"},
                "requestedDeliveryDate": "2026-05-15T00:00:00Z",
                "expectedDeliveryDate": "2026-05-15T00:00:00Z",
            },
        ],
    }


def test_missing_warehouse_config_fails():
    config = dict(CONFIG)
    config.pop("export_warehouse_code")

    with pytest.raises(ExtendValidationError, match="export_warehouse_code is required"):
        build_purchase_order_payload(valid_record(), config)


def test_missing_supplier_remote_id_fails():
    with pytest.raises(ExtendValidationError, match="supplier_remoteId is required"):
        build_purchase_order_payload(valid_record(supplier_remoteId=""), CONFIG)


def test_missing_line_items_fails():
    record = valid_record()
    record.pop("line_items")

    with pytest.raises(ExtendValidationError, match="line_items is required"):
        build_purchase_order_payload(record, CONFIG)


def test_missing_product_remote_id_fails_with_line_index():
    record = valid_record(line_items=json.dumps([{"quantity": 1}]))

    with pytest.raises(
        ExtendValidationError,
        match="missing product_remoteId at line index 0",
    ):
        build_purchase_order_payload(record, CONFIG)


def test_invalid_quantity_fails_with_product_remote_id():
    record = valid_record(
        line_items=json.dumps([{"product_remoteId": "PROD-1", "quantity": 0}])
    )

    with pytest.raises(
        ExtendValidationError,
        match="product_remoteId PROD-1: quantity must be > 0",
    ):
        build_purchase_order_payload(record, CONFIG)


def test_created_at_is_optional():
    payload = build_purchase_order_payload(valid_record(created_at=None), CONFIG)

    assert "requestedDeliveryDate" not in payload["header"]
    assert "requestedDeliveryDate" not in payload["rows"][0]
    assert "expectedDeliveryDate" not in payload["rows"][0]
