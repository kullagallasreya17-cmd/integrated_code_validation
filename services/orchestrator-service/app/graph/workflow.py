"""LangGraph workflow for the validation and autonomous repair loop."""

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
	aggregate_findings,
	analyze,
	bump_retry,
	compare_results,
	explain_and_prioritize,
	finalize,
	reanalyze,
	repair,
	should_retry,
	understand_project,
	validate,
)
from app.graph.state import WorkflowState


def build_workflow():
	"""Build the analysis graph used by the orchestrator service.

	A failed validation is routed through the bounded repair loop. Successful
	validation, or an exhausted retry budget, always reaches final reporting.
	"""
	graph = StateGraph(WorkflowState)

	graph.add_node("understand", understand_project)
	graph.add_node("analyze", analyze)
	graph.add_node("aggregate", aggregate_findings)
	graph.add_node("explain_prioritize", explain_and_prioritize)
	graph.add_node("repair", repair)
	graph.add_node("validate", validate)
	graph.add_node("retry", bump_retry)
	graph.add_node("reanalyze", reanalyze)
	graph.add_node("compare", compare_results)
	graph.add_node("finalize", finalize)

	graph.add_edge(START, "understand")
	graph.add_edge("understand", "analyze")
	graph.add_edge("analyze", "aggregate")
	graph.add_edge("aggregate", "explain_prioritize")
	graph.add_edge("explain_prioritize", "repair")
	graph.add_edge("repair", "validate")
	graph.add_conditional_edges(
		"validate",
		should_retry,
		{"retry": "retry", "finalize": "finalize"},
	)
	graph.add_edge("retry", "repair")
	graph.add_edge("finalize", "reanalyze")
	graph.add_edge("reanalyze", "compare")
	graph.add_edge("compare", END)

	return graph.compile()
