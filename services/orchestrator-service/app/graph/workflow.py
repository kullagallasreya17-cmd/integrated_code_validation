"""LangGraph workflow for the validation and autonomous repair loop."""

from collections.abc import Callable
from typing import Any

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


def _track_stage(stage: str, node: Callable[..., Any]) -> Callable[..., Any]:
	async def tracked(state: WorkflowState, config: dict | None = None) -> dict:
		callback = (config or {}).get("configurable", {}).get("on_stage")
		if callable(callback):
			callback(stage, "running")
		try:
			update = await node(state)
		except Exception:
			if callable(callback):
				callback(stage, "failed")
			raise

		stage_updates = update.get("stage_history", [])
		stage_status = stage_updates[-1].get("status", "completed") if stage_updates else "completed"
		if callable(callback):
			callback(stage, stage_status)
		return update

	return tracked


def build_workflow():
	"""Build the analysis graph used by the orchestrator service.

	A failed validation is routed through the bounded repair loop. Successful
	validation, or an exhausted retry budget, always reaches final reporting.
	"""
	graph = StateGraph(WorkflowState)

	graph.add_node("understand", _track_stage("understand", understand_project))
	graph.add_node("analyze", _track_stage("analyze", analyze))
	graph.add_node("aggregate", _track_stage("aggregate", aggregate_findings))
	graph.add_node("explain_prioritize", _track_stage("explain_prioritize", explain_and_prioritize))
	graph.add_node("repair", _track_stage("repair", repair))
	graph.add_node("validate", _track_stage("validate", validate))
	graph.add_node("retry", _track_stage("retry", bump_retry))
	graph.add_node("reanalyze", _track_stage("reanalyze", reanalyze))
	graph.add_node("compare", _track_stage("compare", compare_results))
	graph.add_node("finalize", _track_stage("finalize", finalize))

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
