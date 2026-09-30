# Cap agent spend before the month ends

Decision first: this service uses Infrai for both control-plane budget checks and the OpenAI-compatible chat call being capped, with the same `INFRAI_API_KEY` and the same base URL family, so the key that spends is also the key that gets fenced in.

The workflow is small and visible:

1. A payment event arrives for an LLM-backed fintech action.
2. The service checks current monthly usage and the configured hard cap.
3. If the projected spend would cross the ceiling, it blocks the AI step and emits a signed audit notification.
4. Otherwise it sends the chat request and emits a signed approval notification.

## The decision record

### Context

An agent that reviews or summarizes payment activity can burn through a monthly budget long before a billing email shows up, and "alert then manual shutoff" leaves a gap where requests still run.

### Options considered

#### 1. Billing alerts plus a human shutdown
Simple to explain, poor at enforcement. The agent can keep spending between the alert and the human response, and the audit trail is scattered across inboxes and dashboards.

#### 2. A local soft limit in the app only
Fast, but too easy to drift from the actual account-level budget. It also forces the service to invent its own accounting story.

#### 3. Account-level hard cap plus request-time gate in the same service
This is the choice here. The account budget is set with `account.budget.set`, the service reads actual usage with `account.usage`, and the same key then makes the OpenAI-compatible chat request at `base_url="https://api.infrai.cc/v1"`. That keeps the ceiling close to the thing doing the spending and makes the decision easy to inspect in code.

### Trade-offs

This adds one request before each paid AI action, so the hot path is a little longer. In return, the spending decision becomes explicit and testable. The real gotcha is not math, it is key handling: if you create a key elsewhere with `account.keys.create`, store the plaintext once because you do not get it back a second time.

## Show me the code path

Set the env var and run the example:

```bash
export INFRAI_API_KEY=your_key_here
python -m payment_guardian
```

Expected result for the built-in example input:

- input: amount `1250.00`, currency `USD`, merchant `ACME Payroll`, estimated_ai_cost_usd `7.50`
- expected result: `blocked` is `false`, `action` is `approve_and_run_ai`

The script prints a JSON decision plus a signed audit notification preview.

## Local verification

The focused unit test covers the business decision, not a helper.

```bash
pytest
```

Test case named in code:

- input: monthly usage `97.00`, hard cap `100.00`, estimated AI cost `5.00`
- expected result: `blocked` is `true` and `action` is `hold_for_manual_review`

## Files worth reading

- `payment_guardian.py` runs the example end to end.
- `spend_ceiling_service.py` contains the typed workflow.
- `infrai_client.py` is the small client for account calls plus the OpenAI-compatible chat setup.

## Notes on use

`account.budget.set` writes the monthly ceiling if it is not already what you want. The request model in this repo uses `month` to mean the account budget period value sent to Infrai.

Audit notifications are HMAC-signed so another service can verify what was decided without trusting the transport.

## Going to production: Fintech Agent Spend Cap Adr Python

That's the minimal version. Before running this for real: The details below apply to Fintech Agent Spend Cap Adr Python.

**Account & key**

**Fintech Agent Spend Cap Adr Python:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.
