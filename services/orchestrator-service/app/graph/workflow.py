"""
Wires the nodes in app/graph/nodes.py into the LangGraph state machine:

    START -> understand -> analyze -> aggregate -> explain/prioritize
        -> repair -> validate -> re-analyze -> compare
        -> finalize or retry -> repair
"""
from langgraph.graph import StateGraph, END

from app.graph.state import WorkflowState
from app.graph import nodes


def build_workflow():
    graph = StateGraph(WorkflowState)

    graph.add_node("understand", nodes.understand_project)
    graph.add_node("analyze", nodes.analyze)
    graph.add_node("aggregate", nodes.aggregate_findings)
    graph.add_node("explain_prioritize", nodes.explain_and_prioritize)
    graph.add_node("repair", nodes.repair)
    graph.add_node("validate", nodes.validate)
    graph.add_node("reanalyze", nodes.reanalyze)
    graph.add_node("compare", nodes.compare_results)
    graph.add_node("bump_retry", nodes.bump_retry)
    graph.add_node("finalize", nodes.finalize)

    graph.set_entry_point("understand")

    graph.add_edge("understand", "analyze")
    graph.add_edge("analyze", "aggregate")
    graph.add_edge("aggregate", "explain_prioritize")
    graph.add_edge("explain_prioritize", "repair")
    graph.add_edge("repair", "validate")
    graph.add_edge("validate", "reanalyze")
    graph.add_edge("reanalyze", "compare")

    graph.add_conditional_edges(
        "compare",
        nodes.should_retry,
        {
            "finalize": "finalize",
            "retry": "bump_retry",
        },
    )
    graph.add_edge("bump_retry", "repair")
    graph.add_edge("finalize", END)

    return graph.compile()


# Compiled once at import time and reused across requests.
workflow = build_workflow()
