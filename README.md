# target-extend

A [Singer](https://www.singer.io/) target for sending PurchaseOrders to the Extend Commerce REST API, built with the Hotglue Target SDK.

## Overview

This target sends Optiply `BuyOrders` records to Extend Commerce as purchase orders.

It performs one API call per incoming purchase order:

1. **Create Purchase Order**: `POST /RESTAPI/v1_0/{client}/PurchaseOrders`

The target is POST-only. It does not look up existing purchase orders or perform duplicate prevention.

## Installation

```bash
pip install target-extend
```

Or install from source:

```bash
git clone <repository-url>
cd target-extend
pip install -e .
```

## Configuration

The target requires the following configuration:

- `api_url` (required): Extend REST API base URL
- `client` (required): Extend client path segment
- `username` (required): Extend username
- `password` (required): Extend password
- `export_warehouse_code` (optional): Warehouse code to send on purchase orders. If omitted, the target does not send `header.warehouse`.
- `timeout` (optional): Request timeout in seconds (default: `300`)

### Example Configuration

```json
{
  "api_url": "https://example.extend.local/RESTAPI",
  "client": "DEMO_CLIENT",
  "username": "demo-user@example.com",
  "password": "demo-password",
  "export_warehouse_code": "DEMO_WAREHOUSE",
  "timeout": 300
}
```

A full list of supported settings and capabilities is available by running:

```bash
target-extend --about
```

## Usage

### Input Schema

The target expects records from the `BuyOrders` stream with the following shape:

```json
{
  "id": "12345",
  "supplier_remoteId": "SUPPLIER-001",
  "transaction_date": "2026-05-01T10:00:00Z",
  "created_at": "2026-05-15T00:00:00Z",
  "externalid": "12345",
  "line_items": [
    {
      "product_remoteId": "PRODUCT-001",
      "quantity": 5
    },
    {
      "product_remoteId": "PRODUCT-002",
      "quantity": 10
    }
  ]
}
```

**Note**: In the Optiply export ETL, `created_at` is used in practice as the expected delivery date for the buy order.

### Running the Target

```bash
target-extend --config config.json < input.jsonl
```

Or with Meltano:

```yaml
loaders:
  - name: target-extend
    pip_url: target-extend
    config:
      api_url: "https://example.extend.local/RESTAPI"
      client: "DEMO_CLIENT"
      username: "demo-user@example.com"
      password: "demo-password"
      export_warehouse_code: "DEMO_WAREHOUSE"
```

## How It Works

### Authentication

The target builds an Extend Basic Authentication header from `username` and `password`:

```text
ExtendBasicAuthorization: Basic <base64 username:password>
```

### Purchase Order Mapping

The target creates this Extend payload:

```json
{
  "header": {
    "warehouse": "DEMO_WAREHOUSE",
    "supplier": {
      "supplierNumber": "SUPPLIER-001"
    },
    "reference": "12345",
    "requestedDeliveryDate": "2026-05-15T00:00:00Z"
  },
  "rows": [
    {
      "productNumber": "PRODUCT-001",
      "purchaseDataProductUnit": {
        "quantity": 5,
        "unit": "pcs"
      },
      "requestedDeliveryDate": "2026-05-15T00:00:00Z",
      "expectedDeliveryDate": "2026-05-15T00:00:00Z"
    }
  ]
}
```

Field mapping:

- `config.export_warehouse_code` -> `header.warehouse` when configured
- `supplier_remoteId` -> `header.supplier.supplierNumber`
- `id` -> `header.reference`
- `created_at` -> `header.requestedDeliveryDate`
- `created_at` -> each row `requestedDeliveryDate`
- `created_at` -> each row `expectedDeliveryDate`
- `line_items[].product_remoteId` -> `rows[].productNumber`
- `line_items[].quantity` -> `rows[].purchaseDataProductUnit.quantity`
- Row unit is hardcoded to `pcs`

The target does not send prices, currency, notes, supplier product numbers, shipments, or auto reception fields.

### Validation

The target fails the whole purchase order if:

- `supplier_remoteId` is missing
- `line_items` is missing, empty, invalid JSON, or not a list
- any line is missing `product_remoteId`
- any line has missing, non-numeric, or non-positive `quantity`

## Development

### Setup

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

### Testing

```bash
pytest
```

Or with Poetry:

```bash
poetry install
poetry run pytest
```

### CLI

```bash
poetry run target-extend --help
```

## License

Apache 2.0
