# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A deliberately tiny LangGraph agent used as a behavioral-test fixture.

The external-agent-monitoring scenario copies this project into the sandbox
and asks the agent under test to instrument it for DataRobot OTel monitoring.
The LLM is a FakeListChatModel so the graph runs (and emits instrumentation
callbacks) with no network access and no model API key.
"""

from typing import TypedDict

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.graph import END, StateGraph


class AgentState(TypedDict):
    question: str
    context: str
    answer: str


llm = FakeListChatModel(
    responses=[
        "Month-to-month customers with short tenure and high charges churn most."
    ]
)


def lookup(state: AgentState) -> dict:
    """Stand-in for a retrieval tool."""
    return {"context": "contract_type=Month-to-month correlates strongly with churn"}


def respond(state: AgentState) -> dict:
    reply = llm.invoke(f"{state['question']}\n\nContext: {state['context']}")
    return {"answer": reply.content}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("lookup", lookup)
    graph.add_node("respond", respond)
    graph.set_entry_point("lookup")
    graph.add_edge("lookup", "respond")
    graph.add_edge("respond", END)
    return graph.compile()
