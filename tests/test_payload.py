from datetime import datetime, timezone
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


def valid_line(**overrides):
    line = {
        "product_remoteId": "10001",
        "quantity": 10,
        "unitPrice": 12.34,
        "vatPercent": 0.0,
        "currency": "USD",
        "purchase_unit": "ST",
        "product_unit": "ST",
        "expectedDeliveryDate": "2026-06-26T00:00:00Z",
    }
    line.update(overrides)
    return line


def valid_record(**overrides):
    record = {
        "id": 1000001,
        "externalid": "OP-1000001",
        "supplier_remoteId": 123,
        "supplierAgreementNumber": 123,
        "Warehouse": "DEMO_WAREHOUSE_RECORD",
        "currency": "USD",
        "created_at": "2026-06-26T00:00:00.000000Z",
        "line_items": json.dumps([valid_line()]),
    }
    record.update(overrides)
    return record


def test_builds_extend_purchase_order_payload_from_enriched_buy_order():
    payload = build_purchase_order_payload(valid_record(), CONFIG)

    assert payload == {
        "header": {
            "warehouse": "DEMO_WAREHOUSE_RECORD",
            "supplier": {"supplierAgreementNumber": 123},
            "reference": "OP-1000001",
        },
        "rows": [
            {
                "productNumber": 10001,
                "purchaseDataPurchaseUnit": {"quantity": 10.0, "unit": "ST"},
                "purchaseDataProductUnit": {
                    "quantity": 10.0,
                    "unit": "ST",
                    "unitPrice": 12.34,
                    "vatPercent": 0.0,
                    "currency": "USD",
                },
                "expectedDeliveryDate": "2026-06-26T00:00:00Z",
            }
        ],
    }


def test_config_warehouse_is_fallback_when_record_has_no_warehouse():
    payload = build_purchase_order_payload(valid_record(Warehouse=None), CONFIG)

    assert payload["header"]["warehouse"] == "DEMO_WAREHOUSE"


def test_missing_warehouse_omits_warehouse():
    config = dict(CONFIG)
    config.pop("export_warehouse_code")

    payload = build_purchase_order_payload(valid_record(Warehouse=None), config)

    assert "warehouse" not in payload["header"]


def test_missing_supplier_agreement_number_fails():
    with pytest.raises(
        ExtendValidationError, match="supplierAgreementNumber is required"
    ):
        build_purchase_order_payload(valid_record(supplierAgreementNumber=""), CONFIG)


def test_missing_line_items_fails():
    record = valid_record()
    record.pop("line_items")

    with pytest.raises(ExtendValidationError, match="line_items is required"):
        build_purchase_order_payload(record, CONFIG)


def test_missing_product_remote_id_fails_with_line_index():
    record = valid_record(line_items=json.dumps([valid_line(product_remoteId="")]))

    with pytest.raises(
        ExtendValidationError,
        match="missing product_remoteId at line index 0",
    ):
        build_purchase_order_payload(record, CONFIG)


def test_invalid_quantity_fails_with_product_remote_id():
    record = valid_record(line_items=json.dumps([valid_line(quantity=0)]))

    with pytest.raises(
        ExtendValidationError,
        match="product_remoteId 10001: quantity must be > 0",
    ):
        build_purchase_order_payload(record, CONFIG)


def test_missing_currency_uses_record_currency_fallback():
    record = valid_record(line_items=json.dumps([valid_line(currency=None)]))

    payload = build_purchase_order_payload(record, CONFIG)

    assert payload["rows"][0]["purchaseDataProductUnit"]["currency"] == "USD"


def test_missing_expected_delivery_date_uses_created_at_fallback():
    record = valid_record(
        line_items=json.dumps([valid_line(expectedDeliveryDate=None)])
    )

    payload = build_purchase_order_payload(record, CONFIG)

    assert payload["rows"][0]["expectedDeliveryDate"] == "2026-06-26T00:00:00.000000Z"


def test_does_not_send_requested_delivery_date():
    payload = build_purchase_order_payload(valid_record(), CONFIG)

    assert "requestedDeliveryDate" not in payload["header"]
    assert "requestedDeliveryDate" not in payload["rows"][0]


def test_created_at_datetime_fallback_is_serialized():
    created_at = datetime(2026, 6, 26, tzinfo=timezone.utc)
    record = valid_record(
        created_at=created_at,
        line_items=json.dumps([valid_line(expectedDeliveryDate=None)]),
    )

    payload = build_purchase_order_payload(record, CONFIG)

    assert payload["rows"][0]["expectedDeliveryDate"] == "2026-06-26T00:00:00+00:00"
    json.dumps(payload)
