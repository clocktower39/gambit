# eBay Sandbox connector — runbook (Phase 2)

**Verdict:** eBay Sandbox is the right "real marketplace" integration. It's the only
major marketplace with a free sandbox + programmatic listing + a real buyer↔seller
negotiation loop you can drive entirely by API. Budget **~1–2 hrs** for keys + OAuth +
a first successful listing, then the negotiation loop is small.

## The one decisive call
**Build BOTH listing and negotiation on the legacy Trading API (XML).** The modern REST
"Negotiation API" is *seller-initiated only* (offer-to-watchers) and is half-broken in
Sandbox. The buyer-initiated **Best Offer** haggle loop you want lives only in Trading.

## Call sequence
1. **List with Best Offer on** — Trading `AddFixedPriceItem` (single call; set
   `BestOfferDetails.BestOfferEnabled=true`, plus optional `BestOfferAutoAcceptPrice` /
   `MinimumBestOfferPrice` under `ListingDetails`). Avoids the REST Inventory API's
   business-policy + location setup tax.
2. **Buyer makes an offer** — Trading `PlaceOffer` (`Action=Offer`, optional free-text
   `BuyerMessage`). In a demo this can also be done by hand at sandbox.ebay.com.
3. **Seller reads offers** — Trading `GetBestOffers` → `BestOfferID`, price, `BuyerMessage`.
4. **Seller responds** — Trading `RespondToBestOffer` (`Action=Accept|Decline|Counter`;
   for a counter set `CounterOfferPrice` + `CounterOfferQuantity` + optional `SellerResponse`).
5. **Buyer accepts the counter** — `PlaceOffer` again with the `BestOfferID`, `Action=Accept`.
   Offers expire in 48h; a new counter auto-declines prior offers.

Free-text Q&A (separate from numeric offers): `GetMemberMessages` / `AddMemberMessageRTQ`
(~75/60s rate limit). Our agent can do both numeric counters and free-text replies.

## Auth (do this first)
- One developer account → per environment: **App ID (client_id), Cert ID (client_secret),
  Dev ID**, plus a **RuName** redirect identifier. Sandbox keysets generate instantly, no approval.
- All Sell/Best-Offer calls need a **user access token** (authorization_code grant), NOT an
  app token:
  1. Browser → `https://auth.sandbox.ebay.com/oauth2/authorize?client_id=...&redirect_uri=<RuName>&response_type=code&scope=...&prompt=login`
  2. Log in as a **sandbox seller test user**, consent → auth code (5-min life)
  3. `POST https://api.sandbox.ebay.com/identity/v1/oauth2/token` (grant_type=authorization_code)
     → user token (~2h) + **refresh token (~18 mo — store it** so you don't re-consent all day).
- Trading API accepts the OAuth token via header `X-EBAY-API-IAF-TOKEN`.
- Create test users in the Dev Portal: *User Access Tokens → Register a new Sandbox user*.
  You need **two** (seller + buyer) — eBay forbids buying your own listing, enforced in Sandbox too.

## Top 3 gotchas
1. **Trading-API-only negotiation.** Don't default to the REST stack — you'll waste hours
   discovering it can't receive/counter a buyer offer.
2. **OAuth + two-user friction.** 5-min auth codes, browser login per test user. Script a
   small OAuth helper early; persist refresh tokens.
3. **Sandbox flakiness + listing field landmines.** Get ONE listing to publish in the first
   1–2 hrs (category ID, ConditionID, shipping/return blocks are finicky). Keep a manual
   fallback: place the buyer offer via sandbox.ebay.com UI so a flaky `PlaceOffer` can't kill
   the live demo.

## Backup
**Reverb** has a full listing API + a real offers/negotiation API (accept/counter/reject) and
even an official Offer Bot — but **no sandbox** (live marketplace only). Use only if we accept
running against production. Etsy/Shopify have listing APIs but **no buyer-seller negotiation**.
Mercari/OfferUp/Craigslist: no usable API, automation prohibited — do not attempt.

## Minimal Python (Trading over requests)
```python
import requests, re
SANDBOX = "https://api.sandbox.ebay.com/ws/api.dll"

def trading_call(call_name, xml_body, token):
    headers = {
        "X-EBAY-API-SITEID": "0",                  # US
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1193",
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-IAF-TOKEN": token,             # OAuth user token
        "Content-Type": "text/xml",
    }
    r = requests.post(SANDBOX, data=xml_body.encode(), headers=headers, timeout=30)
    r.raise_for_status()
    return r.text
# AddFixedPriceItem (BestOfferDetails.BestOfferEnabled=true) -> ItemID
# GetBestOffers(ItemID) -> BestOfferID, price, BuyerMessage
# RespondToBestOffer(ItemID, BestOfferID, Action=Counter, CounterOfferPrice=...)
```

**Maps to our code:** implement `connectors/ebay.py` against the `connectors/base.py` interface
(`post_listing`, `get_offers`, `respond_offer`). The negotiation *brain* stays the same
`SellerAgent` + `Strategy`; the connector just translates its decisions into Trading API calls.
