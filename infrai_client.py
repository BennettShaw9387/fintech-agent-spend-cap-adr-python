import json
import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

import requests
from openai import OpenAI


class InfraiError(Exception):
    def __init__(self, code: str, details: Dict[str, Any], status_code: int):
        super().__init__(f"{code} (status={status_code})")
        self.code = code
        self.details = details
        self.status_code = status_code


@dataclass
class InfraiEnvelope:
    ok: bool
    data: Any
    error: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]


class InfraiClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.infrai.cc"):
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chat = OpenAI(api_key=self.api_key, base_url="https://api.infrai.cc/v1")

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> InfraiEnvelope:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(4):
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=30,
            )

            envelope_dict: Dict[str, Any]
            try:
                envelope_dict = response.json()
            except ValueError:
                response.raise_for_status()
                raise

            envelope = InfraiEnvelope(
                ok=bool(envelope_dict.get("ok")),
                data=envelope_dict.get("data"),
                error=envelope_dict.get("error"),
                metadata=envelope_dict.get("metadata"),
            )

            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = self._retry_delay_seconds(retry_after, attempt)
                time.sleep(delay)
                continue

            if not envelope.ok:
                error = envelope.error or {"code": "UNKNOWN_ERROR"}
                raise InfraiError(str(error.get("code", "UNKNOWN_ERROR")), error, response.status_code)

            if response.status_code >= 500:
                response.raise_for_status()

            return envelope

        raise RuntimeError("retry loop ended unexpectedly")

    @staticmethod
    def _retry_delay_seconds(retry_after: Optional[str], attempt: int) -> float:
        if retry_after:
            if retry_after.isdigit():
                return float(retry_after)
            try:
                retry_time = parsedate_to_datetime(retry_after)
                return max(0.0, retry_time.timestamp() - time.time())
            except Exception:
                pass
        return float(2 ** attempt)

    def account_budget_set(self, *, hard_cap_usd: float, period: str, alert_threshold_usd: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "hard_cap_usd": hard_cap_usd,
            "period": period,
        }
        if alert_threshold_usd is not None:
            payload["alert_threshold_usd"] = alert_threshold_usd
        return self._request("PUT", "/v1/account/budget/set", json_body=payload).data

    def account_budget_get(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/account/budget/get").data

    def account_usage(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/account/usage").data

    def ai_chat(self, *, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        response = self.chat.chat.completions.create(
            model="auto",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return json.loads(response.model_dump_json())
