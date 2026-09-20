import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.graph.workflow import workflow
from app.schemas.requests import StartAnalysisRequest, WorkflowRunResponse
from app.persistence.run_store import RunStore
from app.a2a.dispatcher import A2ADispatcher
from shared.schemas.a2a import A2ATaskRequest, A2ATaskResponse

app = FastAPI(title="LangGraph Orchestrator Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

stream_queues: dict[str, asyncio.Queue[dict]] = {}
run_records: dict[str, dict] = {}
run_store = RunStore(settings.run_store_path)
a2a_records: dict[str, dict] = {}
a2a_dispatcher = A2ADispatcher(a2a_records)
logger = logging.getLogger("orchestrator.workflow")


def save_run(project_id: str, record: dict) -> None:
    run_records[project_id] = record
    run_store.upsert(project_id, record)
    update_a2a_tasks(project_id, record)
    logger.info(
        "workflow_status project_id=%s status=%s stage=%s retry_count=%s",
        project_id,
        record.get("status"),
        record.get("stage"),
        record.get("retry_count", 0),
    )


def update_a2a_tasks(project_id: str, record: dict) -> None:
    for task_id, task in a2a_records.items():
        if task.get("project_id") == project_id:
            task.update({"status": record.get("status"), "result": record})


def workflow_response(project_id: str, state: dict) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        project_id=project_id,
        validation_status=state.get("validation_status", "unknown"),
        retry_count=state.get("retry_count", 0),
        findings=state.get("findings", []),
        final_report=state.get("final_report", {}),
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.get("/.well-known/agent-card.json")
def agent_card():
    """A2A discovery metadata for the Person 1 orchestrator agent."""
    return {
        "name": "coding-validation-orchestrator",
        "description": "Coordinates the coding validation LangGraph workflow.",
        "version": "1.0.0",
        "url": "/a2a/v1/tasks",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "skills": [
            {"id": "workflow.start", "description": "Start a project validation workflow."},
            {"id": "workflow.status", "description": "Read workflow task status."},
            {"id": "agent.result", "description": "Submit an agent result to the orchestrator."},
        ],
    }


async def run_a2a_workflow(task_id: str, request: StartAnalysisRequest) -> None:
    queue: asyncio.Queue[dict] = asyncio.Queue()
    a2a_records[task_id]["status"] = "working"
    await run_stream(request, queue)
    record = a2a_records[task_id]
    record["status"] = "completed" if run_records.get(request.project_id, {}).get("status") == "completed" else "failed"
    record["result"] = run_records.get(request.project_id, {})


@app.post("/a2a/v1/tasks", response_model=A2ATaskResponse)
async def a2a_tasks(task: A2ATaskRequest):
    """Accept A2A task messages from the frontend or specialized agents."""
    if task.task_type == "workflow.start":
        response, request = a2a_dispatcher.submit_workflow(task)
        if request.project_id in stream_queues:
            raise HTTPException(status_code=409, detail="Workflow already running")
        a2a_records[response.task_id]["project_id"] = request.project_id
        asyncio.create_task(run_a2a_workflow(response.task_id, request))
        response.status = "working"
        return response
    if task.task_type == "workflow.status":
        return a2a_dispatcher.status(task)
    return a2a_dispatcher.agent_result(task)


@app.post("/workflow/run", response_model=WorkflowRunResponse)
async def run_workflow(request: StartAnalysisRequest):
    """
    Runs the full understand -> analyze -> repair -> validate ->
    retry/finalize graph for a project and returns the final result.

    This remains available for clients that need a single blocking response.
    The gateway uses the streaming start/stream endpoints below for live
    progress updates.
    """
    initial_state = {
        "project_id": request.project_id,
        "project_files": {f.path: f.content for f in request.files},
        "project_context": request.project_context,
        "tools": request.tools,
    }

    logger.info("workflow_start project_id=%s mode=blocking", request.project_id)
    final_state = await workflow.ainvoke(initial_state)
    result = workflow_response(request.project_id, final_state)
    save_run(request.project_id, {
        "project_id": request.project_id,
        "status": "completed",
        "stage": "finalize",
        "message": "Final report ready",
        "retry_count": final_state.get("retry_count", 0),
        "result": result.model_dump(),
    })
    return result


async def run_stream(request: StartAnalysisRequest, queue: asyncio.Queue[dict]) -> None:
    state = {
        "project_id": request.project_id,
        "project_files": {f.path: f.content for f in request.files},
        "project_context": request.project_context,
        "tools": request.tools,
    }
    labels = {
        "understand": "Project uploaded",
        "analyze": "Analysis",
        "aggregate": "Finding aggregation",
        "explain_prioritize": "Explain and prioritize findings",
        "repair": "Repair",
        "validate": "Validation",
        "reanalyze": "Re-analyzing repaired code",
        "compare": "Comparing before and after",
        "bump_retry": "Retrying validation",
        "finalize": "Finalizing report",
    }

    try:
        logger.info("workflow_start project_id=%s mode=stream", request.project_id)
        async for update in workflow.astream(state, stream_mode="updates"):
            for node, partial in update.items():
                state.update(partial)
                save_run(request.project_id, {
                    "project_id": request.project_id,
                    "status": "running",
                    "stage": node,
                    "message": labels.get(node, node),
                    "retry_count": state.get("retry_count", 0),
                })
                await queue.put(
                    {"event": "progress", "step": node, "message": labels.get(node, node)}
                )
        result = workflow_response(request.project_id, state).model_dump()
        save_run(request.project_id, {
            "project_id": request.project_id,
            "status": "completed",
            "stage": "finalize",
            "message": "Final report ready",
            "retry_count": state.get("retry_count", 0),
            "result": result,
        })
        await queue.put({"event": "complete", "result": result})
    except Exception as exc:  # noqa: BLE001 - delivered to the streaming client
        logger.exception("workflow_failed project_id=%s", request.project_id)
        save_run(request.project_id, {
            "project_id": request.project_id,
            "status": "failed",
            "stage": "error",
            "message": "Workflow failed",
            "error": "Workflow failed before completion",
        })
        await queue.put({"event": "failed", "message": str(exc)})
    finally:
        await queue.put({"event": "end"})


@app.post("/workflow/start")
async def start_workflow(request: StartAnalysisRequest):
    if request.project_id in stream_queues:
        raise HTTPException(status_code=409, detail="Analysis already running for this project")
    queue: asyncio.Queue[dict] = asyncio.Queue()
    stream_queues[request.project_id] = queue
    save_run(request.project_id, {
        "project_id": request.project_id,
        "status": "queued",
        "stage": "understand",
        "message": "Analysis queued",
        "retry_count": 0,
    })
    asyncio.create_task(run_stream(request, queue))
    return {"project_id": request.project_id}


@app.get("/workflow/status/{project_id}")
async def workflow_status(project_id: str):
    record = run_records.get(project_id) or run_store.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return record


@app.get("/workflow/stream/{project_id}")
async def stream_workflow(project_id: str):
    queue = stream_queues.get(project_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Analysis stream not found")

    async def events():
        try:
            while True:
                message = await queue.get()
                if message["event"] == "end":
                    break
                yield f"event: {message['event']}\ndata: {json.dumps(message)}\n\n"
        finally:
            stream_queues.pop(project_id, None)

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
