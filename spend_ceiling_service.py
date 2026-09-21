import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from infrai_client import InfraiClient


class PaymentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str
    customer_id: str
    merchant: str
    amount_usd: Decimal = Field(gt=Decimal("0"))
    estimated_ai_cost_usd: Decimal = Field(ge=Decimal("0"))
    summary_prompt: str


class SpendCapPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_hard_cap_usd: Decimal = Field(gt=Decimal("0"))
    monthly_alert_threshold_usd: Decimal = Field(gt=Decimal("0"))
    period: str


class AuditNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str
    customer_id: str
    action: str
    reason: str
    projected_monthly_spend_usd: Decimal
    signature: str


class SpendDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked: bool
    action: str
    reason: str
    projected_monthly_spend_usd: Decimal
    ai_summary: Optional[str] = None
    audit_notification: AuditNotification


@dataclass
class SpendCeilingService:
    infrai: InfraiClient
    signing_secret: str

    def apply_policy(self, event: PaymentEvent, policy: SpendCapPolicy) -> SpendDecision:
        budget = self.infrai.account_budget_get()
        hard_cap = self._extract_decimal(budget, "hard_cap_usd", policy.monthly_hard_cap_usd)
        if hard_cap != policy.monthly_hard_cap_usd:
            self.infrai.account_budget_set(
                hard_cap_usd=float(policy.monthly_hard_cap_usd),
                period=policy.period,
                alert_threshold_usd=float(policy.monthly_alert_threshold_usd),
            )
            hard_cap = policy.monthly_hard_cap_usd

        usage = self.infrai.account_usage()
        current_usage = self._extract_decimal(usage, "total_usd", Decimal("0"))
        projected = current_usage + event.estimated_ai_cost_usd

        if projected > hard_cap:
            notification = self._build_notification(
                event=event,
                action="hold_for_manual_review",
                reason="projected monthly spend crosses hard cap",
                projected=projected,
            )
            return SpendDecision(
                blocked=True,
                action="hold_for_manual_review",
                reason="projected monthly spend crosses hard cap",
                projected_monthly_spend_usd=projected,
                audit_notification=notification,
            )

        chat_response = self.infrai.ai_chat(
            system_prompt="Summarize payment risk for an internal fintech operations queue in one short paragraph.",
            user_prompt=event.summary_prompt,
        )
        ai_summary = self._extract_summary(chat_response)
        notification = self._build_notification(
            event=event,
            action="approve_and_run_ai",
            reason="projected monthly spend remains within hard cap",
            projected=projected,
        )
        return SpendDecision(
            blocked=False,
            action="approve_and_run_ai",
            reason="projected monthly spend remains within hard cap",
            projected_monthly_spend_usd=projected,
            ai_summary=ai_summary,
            audit_notification=notification,
        )

    def verify_notification(self, notification: AuditNotification) -> bool:
        unsigned_payload = {
            "payment_id": notification.payment_id,
            "customer_id": notification.customer_id,
            "action": notification.action,
            "reason": notification.reason,
            "projected_monthly_spend_usd": str(notification.projected_monthly_spend_usd),
        }
        expected = self._sign_payload(unsigned_payload)
        return hmac.compare_digest(expected, notification.signature)

    def _build_notification(self, *, event: PaymentEvent, action: str, reason: str, projected: Decimal) -> AuditNotification:
        payload = {
            "payment_id": event.payment_id,
            "customer_id": event.customer_id,
            "action": action,
            "reason": reason,
            "projected_monthly_spend_usd": str(projected),
        }
        signature = self._sign_payload(payload)
        return AuditNotification(signature=signature, **payload)

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self.signing_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    @staticmethod
    def _extract_decimal(source: Dict[str, Any], key: str, default: Decimal) -> Decimal:
        value = source.get(key, default)
        return Decimal(str(value))

    @staticmethod
    def _extract_summary(chat_response: Dict[str, Any]) -> str:
        choices = chat_response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return " ".join(part for part in text_parts if part)
        return str(content)
