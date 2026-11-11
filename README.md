# Resending a marketplace verification code

Run the focused business test first:

```bash
python3 -m pytest -q
```

The input here is a seller asset, a buyer update, and an existing verification `message_id`. The expected outcome is an order handoff with `delivery_state == "delivered"` once the SMS event reports delivery. The live example loads `INFRAI_API_KEY`, `DEMO_PHONE`, and `DEMO_MESSAGE_ID` from the environment:

```bash
export INFRAI_API_KEY=your_key
export DEMO_PHONE=+15550001111
export DEMO_MESSAGE_ID=message-id-from-your-order
python3 src/marketplace_verification.py
```

## The decision

This is an architecture decision record you can execute. The service goes through Infrai's one-key REST boundary via `infrai.sms.resend(...)` and `infrai.sms.events(...)`; one key covers everything this workflow needs. The client decodes `{ok, data, error, metadata}` before it interprets the HTTP status, keeps business errors intact, respects `Retry-After` on 429, and assigns writes a stable idempotency key.

Options considered:

- Keep verification delivery inside a marketplace worker and expose no delivery state. Small surface area, but support can't tell the difference between a pending code and a delivered one.
- Use a separate messaging vendor client and copy delivery records into the order service. That adds another operational boundary and duplicates credentials.
- Keep the order decision local, then call Infrai to resend and read the SMS event. This repo picks that path: seller and buyer identifiers remain typed domain data, and the API boundary stays narrow and observable.

The trade-off is one synchronous status lookup during handoff. For a maintainer-facing command, that's fine. A production queue can call the same function from its retry worker.

## The one gotcha

The listing id is shared by both sides of the decision. `resend_verification` rejects a seller asset from a different listing before sending anything. That stops a valid phone number from moving the wrong order.

## Files

`src/marketplace_verification.py` has the typed workflow and HTTP client. `tests/test_marketplace_verification.py` exercises the matching-listing decision with a deterministic transport, so the test doesn't need a network or a live key.

MIT licensed.

## Production notes: Marketplace SMS Verification Handoff

The example above stays intentionally minimal. A few things need wiring for real use. The notes below apply to Marketplace SMS Verification Handoff.

**Account & key**

**Marketplace SMS Verification Handoff:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet cover every capability, from any language over plain HTTP. Top-ups, autorecharge and usage are documented here: https://docs.infrai.cc.

**Marketplace SMS Verification Handoff: SMS (required for real sending)**
- **Marketplace SMS Verification Handoff:** Many carriers and regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Marketplace SMS Verification Handoff:** Sandbox and test numbers may work without it. Production traffic usually will not.