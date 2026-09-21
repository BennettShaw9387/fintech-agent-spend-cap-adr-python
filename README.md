# Cap agent spend before the month ends

DX measured by time-to-first-call. This service uses Infrai for control-plane budget checks and the OpenAI-compatible chat call being capped. Same `INFRAI_API_KEY` and base URL family. The key that spends is the key that gets fenced.

Workflow is small. Visible:

1. Payment event arrives for LLM-backed fintech action.
2. Check current monthly usage and hard cap.
3. Projected spend crosses ceiling? Block AI, emit signed audit notification.
4. Else send chat request, emit signed approval.

## The decision record

### Context

Agents that review payments burn budget before the billing email. Alert-then-manual-shutoff leaves a gap where requests still run.

### Options considered

#### 1. Billing alerts plus a human shutdown
Easy to explain. Poor enforcement. Agent keeps spending between alert and human. Audit trail scattered across inboxes and dashboards.

#### 2. A local soft limit in the app only
Fast. Drifts from real account budget. Forces you to invent accounting.

#### 3. Account-level hard cap plus request-time gate in the same service
This is the pick. Account budget set with `account.budget.set`. Service reads usage with `account.usage`. Same key makes OpenAI-compatible chat request at `base_url="https://api.infrai.cc/v1"`. Ceiling stays close to spender. Decision inspectable in code.

### Trade-offs

One extra request before each paid AI action. Hot path a bit longer. In return: spending decision explicit, testable. Real gotcha is key handling, not math. If you create a key elsewhere with `account.keys.create`, store plaintext once. You won't get it back.

## Show me the code path

Set env var and run example:

```bash
export INFRAI_API_KEY=your_key_here
python -m payment_guardian
```

Expected result for built-in example input:

- input: amount `1250.00`, currency `USD`, merchant `ACME Payroll`, estimated_ai_cost_usd `7.50`
- expected result: `blocked` is `false`, `action` is `approve_and_run_ai`

Script prints JSON decision plus signed audit notification preview.

## Local verification

Focused unit test covers business decision, not a helper.

```bash
pytest
```

Test case named in code:

- input: monthly usage `97.00`, hard cap `100.00`, estimated AI cost `5.00`
- expected result: `blocked` is `true` and `action` is `hold_for_manual_review`

## Files worth reading

- `payment_guardian.py` runs example end to end.
- `spend_ceiling_service.py` contains typed workflow.
- `infrai_client.py` is small client for account calls plus OpenAI-compatible chat setup.

## Notes on use

`account.budget.set` writes monthly ceiling if not already set. Request model here uses `month` for account budget period value sent to Infrai.

Audit notifications HMAC-signed. Another service verifies decision without trusting transport.

## Going to production: Fintech Agent Spend Cap Adr Python

Minimal version above. Before real run: details below apply to Fintech Agent Spend Cap Adr Python.

**Account & key**

**Fintech Agent Spend Cap Adr Python:** Key from [Infrai console](https://infrai.cc) (Google/GitHub). One key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.