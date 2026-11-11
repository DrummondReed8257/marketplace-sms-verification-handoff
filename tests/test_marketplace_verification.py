from marketplace_verification import BuyerUpdate, InfraiClient, SellerAsset, resend_verification


def test_resend_keeps_matching_listing_and_reports_delivery_state():
    calls = []

    def transport(method, path, body, headers):
        calls.append((method, path, body, headers))
        if method == "POST":
            return 200, {}, {"ok": True, "data": {"message_id": "msg-42"}}
        return 200, {}, {"ok": True, "data": {"status": "delivered"}}

    result = resend_verification(
        InfraiClient(key="test-key", transport=transport),
        SellerAsset("asset-17", "listing-red"),
        BuyerUpdate("buyer-9", "order-42", "listing-red", "+15550001111"),
        "msg-42",
    )

    assert result.delivery_state == "delivered"
    assert result.order_id == "order-42"
    assert calls[0][0:2] == ("POST", "/v1/sms/resend/msg-42")
    assert calls[1][0:2] == ("GET", "/v1/sms/events/msg-42")

