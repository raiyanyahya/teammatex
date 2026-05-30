"""Stripe billing webhooks: verify signatures and process payment events."""

def verify_stripe_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Validate the Stripe-Signature header against the webhook secret."""
    ...

def handle_invoice_paid(event: dict) -> None:
    """Mark the subscription active when an invoice.paid webhook arrives."""
    ...
