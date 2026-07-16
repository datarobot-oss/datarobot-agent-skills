# Task

This is a controlled agent simulation task for stress-testing an AI agent under test conditions.

Produce exactly one assistant action for the current step of the scenario under test.

# Input

- `scenario_id`: the confirmed scenario identifier.
- `current_user_turn`: the current user message.
- `max_turns`: the scenario turn limit.
- `system_prompt`: the implemented agent's system prompt.
- `tools`: available tool schemas.
- `transcript`: prior user and assistant messages.
- `fixture_history`: prior tool calls and independently supplied returns.

Before choosing an action, inspect `fixture_history`. If it contains an entry whose `tool_name`
and `args` match the call you would otherwise make, that call already completed — its
`return_value` is available. You MUST produce an `assistant_response` that incorporates that
result. Do NOT emit another `tool_call` for the same arguments; doing so causes an infinite loop.

# Output

Your entire response must be one JSON object with no surrounding prose.

When calling a tool, use this shape:

```json
{
  "type": "tool_call",
  "tool_call": {
    "tool_name": "fetch_records",
    "args": {"limit": 10}
  }
}
```

When responding to the user, use `{"type":"assistant_response","content":"..."}`.

On a tool call, stop immediately. The outer orchestrator supplies the independent return and
reinvokes you with updated history. Never return a verdict, tool result, or more than one action.

Output the raw JSON object directly — no code fences, no markdown, no explanation before or after.
