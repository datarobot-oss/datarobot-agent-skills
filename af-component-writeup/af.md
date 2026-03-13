 

Getting Started: Documentation and Community
 Before diving into building your first recipe, you'll want to bookmark these essential resources:

Primary Resources
App Templates Community Confluence Space: App Templates Community
  - This is your best starting point for all things App Templates. Think of this as your home base for community knowledge, examples, and getting oriented.

App Framework Confluence Space: 
App Framework Overview and Architecture
  - This is where the design documentation lives. If you want to understand the architecture, philosophy, and technical decisions behind the App Framework, this is your spot.

Tech Talk: Boilerplate as a Service:

Great talk by @Damon Stanley that covers the architecture and technology behind the framework

Slides (LINK)

Recording (LINK)

Slack Channel: #applications - Got questions? Need help? Want to share what you're building? This is where the community hangs out. Don't be shy - we're here to help you succeed.

Creating a New Recipe: The Foundation
Every recipe starts the same way, regardless of what you're building. Here's the process that'll get you from zero to ready-to-customize in minutes:

Step 1: Create Your Repository
Head over to the datarobot GitHub org and create a new repository

Name it with the recipe- prefix (e.g., recipe-my-awesome-app)

We strongly recommend starting from our datarobot/oss-template-repo template - it's got all the good stuff baked in

If you go with a blank repo, that's fine too - you do youDataRobot CLI Documentation 

Important Git Settings:

Allow merge commits (you'll thank me later)

Set merge commits as the default merge strategy

Step 2: Clone and Prepare


git clone git@github.com:datarobot/recipe-your-app-name.git
cd recipe-your-app-name
Step 3: Install uv
If you haven't already, grab Astral's uv package manager. It's fast, it's rad, and it makes Python dependency management actually pleasant:



# Installation instructions at: https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh
Step 4: Bootstrap Your Recipe
Now for the magic. Run this command and answer the interactive questions:



uvx copier copy https://github.com/datarobot/af-component-base .
The copier will ask you questions about your recipe - what you want to name it, what components you need, etc. Answer honestly and thoughtfully. These answers will shape the structure of your recipe.

That's it! You now have the foundation of an App Framework recipe. From here, you'll customize based on what you're building.

Example 1: Simple FastAPI Application
Overview
Just to do a simple two component app framework app that covers a ton of possible functionality, I wanted to start with a FastAPI application running via our Custom Applications features. It pairs well with our https://github.com/datarobot/af-component-react, but for now we’ll leave that out of scope

Key Components
https://github.com/datarobot/af-component-fastapi-backend/Connect your Github account 

Implementation Steps
Run:



uvx copier copy https://github.com/datarobot/af-component-fastapi-backend .
in your repo after you’ve cloned it down and added af-component-base from above.

Answer a few questions here (Defaults are all good here)

 

Then make sure you have the CLI installed:  DataRobot CLI Documentation 

and run dr task compose. After that, you’re ready to configure the app for datarobot with dr start

Testing and Validation
Go ahead and make some changes to <name>/templates/index.html (<name> is web by default).

I did this change:




<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/png" href="{{ app_base_url }}assets/img/favicon.png" />
    <title>Hello</title>
  </head>
  <body>
    <h1>hello world</h1>
    <p>Static asset check:</p>
    <img
      src="{{ app_base_url }}assets/img/favicon.png"
      alt="static favicon proof"
      width="64"
      height="64"
    />
  </body>
</html>
And then run dr run dev to start the server up on port 8080. i.e. visit http://localhost:8080 and you’ll see:


image-20260303-205846.png
You can also head to http://0.0.0.0:8080/docs or http://0.0.0.0:8080/redoc to see the FastAPI autodocs. Take note that changes are automatically discovered and the app restarted with every change in dr run dev mode:


image-20260303-210015.png
When you’re happy with that, you can run dr run deploy and it will deploy it to your DataRobot platform:


image-20260303-210102.png
visit at the URL in the output with a cmd-click or ctrl-shift-click depending on your terminal to see it there:


image-20260303-210200.png
And vibe away! Iterating locally instantly, and deploying to datarobot when you want to share or verify your local changes. With just those steps you get unit tests, linters, deployments, fast iterations, and everything else you might need to do gitflow via GitHub actions and really get to team-work driven state of the art standard practice development of your app on our platform. When you want to shut it down and save money, it is just dr run infra:down to tear it all down, and dr run deploy to bring it back. You can even move it to various different DataRobot installations or other customers by re-running dr auth set-url to change your DR info, and running dr run deploy. What a nice way to share your creations across customers, staging, pre-prod, UAT, and prod. As you go farther, we even have a simple guide and Agent Skill to configure CI/CD: CI/CD setup for application templates: DataRobot docs  and Added CI/CD skill for GitLab and GitHub by carsongee · Pull Request #4 · datarobot-oss/datarobot-agent-skills  

Example 2: LLM with Notebook
Overview
For fast iteration on simple use cases that involve LLMs but which do not (yet) require the full power of agentic workflows, app builders may want to iterate in a Python notebook, either in DataRobot or locally.

Key Components
af-component-llm

Implementation Steps
From your recipe notebook, apply the LLM component. You can accept the default answers.



$ uvx copier copy git@github.com:datarobot-community/af-component-llm .
🎤 The name/folder of your LLM Deployment. Must be a Python-friendly name (letters, numbers, underscores only, no spaces)
   llm
🎤 Model name to use for the LLM. This is the model name in the model-metadata.yaml file
   azure-openai-gpt-5-mini
🎤 Path to the base component answers file (must contain '.datarobot/answers')
   .datarobot/answers/base.yml
Copying from template version 11.4.9
    create  infra
    create  infra/configurations
    create  infra/configurations/llm
    create  infra/configurations/llm/blueprint_with_llm_gateway.py
    create  infra/configurations/llm/registered_model.py
    create  infra/configurations/llm/gateway_direct.py
    create  infra/configurations/llm/deployed_llm.py
    create  infra/configurations/llm/blueprint_with_external_llm.py
    create  infra/infra
    create  infra/infra/llm.py
    create  infra/infra/libllm.py
    create  .datarobot
    create  .datarobot/answers
    create  .datarobot/answers/llm-llm.yml
    create  .datarobot/cli
    create  .datarobot/cli/llm.yml
Then run through setup to populate the UI.



$ dr dotenv setup
This will start an interactive setup. For the passphrase enter anything.

image-20260304-181240.png
The use case can be left blank.


To be able to leverage DataRobot’s governance and monitoring features, we will select the LLM Gateway with External Model option.

image-20260304-172818.png
Press enter which will preview the .env, then press enter again to finish the wizard. 

Now we can deploy the LLM custom model.



$ dr task deploy
This will first ask you to create a stack (name it anything) and then preview the created items.

image-20260304-182959.png
Press up and to select yes and enter. This will deploy the previewed resources; when successful the output should look as follows.

image-20260304-191257.png
You’ll need the deployment ID for your custom model later, but you can always show this output again with.



dr task infra:info
If you want to test out your LLM deployment, you can find your use case in the DataRobot workbench and navigate to the LLM playground in that use case and select the deployed LLM to start chatting.

Otherwise, we’ll proceed with notebook development. Let’s setup a subdirectory for the notebook and start Jupyter. (Note if you are running this from a codespaces instead, skip the uv commands, including the uv run jupyter command, as codespaces is already notebook integrated, just run pip install dotenv litellm instead.)



mkdir notebooks
cd notebooks
uv init .
uv add jupyter dotenv litellm
uv run jupyter notebook
This will launch Jupyter in a browser window that looks as follows. (If you are running in a codespaces, use the “Create Notebook” button in the file browser instead.)

image-20260304-235300.png
Go to “File > New” and select “Notebook” to create a new notebook. Rename your notebook llm_example. We’re going to add the following blocks (press Shift-Enter in a Notebook to submit a block).




from dotenv import load_dotenv
from litellm import completion
from os import getenv
from urllib.parse import urljoin


DATAROBOT_API_TOKEN = getenv('DATAROBOT_API_TOKEN')
DATAROBOT_ENDPOINT = getenv('DATAROBOT_ENDPOINT')
For the next one, you’ll need the deployment ID from your deployment.



# Adjust these based on `dr task infra:info`
LLM_DEPLOYMENT_ID = '<DEPLOYMENT_ID>'
LLM_DEFAULT_MODEL = 'datarobot/azure/gpt-5-mini-2025-08-07'
DEPLOYMENT_BASE = urljoin(DATAROBOT_ENDPOINT, f'v2/deployments/{LLM_DEPLOYMENT_ID}/chat/completions')


def ask_llm(*messages):
    return completion(
        base_url=DEPLOYMENT_BASE,
        api_key=DATAROBOT_API_TOKEN,
        model=LLM_DEFAULT_MODEL,
        messages=messages
    )
With that setup, we can ask our deployment a question.



response = ask_llm({"content": "Hi", "role": "user"})
And then display its response.



response.choices[0].message.content


'Hello — how can I help you today?'
As one screenshot.

image-20260305-001810.png
Now that we have our notebook running locally, we can deploy that notebook on DataRobot (e.g. so we can share it with someone else, run custom jobs). We’ll create a new infra file infra/infra/notebook.py (e.g. vi infra/infra/notebook.py). Paste the following contents into that file.



from pathlib import Path
from pulumi_datarobot.notebook import Notebook
from . import use_case
PROJECT_ROOT = Path(__file__).resolve().parents[2].absolute()
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "llm_example.ipynb"
notebook = Notebook("llm_example_notebook", file_path=str(NOTEBOOK_PATH), use_case_id=use_case.id)
Save it, and now dr task deploy again. This will create a notebook you can find in your use case.

We will have to install our dependencies again in the notebook running in DR (sorry). You can boot up a terminal in the notebook and run.



pip install litellm dotenv
After that you can run your notebook. You should get the same response as locally, it will look like.

image-20260305-004205.png
Testing and Validation
For the true data-science notebook experience, run your notebook locally once, get a single success and declare victory for all time.

Example 3: LLM with Agent
Overview
For sophisticated use cases that require multi-step reasoning, tool usage, and complex workflows, the agent component provides a full agentic framework. This example builds on the LLM component from Example 2 and adds a CrewAI-based multi-agent system that can plan and execute tasks autonomously.

The generated agent is a content creation system with two specialized agents: a Planner that researches and outlines topics, and a Writer that crafts blog posts. Both agents can use MCP tools for research and fact-checking.

Key Components
af-component-llm (from Example 2)
af-component-agent

Implementation Steps
From your recipe directory (after applying base and LLM components), add the agent component using the DataRobot CLI:


dr component add agent
You'll be asked a few questions:

🎤 The name/folder of your Agent Deployment
   agent
🎤 Do you want to use low-code YAML-based configuration (i.e. NeMo Agent Toolkit)?
   No
🎤 Choose the agentic framework template to start with:
   CrewAI
🎤 Path to the base component answers file
   .datarobot/answers/base.yml
🎤 Path to the llm component answers file
   .datarobot/answers/llm-llm.yml
🎤 Path to the DataRobot MCP component answers file
   .datarobot/answers/drmcp-mcp_server.yml
Note: The MCP component is optional - you'll see a warning if the file doesn't exist, which is fine.

The component will create an agent/ directory with:

agent/agent/myagent.py - Your multi-agent workflow
agent/cli.py - Command-line interface
agent/dev.py - Local development server
agent/tests/ - Test suite
agent/public/ - UI assets (favicon, logos, theme)
infra/infra/agent.py - Pulumi deployment configuration
Now configure your environment:


dr dotenv setup
This interactive wizard will ask about:

Agent port (default: 8842)
DataRobot execution environment
Execution environment version ID
Pulumi passphrase (for infrastructure state encryption)
DataRobot default use case (can leave blank)
LLM Gateway configuration
Press enter to accept defaults for most questions.

Deploy to DataRobot:


dr task deploy
This will:

Ask you to create a stack (name it anything)
Preview the resources (LLM deployment + Agent deployment)
Deploy both to DataRobot
Output deployment IDs and URLs
Understanding the Generated Agent
The default agent (agent/agent/myagent.py) demonstrates a multi-agent CrewAI workflow:

Planner Agent: Creates outlines with key points and sources
Writer Agent: Writes blog posts based on the planner's work
Process: Sequential (planner → writer)
Both agents have access to MCP tools for research and can maintain chat history across turns.

Testing and Validation
Local Testing
The easiest way to test your agent is using the built-in CLI:


cd agent
uv run python cli.py execute --user_prompt "Write a blog post about AI in healthcare"
This will:

Run both agents (Planner → Writer) sequentially
Show a preview of the result
Save the full output to execute_output.json
To see the complete blog post that was generated:


cat execute_output.json | jq -r '.choices[0].message.content'
Or to see the full JSON response:


cat execute_output.json
Development Server with Auto-Reload
For iterative development where you're editing the agent code, run the development server:


# Terminal 1: Start the server
dr run dev

# Terminal 2: Test your changes
cd agent
uv run python cli.py execute --user_prompt "Your test prompt"
The server runs on http://localhost:8842 and automatically reloads when you edit agent code. This is useful when you're actively developing and want to test changes quickly without restarting manually.

Testing in DataRobot
After deployment, find your agent in the DataRobot workbench under your use case. You can interact with it through the agent playground or make API calls to the deployment endpoint.

The agent will execute its multi-step workflow: the Planner researches and creates an outline with key points and sources, then the Writer crafts a well-structured blog post based on that outline.

Customizing Your Agent
Want to modify the agent behavior? Edit agent/agent/myagent.py:

Change agent roles and goals
Modify task descriptions
Add more agents to the crew
Integrate additional MCP tools
Switch to a different framework (LangGraph, LlamaIndex, etc.)
After making changes, redeploy with dr run deploy to see them in DataRobot, or test locally with dr run dev.

Where to Go From Here: Keeping Your Recipe Fresh
You've built your recipe - awesome! But here's the thing: the App Framework is constantly evolving, components get updates, security patches land, and new features drop. You don't want to manually track all of that, right? Of course not.

Enter Lord/Lady/Liege Diffington
We've built an agent (using the App Framework itself - how meta is that?) that automatically keeps your recipes up to date. It's called Diffington, and it's basically your personal recipe maintenance assistant.

Here's how to get set up:

Head over to the #applications Slack channel

Request that your new recipe be added to Diffington's watch list

Provide your repo URL

What Diffington Does:

Monitors your recipe for component updates

Creates PRs when updates are available

Keeps your dependencies fresh and secure

Updates itself (because of course it does)

Resources:

Diffington Repo: 

 

GitHub App: GitHub 

Discovering Available Components
Want to know what components you can use in your recipes? There are a few ways to explore:

GitHub Search: Search for af-component in the datarobot and datarobot-community orgs

Confluence Registry: Check out the community-maintained list at 
App Framework - Studio
 

Ask in Slack: The #applications channel is full of folks who've built components and love to share

Contributing Your Own Components
Built something rad that others might want to use? Register it on the Confluence page! The App Framework thrives on community contributions. Remember: we're building on 31 million lines of open source code - contributing back is how we roll.

Final Thoughts
Building App Framework recipes is all about rapid iteration and batteries-included experiences. You're creating something that mid-maturity developers and data scientists can pick up and run with immediately. Keep it simple, keep it customizable, and don't be afraid to ask for help in #applications.

Now go build something awesome!