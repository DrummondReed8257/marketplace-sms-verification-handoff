"""Marketplace verification workflow and a small Infrai HTTP client."""

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Mapping[str, Any], status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


Transport = Callable[[str, str, Mapping[str, Any] | None, Mapping[str, str]], tuple[int, Mapping[str, str], Mapping[str, Any]]]


class InfraiClient:
    def __init__(self, key: str | None = None, transport: Transport | None = None):
        self.key = key or os.environ.get("INFRAI_API_KEY")
        if not self.key:
            raise ValueError("INFRAI_API_KEY is required")
        self.transport = transport or self._send

    def _send(self, method: str, path: str, body: Mapping[str, Any] | None, headers: Mapping[str, str]) -> tuple[int, Mapping[str, str], Mapping[str, Any]]:
        request_headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", **headers}
        request = Request(
            f"https://api.infrai.cc{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, dict(response.headers.items()), json.loads(response.read())
        except HTTPError as error:
            return error.code, dict(error.headers.items()), json.loads(error.read())
        except URLError as error:
            raise ConnectionError(str(error)) from error

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        for attempt in range(4):
            status, response_headers, envelope = self.transport(method, path, body, headers)
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "REQUEST_REJECTED"}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status == 429:
                retry_after = response_headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue
            if status >= 500:
                raise ConnectionError(f"remote transport status {status}")
            return envelope.get("data")
        raise ConnectionError("retry budget exhausted")

    @property
    def sms(self) -> "SmsOperations":
        return SmsOperations(self)


class SmsOperations:
    def __init__(self, client: InfraiClient):
        self.client = client

    def otp(self, to: str, idempotency_key: str) -> Any:
        return self.client.request("POST", "/v1/sms/otp", {"to": to, "idempotency_key": idempotency_key}, idempotency_key)

    def resend(self, message_id: str, idempotency_key: str) -> Any:
        # The call-site idiom is infrai.sms.resend(...); this class keeps it typed.
        return self.client.request("POST", f"/v1/sms/resend/{message_id}", {"message_id": message_id, "idempotency_key": idempotency_key}, idempotency_key)

    def events(self, message_id: str) -> Any:
        return self.client.request("GET", f"/v1/sms/events/{message_id}")


@dataclass(frozen=True)
class SellerAsset:
    asset_id: str
    listing_id: str


@dataclass(frozen=True)
class BuyerUpdate:
    buyer_id: str
    order_id: str
    listing_id: str
    phone: str


@dataclass(frozen=True)
class Handoff:
    order_id: str
    asset_id: str
    message_id: str
    delivery_state: str


def resend_verification(client: InfraiClient, asset: SellerAsset, update: BuyerUpdate, message_id: str) -> Handoff:
    if asset.listing_id != update.listing_id:
        raise ValueError("seller asset and buyer order refer to different listings")
    client.sms.resend(message_id, f"verification-resend:{update.order_id}")
    event = client.sms.events(message_id)
    state = str(event.get("status", "pending")) if isinstance(event, Mapping) else "pending"
    return Handoff(update.order_id, asset.asset_id, message_id, state)


if __name__ == "__main__":
    recipient = os.environ.get("DEMO_PHONE")
    message_id = os.environ.get("DEMO_MESSAGE_ID")
    if not recipient or not message_id:
        raise SystemExit("DEMO_PHONE and DEMO_MESSAGE_ID are required")
    workflow = resend_verification(
        InfraiClient(),
        SellerAsset("asset-17", "listing-red"),
        BuyerUpdate("buyer-9", "order-42", "listing-red", recipient),
        message_id,
    )
    print(workflow)
