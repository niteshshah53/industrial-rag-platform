"""
Document management API endpoints.

Routes:
  POST   /v1/documents/upload     — upload a PDF, queue ingestion
  GET    /v1/documents            — list all documents
  GET    /v1/documents/{id}       — get a single document by ID
  DELETE /v1/documents/{id}       — delete document and its vectors

Design decisions:
  - upload() validates synchronously then delegates to BackgroundTasks.
    The response is 202 Accepted, not 200, because ingestion is async.
  - Business logic lives entirely in IngestionService. Routers only
    handle HTTP concerns: parsing multipart, setting response codes,
    and injecting dependencies.
  - AppError subclasses (DocumentNotFoundError etc.) are raised by the
    service layer and caught by the global exception handler in main.py.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, status

from app.api.dependencies import get_ingestion_service
from app.core.models import DocumentListResponse, DocumentRecord, UploadResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a PDF document",
    description=(
        "Upload a PDF file for ingestion. The file is validated immediately. "
        "Text extraction, chunking, and embedding run as a background task. "
        "Poll GET /v1/documents/{document_id} to monitor ingestion status."
    ),
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    service: IngestionService = Depends(get_ingestion_service),
) -> UploadResponse:
    """
    Accept a PDF upload, validate it, and queue ingestion as a background task.

    Returns 202 Accepted immediately. The document status will be PENDING,
    then PROCESSING, then either READY or FAILED.
    """
    content = await file.read()
    filename = file.filename or "upload.pdf"

    response = await service.upload(filename=filename, content=content)
    background_tasks.add_task(service.run_ingestion, response.document_id, content)

    return response


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents",
    description="Return all documents in the registry, newest first.",
)
async def list_documents(
    service: IngestionService = Depends(get_ingestion_service),
) -> DocumentListResponse:
    """Return all documents ordered by upload timestamp descending."""
    return service.list_documents()


@router.get(
    "/{document_id}",
    response_model=DocumentRecord,
    summary="Get document by ID",
    description="Return metadata for a single document, including its current ingestion status.",
)
async def get_document(
    document_id: str,
    service: IngestionService = Depends(get_ingestion_service),
) -> DocumentRecord:
    """
    Return document metadata by ID.

    Returns 404 if the document does not exist.
    """
    return service.get_document(document_id)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description=(
        "Delete a document from the registry and remove all its vectors from Qdrant. "
        "Returns 204 No Content on success."
    ),
)
async def delete_document(
    document_id: str,
    service: IngestionService = Depends(get_ingestion_service),
) -> None:
    """
    Delete a document and its Qdrant vectors.

    Returns 404 if the document does not exist.
    """
    await service.delete_document(document_id)
