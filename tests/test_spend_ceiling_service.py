from decimal import Decimal

from spend_ceiling_service import PaymentEvent, SpendCapPolicy, SpendCeilingService


class FakeInfraiClient:
    def __init__(self, *, budget_hard_cap_usd: str, usage_total_usd: str):
        self._budget = {"hard_cap_usd": budget_hard_cap_usd}
        self._usage = {"total_usd": usage_total_usd}
        self.budget_set_calls = []
        self.chat_calls = []

    def account_budget_get(self):
        return self._budget

    def account_budget_set(self, *, hard_cap_usd: float, period: str, alert_threshold_usd: float):
        self.budget_set_calls.append(
            {
                "hard_cap_usd": hard_cap_usd,
                "period": period,
                "alert_threshold_usd": alert_threshold_usd,
            }
        )
        self._budget = {"hard_cap_usd": str(hard_cap_usd)}
        return self._budget

    def account_usage(self):
        return self._usage

    def ai_chat(self, *, system_prompt: str, user_prompt: str):
        self.chat_calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return {
            "choices": [
                {
                    "message": {
                        "content": "Low operational risk for routine payroll disbursement."
                    }
                }
            ]
        }


def test_blocks_when_projected_spend_crosses_hard_cap():
    client = FakeInfraiClient(budget_hard_cap_usd="100.00", usage_total_usd="97.00")
    service = SpendCeilingService(infrai=client, signing_secret="test-secret")
    event = PaymentEvent(
        payment_id="pay_blocked",
        customer_id="cust_7",
        merchant="Northwind Treasury",
        amount_usd="800.00",
        estimated_ai_cost_usd="5.00",
        summary_prompt="Summarize risk.",
    )
    policy = SpendCapPolicy(
        monthly_hard_cap_usd="100.00",
        monthly_alert_threshold_usd="80.00",
        period="month",
    )

    decision = service.apply_policy(event, policy)

    assert decision.blocked is True
    assert decision.action == "hold_for_manual_review"
    assert decision.projected_monthly_spend_usd == Decimal("102.00")
    assert client.chat_calls == []
    assert service.verify_notification(decision.audit_notification) is True


def test_allows_ai_when_projected_spend_stays_within_hard_cap():
    client = FakeInfraiClient(budget_hard_cap_usd="100.00", usage_total_usd="70.00")
    service = SpendCeilingService(infrai=client, signing_secret="test-secret")
    event = PaymentEvent(
        payment_id="pay_allowed",
        customer_id="cust_8",
        merchant="ACME Payroll",
        amount_usd="1250.00",
        estimated_ai_cost_usd="7.50",
        summary_prompt="Summarize risk.",
    )
    policy = SpendCapPolicy(
        monthly_hard_cap_usd="100.00",
        monthly_alert_threshold_usd="80.00",
        period="month",
    )

    decision = service.apply_policy(event, policy)

    assert decision.blocked is False
    assert decision.action == "approve_and_run_ai"
    assert decision.projected_monthly_spend_usd == Decimal("77.50")
    assert decision.ai_summary == "Low operational risk for routine payroll disbursement."
    assert len(client.chat_calls) == 1
    assert service.verify_notification(decision.audit_notification) is True
