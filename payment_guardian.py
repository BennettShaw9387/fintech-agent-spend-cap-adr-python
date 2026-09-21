import json
import os

from infrai_client import InfraiClient
from spend_ceiling_service import PaymentEvent, SpendCapPolicy, SpendCeilingService


def main() -> None:
    signing_secret = os.environ.get("AUDIT_SIGNING_SECRET", "local-demo-secret")
    infrai = InfraiClient()
    service = SpendCeilingService(infrai=infrai, signing_secret=signing_secret)

    event = PaymentEvent(
        payment_id="pay_1001",
        customer_id="cust_42",
        merchant="ACME Payroll",
        amount_usd="1250.00",
        estimated_ai_cost_usd="7.50",
        summary_prompt="Review payment pay_1001 for customer cust_42 to merchant ACME Payroll amount 1250.00 USD and summarize operational risk.",
    )
    policy = SpendCapPolicy(
        monthly_hard_cap_usd="100.00",
        monthly_alert_threshold_usd="80.00",
        period="month",
    )

    decision = service.apply_policy(event, policy)
    verified = service.verify_notification(decision.audit_notification)

    print(
        json.dumps(
            {
                "blocked": decision.blocked,
                "action": decision.action,
                "reason": decision.reason,
                "projected_monthly_spend_usd": str(decision.projected_monthly_spend_usd),
                "ai_summary": decision.ai_summary,
                "audit_notification_verified": verified,
                "audit_notification": decision.audit_notification.model_dump(mode="json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
