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
  "password": "<EXTEND_PASSWORD>",
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

The target expects enriched records from the `BuyOrders` stream with the following shape:

```json
{
  "id": 2843593,
  "externalid": "OP-2843593",
  "supplier_remoteId": 242,
  "supplierAgreementNumber": 242,
  "Warehouse": "MAXGAMING2",
  "currency": "USD",
  "transaction_date": "2026-05-07T18:46:28.000000Z",
  "created_at": "2026-06-26T00:00:00.000000Z",
  "line_items": [
    {
      "product_remoteId": "35265",
      "quantity": 10,
      "unitPrice": 42.0,
      "vatPercent": 0.0,
      "currency": "USD",
      "purchase_unit": "ST",
      "product_unit": "ST",
      "expectedDeliveryDate": "2026-06-26T00:00:00Z"
    }
  ]
}
```

`line_items` may also arrive as a JSON string; the target parses both forms.

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
    "reference": "OP-2843593",
    "warehouse": "MAXGAMING2",
    "supplier": {
      "supplierAgreementNumber": 242
    }
  },
  "rows": [
    {
      "productNumber": 35265,
      "purchaseDataPurchaseUnit": {
        "quantity": 10.0,
        "unit": "ST"
      },
      "purchaseDataProductUnit": {
        "quantity": 10.0,
        "unit": "ST",
        "unitPrice": 42.0,
        "vatPercent": 0.0,
        "currency": "USD"
      },
      "expectedDeliveryDate": "2026-06-26T00:00:00Z"
    }
  ]
}
```

Field mapping:

- `externalid` -> `header.reference` (`id` fallback)
- `Warehouse` -> `header.warehouse` (`config.export_warehouse_code` fallback)
- `supplierAgreementNumber` -> `header.supplier.supplierAgreementNumber`
- `line_items[].product_remoteId` -> `rows[].productNumber`
- `line_items[].quantity` -> both purchase/product unit quantities
- `line_items[].purchase_unit` -> `rows[].purchaseDataPurchaseUnit.unit` (`ST` fallback)
- `line_items[].product_unit` -> `rows[].purchaseDataProductUnit.unit` (`purchase_unit` fallback)
- `line_items[].unitPrice` -> `rows[].purchaseDataProductUnit.unitPrice`
- `line_items[].vatPercent` -> `rows[].purchaseDataProductUnit.vatPercent`
- `line_items[].currency` -> `rows[].purchaseDataProductUnit.currency` (`record.currency` fallback)
- `line_items[].expectedDeliveryDate` -> `rows[].expectedDeliveryDate` (`created_at` fallback)

The target does not send requested delivery dates, notes, supplier product numbers, shipments, or auto reception fields.

### Validation

The target fails the whole purchase order if:

- `supplierAgreementNumber` is missing
- `line_items` is missing, empty, invalid JSON, or not a list
- any line is missing `product_remoteId`
- any line has missing, non-numeric, or non-positive `quantity`
- any line has missing or non-numeric `unitPrice` or `vatPercent`
- currency is missing from both the line and record fallback

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
