# Using DataRobot Skills with LangGraph

## How Skills Work (General)

Skills are **instruction files** (`SKILL.md`) that guide AI agents. They work differently depending on the agent framework:

### For Claude Code / Codex / Gemini CLI
- Skills are **loaded automatically** when triggered
- Agent reads `SKILL.md` → writes Python code → executes code
- Skills act as **prompts/instructions** for the agent

### For LangGraph (Programmatic Agents)
- Skills need to be **explicitly loaded and used**
- You read `SKILL.md` content → use it as prompts → guide your agent nodes
- Skills become **part of your agent's prompt engineering**

## LangGraph Integration Approaches

## Dependency Note (LangGraph / LangChain)

LangGraph and LangChain packages evolve quickly and can be version-sensitive. If you see import errors like:

- `ImportError: cannot import name 'RemoveMessage' from 'langchain_core.messages'`

upgrade the LangChain stack to compatible versions (for example, `langgraph`, `langchain-core`, and `langchain-openai`) in the same environment.

### Approach 1: Load Skills as System Prompts

Use skill content as system prompts for your LLM nodes:

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage
import yaml
import frontmatter

def load_skill(skill_path: str) -> dict:
    """Load a skill's frontmatter and content."""
    with open(skill_path, 'r') as f:
        post = frontmatter.load(f)
        return {
            'name': post.metadata.get('name'),
            'description': post.metadata.get('description'),
            'content': post.content
        }

def create_datarobot_agent():
    # Load the predictions skill
    skill = load_skill('datarobot-predictions/SKILL.md')
    
    # Create system prompt from skill
    system_prompt = f"""
    You are a DataRobot assistant. Use the following skill guidance:
    
    {skill['content']}
    
    When making predictions:
    1. Use the DataRobot Python SDK directly
    2. Follow the workflows described above
    3. Execute code using the SDK methods shown
    """
    
    # Use in your LangGraph node
    # ... your agent setup ...
```

### Approach 2: Dynamic Skill Selection

Select skills based on user intent:

```python
from langgraph.graph import StateGraph
import os

class SkillRouter:
    def __init__(self, skills_dir='.'):
        self.skills_dir = skills_dir
        self.skills = {}
        self._load_all_skills()
    
    def _load_all_skills(self):
        """Load all available skills."""
        for skill_dir in os.listdir(self.skills_dir):
            if skill_dir.startswith('datarobot-'):
                skill_path = f"{skill_dir}/SKILL.md"
                if os.path.exists(skill_path):
                    skill = load_skill(skill_path)
                    self.skills[skill['name']] = skill
    
    def select_skill(self, user_query: str) -> dict:
        """Select appropriate skill based on user query."""
        # Simple keyword matching (you could use LLM for this)
        query_lower = user_query.lower()
        
        if 'predict' in query_lower or 'prediction' in query_lower:
            return self.skills.get('datarobot-predictions')
        elif 'train' in query_lower or 'model' in query_lower:
            return self.skills.get('datarobot-model-training')
        elif 'deploy' in query_lower:
            return self.skills.get('datarobot-model-deployment')
        # ... more matching logic
        
        return None
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """Get formatted prompt from skill."""
        skill = self.skills.get(skill_name)
        if not skill:
            return ""
        
        return f"""
        Skill: {skill['name']}
        Description: {skill['description']}
        
        {skill['content']}
        """

# Use in LangGraph
skill_router = SkillRouter()

def datarobot_node(state):
    """LangGraph node that uses skills."""
    user_query = state['messages'][-1].content
    
    # Select appropriate skill
    skill = skill_router.select_skill(user_query)
    
    if skill:
        # Add skill content to system prompt
        system_prompt = skill_router.get_skill_prompt(skill['name'])
        # ... use in your LLM call ...
    else:
        # Default behavior
        pass
    
    return state
```

### Approach 3: Execute Helper Scripts

Use the helper scripts directly in your LangGraph agent:

```python
import subprocess
import json
from langgraph.graph import StateGraph

def execute_skill_script(script_path: str, args: list) -> dict:
    """Execute a skill helper script."""
    cmd = ['python3', script_path] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=os.environ  # Includes DATAROBOT_API_TOKEN
    )
    
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        return {'error': result.stderr}

def get_deployment_features_node(state):
    """LangGraph node that uses helper script."""
    deployment_id = state.get('deployment_id')
    
    if deployment_id:
        result = execute_skill_script(
            'datarobot-predictions/scripts/get_deployment_features.py',
            [deployment_id]
        )
        state['deployment_features'] = result
    
    return state
```

### Approach 4: Use Skills as Code Templates

Extract code examples from skills and use them as templates:

```python
import re
from langgraph.graph import StateGraph

def extract_code_examples(skill_content: str) -> list:
    """Extract Python code blocks from skill content."""
    pattern = r'```python\n(.*?)\n```'
    matches = re.findall(pattern, skill_content, re.DOTALL)
    return matches

def generate_code_from_skill(skill_name: str, task: str) -> str:
    """Generate code using skill examples as templates."""
    skill = load_skill(f'{skill_name}/SKILL.md')
    examples = extract_code_examples(skill['content'])
    
    # Use examples as few-shot prompts for code generation
    # ... your code generation logic ...
    
    return generated_code

# Use in LangGraph node
def code_generation_node(state):
    skill_name = state.get('selected_skill')
    task = state.get('task')
    
    code = generate_code_from_skill(skill_name, task)
    state['generated_code'] = code
    
    return state
```

## Complete LangGraph Example (Recommended Pattern)

Rather than shipping a “known-to-run” LangGraph snippet (LangGraph/LangChain versions change frequently),
the recommended pattern is:

1. **Load** `datarobot-*/SKILL.md` as prompt text
2. **Route** to the right skill based on intent
3. **Execute** the SDK workflow directly (or via helper scripts) in a safe environment

## Best Practices for LangGraph

1. **Load skills at initialization** - Parse all `SKILL.md` files once
2. **Use skill selection** - Route to appropriate skill based on user intent
3. **Combine with code execution** - Generate code from skills, then execute
4. **Handle errors gracefully** - Skills guide code generation, but execution may fail
5. **Cache skill content** - Don't re-read files on every request
6. **Use helper scripts** - Execute scripts directly when appropriate
7. **Sandbox execution** - Always sandbox code execution in production

## Example: Simple LangGraph Agent with Skills

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
import frontmatter

# Simple skill loader
def load_skill(name: str) -> str:
    with open(f'{name}/SKILL.md', 'r') as f:
        post = frontmatter.load(f)
        return post.content

# LangGraph node that uses skill
def datarobot_node(state):
    query = state['query']
    
    # Determine which skill to use
    if 'predict' in query.lower():
        skill_content = load_skill('datarobot-predictions')
    elif 'train' in query.lower():
        skill_content = load_skill('datarobot-model-training')
    else:
        skill_content = load_skill('datarobot-predictions')  # default
    
    # Use skill as system prompt
    system_prompt = f"Use this guidance: {skill_content}"
    
    # Your LLM call here with system_prompt
    # ... generate code using skill guidance ...
    
    return state

# Build graph
workflow = StateGraph(dict)
workflow.add_node("datarobot", datarobot_node)
workflow.set_entry_point("datarobot")
workflow.add_edge("datarobot", END)
app = workflow.compile()
```

## Summary

**For LangGraph agents, skills work as:**
1. **Prompt templates** - Load skill content and use in system prompts
2. **Code templates** - Extract examples and use for few-shot learning
3. **Routing logic** - Select appropriate skill based on user intent
4. **Helper scripts** - Execute scripts directly in agent nodes

Skills don't automatically load like in Claude Code - you need to **explicitly integrate them** into your LangGraph agent's workflow.

