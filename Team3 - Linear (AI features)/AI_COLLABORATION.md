# AI Collaboration Disclosure

No provider billing data was available to this coding session. Cost is therefore
`NOT_MEASURED`, not estimated.

| Tool / model | Use | Generated contribution | Human verification required | Estimated / measured cost |
| --- | --- | --- | --- | --- |
| OpenAI Codex (GPT-5 family) | Repository/specification analysis and implementation assistance | Read the complete Week3 dossier; generated implementation, conformance tests, evaluation, CI/container assets, and documentation. | Product owner/engineer must review code and claims. Executed pinned tests, lint, mypy, build, evaluation, and Compose validation. | NOT_MEASURED |
| Deterministic fixture provider inside Warrant | Offline development, tests, and reliable demo replay | Extracts synthetic descriptive features and produces a simulated evidence judgement through the same schemas as a real provider. | UI permanently labels fixture mode; results are excluded from live-model quality claims. | $0 runtime inference; no external call |
| OpenAI-compatible provider inside Warrant | Optional real extraction, criterion judging, and non-authorising prose | Genuine JSON-schema constrained calls when `AI_PROVIDER=openai` and credentials are configured. | Not called or measured. Run a live evaluation before reporting quality, latency, token use, or cost. | NOT_MEASURED |

## Verification performed in this session

- R&D source-of-truth reviewed across all 45 sections, including the interactive scenario data embedded in JavaScript.
- Required sequence: Ruff passed; mypy passed; 21 unit and 32 wider tests passed;
  evaluation passed; source distribution and wheel built.
- `make eval`: 120 policy cases plus six E2E/operational slices; 0 unsafe allows and
  100% safe E2E/operational rates.
- `docker compose config -q`: passed. Image execution was not verified because the
  local Docker daemon was not running.
- Healthy smoke flow: `REQUIRE_APPROVAL`, `DENY`, and `ALLOW` reference scenarios all produced intended verdicts.
- Complete smoke flow: approval with narrowed scope, warrant, evidence return, verification, and audit-chain check completed.
- Dependency versions resolved and pinned in `uv.lock`.
- Visual browser verification was attempted but the in-app browser connection could not initialise; no screenshot-level verification is claimed.

## Integrity boundary

AI assistance did not generate users, interviews, quotes, willingness-to-pay evidence, customer feedback, live-model scores, latency numbers, cost numbers, or compliance claims. No such evidence exists in this implementation.
