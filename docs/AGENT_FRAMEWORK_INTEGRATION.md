# Agent Framework Integration (LangGraph, PydanticAI, etc.)

This repo’s “skills” are **instruction bundles** (`dr-*/SKILL.md`) plus optional helper scripts (`dr-*/scripts/`).  
Some agent runtimes (Claude Code, Codex, Gemini CLI) can auto-load these; **most programmatic agent frameworks (LangGraph, PydanticAI, LangChain, etc.) require you to load them yourself**.

## The core pattern (framework-agnostic)

- **Load** the relevant `SKILL.md` text (and optionally any scripts/templates in that folder)
- **Route** user requests to one or more skills (keyword routing or LLM router)
- **Inject** the skill text into your system prompt (or your “instructions” field)
- **Execute**:
  - Option A: run our helper scripts (simple + stable)
  - Option B: have the LLM generate Python that uses the DataRobot SDK directly (more flexible; needs sandboxing)

### Minimal “skill loader”

```python
from pathlib import Path
import frontmatter

def load_skill(skill_dir: str) -> dict:
    """Return {name, description, content} from dr-*/SKILL.md."""
    skill_path = Path(skill_dir) / "SKILL.md"
    post = frontmatter.load(skill_path)
    return {
        "name": post.metadata.get("name", skill_dir),
        "description": post.metadata.get("description", ""),
        "content": post.content,
    }
```

### Optional: run helper scripts as “tools”

```python
import subprocess
import json
import os

def run_skill_script(script_path: str, *args: str) -> dict:
    """Run a repo script and parse JSON output (if any)."""
    proc = subprocess.run(
        ["python3", script_path, *args],
        capture_output=True,
        text=True,
        env=os.environ,  # expects DATAROBOT_API_TOKEN / DATAROBOT_ENDPOINT
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}
    # Most helper scripts print JSON. If not JSON, return raw text.
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"output": proc.stdout}
```

## LangGraph pattern (load skill → prompt → SDK/script execution)

LangGraph’s API is version-sensitive, so treat this as a **pattern**, not a pinned snippet.

- **Router node**: chooses a skill (`dr-predictions`, `dr-model-training`, …)
- **Planner node**: LLM uses skill guidance to decide steps (often “call helper script”)
- **Executor node**: runs helper scripts / SDK code

Key takeaway: LangGraph does **not** auto-load `SKILL.md`. Your router/planner nodes must read them.

For an SDK-verified workflow, see `examples/sdk_smoke_predictions.py`.

### LangGraph: minimal “router + tool execution” sketch

```python
# NOTE: This is a pattern sketch; adapt imports/APIs to your LangGraph version.

from typing import TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
import json

def load_skill_catalog() -> list[dict]:
    """
    Build a lightweight catalog the router LLM can see.
    Only include name/description (not full SKILL.md) to keep routing fast.
    """
    # Example: load from all dr-*/SKILL.md using frontmatter in load_skill(...)
    # Return list of: {"name": "...", "description": "...", "dir": "dr-predictions"}
    raise NotImplementedError

class State(TypedDict):
    messages: List[BaseMessage]
    skill_name: str
    skill_text: str

def route_skill_with_llm(state: State, router_llm) -> State:
    """
    Let an LLM choose the best skill(s) given the available catalog.

    Return a single chosen skill for simplicity; you can extend to multiple skills.
    """
    user_text = state["messages"][-1].content
    catalog = load_skill_catalog()

    router_prompt = f"""
You are a router. Choose the single best DataRobot skill for the user request.

User request:
{user_text}

Available skills (name + description):
{json.dumps(catalog, indent=2)}

Return ONLY JSON:
{{"skill_name": "<name>", "confidence": 0-1, "why": "<short>"}}
"""

    resp = router_llm.invoke([SystemMessage(content=router_prompt)])
    # Parse JSON (defensively)
    choice = json.loads(resp.content)
    chosen = choice["skill_name"]

    # Validate chosen skill exists in catalog
    by_name = {s["name"]: s for s in catalog}
    if chosen not in by_name:
        # fallback: default to predictions
        chosen = "dr-predictions"

    skill_dir = by_name.get(chosen, {"dir": "dr-predictions"})["dir"]
    skill = load_skill(skill_dir)
    state["skill_name"] = skill["name"]
    state["skill_text"] = skill["content"]
    return state

def tool_get_deployment_features(deployment_id: str) -> dict:
    return run_skill_script("dr-predictions/scripts/get_deployment_features.py", deployment_id)

def tool_make_prediction(deployment_id: str, data_json: str) -> dict:
    return run_skill_script("dr-predictions/scripts/make_prediction.py", deployment_id, data_json)

def planner_node(state: State) -> State:
    # Typical pattern: inject SKILL.md into system prompt.
    system = SystemMessage(content=f"Use this skill guidance:\n\n{state['skill_text']}")
    state["messages"] = [system] + state["messages"]
    # Then call your model / tools in whatever LangGraph pattern you use (ReAct, function calling, etc.)
    return state
```

## PydanticAI pattern (skills as system prompt + optional tool wrapper)

PydanticAI (and similar “typed agent” frameworks) usually give you:

- a **system prompt / instructions** field
- a way to register **tools/functions**

Use the same core pattern:

1. Load `SKILL.md` and place it in the agent’s system prompt
2. Register “helper script runners” as tools (predict/template/etc.)
3. Ask the model to either call tools or produce SDK code

### Tool-wrapper approach (recommended)

Define a tool that calls our stable helper scripts, e.g.:

```python
def get_deployment_features(deployment_id: str) -> dict:
    return run_skill_script(
        "dr-predictions/scripts/get_deployment_features.py",
        deployment_id,
    )
```

Then add that tool to your agent framework’s tool registry.

### PydanticAI: minimal “skills as instructions + tool wrappers” sketch

```python
# NOTE: This is a pattern sketch; adapt to your PydanticAI version.

skill = load_skill("dr-predictions")
instructions = f"""
You are a DataRobot assistant.
Follow this skill guidance:

{skill['content']}
"""

# Example tools (wrapping repo scripts)
def get_deployment_features(deployment_id: str) -> dict:
    return run_skill_script("dr-predictions/scripts/get_deployment_features.py", deployment_id)

def generate_template(deployment_id: str, n_rows: int = 10, out_path: str = "template.csv") -> dict:
    # this script prints text; wrapper returns {"output": "..."} unless it prints JSON
    return run_skill_script(
        "dr-predictions/scripts/generate_prediction_data_template.py",
        deployment_id,
        str(n_rows),
        out_path,
    )

def score_one_row(deployment_id: str, data_json: str) -> dict:
    return run_skill_script("dr-predictions/scripts/make_prediction.py", deployment_id, data_json)

# Then, register these functions as tools in your PydanticAI Agent
# and set `instructions`/system prompt to include the SKILL.md content.
```

## CrewAI pattern (skills as backstory/goal + tools)

CrewAI is also version-sensitive; conceptually you:

1. Load the appropriate `SKILL.md`
2. Put it into the agent’s **backstory**/**goal**/**system prompt**
3. Expose helper scripts as **tools**
4. Create tasks that reference the skill explicitly

### CrewAI: minimal “agent + tools + task” sketch

```python
# NOTE: This is a pattern sketch; adapt imports to your CrewAI version.

skill = load_skill("dr-predictions")

def get_deployment_features(deployment_id: str) -> dict:
    return run_skill_script("dr-predictions/scripts/get_deployment_features.py", deployment_id)

def make_prediction(deployment_id: str, data_json: str) -> dict:
    return run_skill_script("dr-predictions/scripts/make_prediction.py", deployment_id, data_json)

# agent = Agent(
#   role="DataRobot Prediction Assistant",
#   goal="Help users score data using DataRobot deployments.",
#   backstory=f"Use this skill guidance:\n\n{skill['content']}",
#   tools=[get_deployment_features, make_prediction],
# )
#
# task = Task(
#   description="Generate a template for deployment abc123 and score one example row.",
#   expected_output="A CSV template path + prediction output",
#   agent=agent,
# )
#
# crew = Crew(agents=[agent], tasks=[task])
# result = crew.kickoff()
```

## Practical recommendation

- **For production agents**: prefer **helper scripts as tools** (repeatable, less prompt drift).
- **For exploratory workflows**: let the LLM write SDK code guided by `SKILL.md` (but sandbox execution).


