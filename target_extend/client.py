"""REST client for Extend Commerce API."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import backoff
import requests
from singer_sdk.exceptions import RetriableAPIError

from target_extend.auth import ExtendAuth


LOGGER = logging.getLogger(__name__)


class ExtendClient:
    """Small REST client for Extend Commerce purchase orders."""

    RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize client from target config."""
        self.config = config
        self.auth = ExtendAuth(config)
        self.timeout = config.get("timeout", 300)

    @property
    def base_url(self) -> str:
        """Return configured Extend REST API base URL."""
        return self.config.get("api_url", "https://developer.lxir.se/RESTAPI").rstrip("/")

    @property
    def client(self) -> str:
        """Return Extend client path segment."""
        return self.config["client"]

    def purchase_orders_endpoint(self) -> str:
        """Return the create purchase order endpoint URL."""
        return f"{self.base_url}/v1_0/{self.client}/PurchaseOrders"

    @backoff.on_exception(
        backoff.expo,
        (RetriableAPIError, requests.exceptions.ReadTimeout, requests.exceptions.Timeout),
        max_tries=5,
        factor=2,
    )
    def post_purchase_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a purchase order in Extend and return parsed JSON response."""
        LOGGER.info(
            "REQUEST - endpoint: %s, request_body: %s",
            f"/v1_0/{self.client}/PurchaseOrders",
            payload,
        )
        response = requests.post(
            self.purchase_orders_endpoint(),
            headers=self.auth.headers,
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code in self.RETRIABLE_STATUS_CODES:
            raise RetriableAPIError(
                f"Retriable Extend API error {response.status_code}: {response.text[:1000]}",
                response=response,
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"Extend API error {response.status_code}: {response.text[:2000]}",
                response=response,
            ) from exc

        if not response.text:
            return {}

        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw_response": response.text}


def extract_purchase_number(response: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract Extend purchaseNumber from a create purchase order response."""
    if not isinstance(response, dict):
        return None

    header = response.get("header")
    if isinstance(header, dict) and header.get("purchaseNumber"):
        return str(header["purchaseNumber"])

    # Be tolerant of wrappers without hiding API failures.
    for value in response.values():
        if isinstance(value, dict):
            found = extract_purchase_number(value)
            if found:
                return found

    return None
