"""HTTP entrypoint for workflow execution and A2A coordination."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.a2a.dispatcher import A2ADispatcher
from app.config import settings
from app.graph.workflow import build_workflow
from app.persistence.run_store import RunStore
from app.schemas.requests import StartAnalysisRequest
from shared.schemas.a2a import A2ATaskRequest

app = FastAPI(title="Coding Validation Orchestrator", version="1.0.0")
run_store = RunStore(settings.run_store_path)
records: dict[str, dict] = {}
dispatcher = A2ADispatcher(records)
logger = logging.getLogger(__name__)


def _record(project_id: str) -> dict:
	return records.get(project_id) or run_store.get(project_id) or {}


async def _run_workflow(request: StartAnalysisRequest) -> None:
	project_id = request.project_id
	record = _record(project_id)
	record.update({
		"project_id": project_id,
		"status": "working",
		"progress": "understand",
		"error": None,
	})
	records[project_id] = record
	run_store.upsert(project_id, record)

	def publish_stage(stage: str, stage_status: str) -> None:
		record.update({
			"project_id": project_id,
			"status": "working",
			"progress": stage,
			"stage_status": stage_status,
		})
		records[project_id] = record
		run_store.upsert(project_id, record)

	try:
		workflow = build_workflow()
		result = await workflow.ainvoke(
			{
				"project_id": project_id,
				"project_files": {item.path: item.content for item in request.files},
				"project_context": request.project_context,
				"tools": request.tools,
			},
			config={"configurable": {"on_stage": publish_stage}},
		)
		record.update({
			"status": "completed",
			"progress": "finalize",
			"stage_status": "completed",
			"result": result,
			"validation_status": result.get("validation_status", "unknown"),
			"retry_count": result.get("retry_count", 0),
		})
	except Exception as exc:  # noqa: BLE001 - convert workflow failure to status
		logger.error("Workflow %s failed with %s", project_id, type(exc).__name__)
		record.update({
			"status": "failed",
			"stage_status": "failed",
			"failed_stage": record.get("progress"),
			"error": "Workflow execution failed. Check configured agent availability and service logs.",
		})
	records[project_id] = record
	run_store.upsert(project_id, record)


@app.get("/health")
async def health() -> dict:
	return {"status": "ok", "service": settings.service_name}


@app.get("/.well-known/agent-card.json")
async def agent_card() -> dict:
	return {
		"name": "coding-validation-orchestrator",
		"description": "Coordinates code analysis, repair, sandbox validation and reporting.",
		"skills": [
			{"id": "workflow.start", "description": "Start a validation workflow"},
			{"id": "workflow.status", "description": "Read workflow progress and result"},
			{"id": "agent.result", "description": "Receive an agent result"},
		],
	}


@app.post("/workflow/start")
async def start_workflow(request: StartAnalysisRequest) -> dict:
	if _record(request.project_id).get("status") in {"submitted", "working"}:
		raise HTTPException(status_code=409, detail="workflow is already running")
	records[request.project_id] = {
		"project_id": request.project_id,
		"status": "submitted",
		"progress": "queued",
	}
	run_store.upsert(request.project_id, records[request.project_id])
	asyncio.create_task(_run_workflow(request))
	return records[request.project_id]


@app.get("/workflow/status/{project_id}")
async def workflow_status(project_id: str) -> dict:
	record = _record(project_id)
	if not record:
		raise HTTPException(status_code=404, detail="workflow not found")
	return record


@app.get("/workflow/stream/{project_id}")
async def workflow_stream(project_id: str) -> StreamingResponse:
	if not _record(project_id):
		raise HTTPException(status_code=404, detail="workflow not found")

	async def events() -> AsyncIterator[str]:
		while True:
			current = _record(project_id)
			yield f"data: {json.dumps(current, default=str)}\n\n"
			if current.get("status") in {"completed", "failed"}:
				break
			await asyncio.sleep(0.25)

	return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/a2a/v1/tasks")
async def a2a_task(task: A2ATaskRequest) -> dict:
	if task.task_type == "workflow.start":
		response, request = dispatcher.submit_workflow(task)
		if _record(request.project_id).get("status") in {"submitted", "working"}:
			raise HTTPException(status_code=409, detail="workflow is already running")
		records[request.project_id] = {
			"project_id": request.project_id,
			"status": "submitted",
			"progress": "queued",
		}
		run_store.upsert(request.project_id, records[request.project_id])
		asyncio.create_task(_run_workflow(request))
		return response.model_dump()
	if task.task_type == "workflow.status":
		return dispatcher.status(task).model_dump()
	return dispatcher.agent_result(task).model_dump()
