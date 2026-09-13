# Wave 2 — OpenHands Condenser

- Actual implementation lives in `OpenHands/software-agent-sdk@da6f546…`, not the app repository.
- `Condensation` records forgotten event IDs, summary, insertion offset and LLM response ID. Derived View filters IDs while raw history remains; fork/replay and cache rollback tests are strong.
- Missing provenance: model/version, prompt/input hashes, token counts and policy version. Agent Lab should extend the record rather than copy it verbatim.
- Sources: [Condensation model/apply](https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/openhands-sdk/openhands/sdk/event/condenser.py#L11-L96), [fork/replay tests](https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/tests/sdk/conversation/local/test_conversation_tree.py#L224-L290), [cache rollback](https://github.com/OpenHands/software-agent-sdk/blob/da6f5463be9364e55db40435017549340c73bdea/tests/sdk/conversation/test_state_view_cache.py#L219-L231).

## EXPAND
- LEAD: nested condensation/tool-call pairing tests — WHY: avoid broken replay — ANGLE: future implementation test plan, no further repo needed.

