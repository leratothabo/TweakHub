"""
apps/api/scripts/setup_paystack_plans.py

One-time setup for the recurring-subscription feature (services/
subscription_service.py): creates a Paystack Plan for each entry in
SUBSCRIPTION_PLANS via POST /plan, if one by that name doesn't already
exist (checked via GET /plan first, so this is safe to re-run). Prints
the resulting plan_code values with the exact .env lines to set.

This is meant to be run once, by hand, against a real Paystack account --
not part of app startup, and not something the test suite calls. Payment
Plans are billing configuration, the same category of one-time step as
pointing DPO_COMPANY_TOKEN at a real DPO merchant account; nothing in
this codebase should call Paystack's Plan-creation endpoint on every
request.

Usage:
    cd apps/api && source .venv/bin/activate
    export PAYSTACK_SECRET_KEY=sk_...          # or set it in .env
    python -m scripts.setup_paystack_plans

Then copy the printed PAYSTACK_PLAN_CODE_* lines into .env (see
.env.example for where they go) and restart the API.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tweakhub.setup_paystack_plans")


def _find_existing_plan(base_url: str, headers: dict, name: str) -> str | None:
    """GET /plan and look for one whose name matches exactly -- Paystack
    has no "get plan by name" endpoint, so this pages through the list.
    Returns the plan_code if found, else None."""
    page = 1
    while True:
        response = httpx.get(f"{base_url}/plan", headers=headers, params={"page": page, "perPage": 50}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if not body.get("status"):
            raise RuntimeError(f"Paystack GET /plan failed: {body.get('message')}")

        for plan in body.get("data") or []:
            if plan.get("name") == name:
                return plan.get("plan_code")

        meta = body.get("meta") or {}
        total_pages = ((meta.get("total") or 0) + 49) // 50 if meta.get("perPage") else 1
        if page >= total_pages:
            return None
        page += 1


def _create_plan(base_url: str, headers: dict, name: str, amount_kobo: int, currency: str) -> str:
    response = httpx.post(
        f"{base_url}/plan",
        json={"name": name, "amount": amount_kobo, "interval": "monthly", "currency": currency},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("status"):
        raise RuntimeError(f"Paystack POST /plan failed for '{name}': {body.get('message')}")
    plan_code = (body.get("data") or {}).get("plan_code")
    if not plan_code:
        raise RuntimeError(f"Paystack POST /plan response for '{name}' missing plan_code")
    return plan_code


def setup_paystack_plans(currency: str = "USD") -> dict[str, str]:
    """Returns {plan_key: plan_code} for every entry in SUBSCRIPTION_PLANS
    -- reusing an existing Paystack Plan by name where one is found,
    creating any missing one. Importable so a test can exercise the
    idempotency logic against a monkeypatched httpx without touching a
    real Paystack account."""
    from config import get_settings
    from services.subscription_service import SUBSCRIPTION_PLANS

    settings = get_settings()
    if not settings.paystack_secret_key:
        raise RuntimeError("PAYSTACK_SECRET_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json",
    }
    base_url = settings.paystack_base_url

    plan_codes: dict[str, str] = {}
    for plan_key, plan in SUBSCRIPTION_PLANS.items():
        plan_name = f"TweakHub {plan_key.capitalize()} (monthly)"
        amount_kobo = round(plan["price_usd"] * 100)

        existing = _find_existing_plan(base_url, headers, plan_name)
        if existing:
            logger.info("Plan '%s' already exists: %s", plan_name, existing)
            plan_codes[plan_key] = existing
            continue

        code = _create_plan(base_url, headers, plan_name, amount_kobo, currency)
        logger.info("Created plan '%s': %s", plan_name, code)
        plan_codes[plan_key] = code

    return plan_codes


def main() -> None:
    plan_codes = setup_paystack_plans()
    print("\nSet these in .env (see .env.example):\n")
    for plan_key, code in plan_codes.items():
        print(f"PAYSTACK_PLAN_CODE_{plan_key.upper()}={code}")
    print()


if __name__ == "__main__":
    main()
