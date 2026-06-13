"""
Chat / query API endpoints.

Routes:
  POST /v1/chat/query  — blocking: full JSON response with answer + citations
  POST /v1/chat/stream — streaming: SSE token stream, done event with citations

Design decisions:
  - Both routes receive the FastAPI Request to access request.state.request_id,
    which was set by the request_id_middleware in main.py.
  - All business logic lives in QueryService. This router only handles HTTP
    concerns: parsing the request body and returning the response.
  - ServiceUnavailableError (Ollama/Qdrant down) is caught by the global
    AppError handler in main.py for /query. For /stream, errors are emitted
    as SSE error events so the client receives them inline.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_query_service
from app.core.models import QueryRequest, QueryResponse
from app.services.query_service import QueryService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a question",
    description=(
        "Submit a natural-language question. The pipeline embeds the question, "
        "retrieves the most relevant document chunks, assembles them into a context, "
        "and generates a grounded answer with source citations. "
        "Returns 200 with `answer='No relevant documents found.'` when no chunks "
        "meet the score threshold — this is not an error condition."
    ),
)
async def query(
    request: Request,
    query_request: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    """
    Run the RAG pipeline and return a grounded answer with citations.

    The `request_id` in the response body matches the `X-Request-ID` response
    header and all log entries for this request, enabling end-to-end tracing.
    """
    request_id = getattr(request.state, "request_id", None)
    return await service.query(query_request, request_id=request_id)


@router.post(
    "/stream",
    summary="Stream a response via SSE",
    description=(
        "Submit a natural-language question and receive the answer as a "
        "Server-Sent Events stream. Tokens arrive in real time as they are "
        "generated. The final event contains citations and pipeline metrics. "
        "Event format: `data: {type, ...}\\n\\n`. "
        "Types: `token` (incremental content), `done` (final metadata), `error`."
    ),
)
async def stream_query(
    request: Request,
    query_request: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> StreamingResponse:
    """
    Stream the RAG response as SSE events.

    The response body is a sequence of ``data: {json}\\n\\n`` lines.
    Token events arrive during generation; the done event carries citations
    and latency once generation is complete.
    """
    request_id = getattr(request.state, "request_id", None)
    return StreamingResponse(
        service.stream_query(query_request, request_id=request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
