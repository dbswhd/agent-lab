# Wave 1 — multi-agent frameworks

- `microsoft/agent-framework@74a1440…`: strongest current framework reference; executable workflow/orchestration, termination, tool approval, checkpoints, OTel.
- `AG2@4c27160…`: explicit human input/termination/checkpoint semantics but API churn.
- CrewAI/AgentScope provide useful task/message patterns; PydanticAI provides typed deferred approvals but no native group scheduler.
- AutoGen is explicitly maintenance mode and points new users to Agent Framework.
- Sources: [Agent Framework checkpoints](https://github.com/microsoft/agent-framework/blob/74a144085a5fd05921b473001528f3ae0725b76a/python/packages/core/agent_framework/_workflows/_checkpoint.py), [AG2 checkpoint args](https://github.com/ag2ai/ag2/blob/4c27160d4aae04b35e7d4147393c8f18736e9efa/ag2/agent.py#L771-L810), [PydanticAI graph](https://github.com/pydantic/pydantic-ai/blob/916fc83e8929470679db5ac1b3065bda5d5f4253/pydantic_ai/_agent_graph.py), [AutoGen maintenance notice](https://github.com/microsoft/autogen/blob/027ecf0a379bcc1d09956d46d12d44a3ad9cee14/README.md#L180-L191).

## EXPAND
- LEAD: Agent Framework approval/checkpoint tests — WHY: validate production semantics beyond docs — ANGLE: clone and inspect.

