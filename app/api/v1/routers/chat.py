"""
Chat / query API endpoint.

Routes:
  POST /v1/chat/query — submit a question, receive a grounded answer with citations

Design decisions:
  - The route receives the FastAPI Request to access request.state.request_id,
    which was set by the request_id_middleware in main.py. This threads the
    correlation ID through the entire query pipeline without manual propagation.
  - All business logic is in QueryService. This router only handles HTTP
    concerns: parsing the request body and returning the response.
  - ServiceUnavailableError (Ollama/Qdrant down) is caught by the global
    AppError handler in main.py and returned as HTTP 503.
"""

from fastapi import APIRouter, Depends, Request

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
