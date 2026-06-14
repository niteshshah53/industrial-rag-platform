"""
Collection management API endpoints.

Routes:
  POST   /v1/collections                                — create a named collection
  GET    /v1/collections                                — list all collections
  GET    /v1/collections/{id}                           — get one collection with members
  DELETE /v1/collections/{id}                           — delete a collection
  POST   /v1/collections/{id}/documents/{doc_id}        — add a document to a collection
  DELETE /v1/collections/{id}/documents/{doc_id}        — remove a document from a collection

Design decisions:
  - Collections are lightweight named groups — they store only document_ids, not vectors.
  - Querying a collection performs a Qdrant OR filter across all member document_ids,
    so retrieval quality scales naturally with the number of member documents.
  - Adding a non-existent document_id is allowed (returns 204); the member will simply
    never match during retrieval until the document is ingested.
  - Deleting a document automatically removes it from all collections (handled in
    IngestionService.delete_document).
"""

from fastapi import APIRouter, Depends, status
from typing import Annotated

from app.api.dependencies import get_document_repository
from app.core.exceptions import CollectionNotFoundError
from app.core.models import CollectionCreate, CollectionListResponse, CollectionRecord
from app.db.document_repository import DocumentRepository

router = APIRouter(prefix="/collections", tags=["Collections"])

DocRepoDep = Annotated[DocumentRepository, Depends(get_document_repository)]


@router.post(
    "",
    response_model=CollectionRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Create a collection",
    description=(
        "Create a named collection of documents. Optionally supply an initial list "
        "of document_ids to add as members immediately."
    ),
)
async def create_collection(body: CollectionCreate, doc_repo: DocRepoDep) -> CollectionRecord:
    return doc_repo.create_collection(
        name=body.name,
        description=body.description,
        document_ids=body.document_ids,
    )


@router.get(
    "",
    response_model=CollectionListResponse,
    summary="List all collections",
    description="Return all collections with their member document counts, newest first.",
)
async def list_collections(doc_repo: DocRepoDep) -> CollectionListResponse:
    collections = doc_repo.list_collections()
    return CollectionListResponse(collections=collections, total=len(collections))


@router.get(
    "/{collection_id}",
    response_model=CollectionRecord,
    summary="Get a collection",
    description="Return a collection and the full list of its member document_ids.",
)
async def get_collection(collection_id: str, doc_repo: DocRepoDep) -> CollectionRecord:
    record = doc_repo.get_collection(collection_id)
    if record is None:
        raise CollectionNotFoundError(collection_id)
    return record


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a collection",
    description=(
        "Delete a collection and all its membership entries. "
        "Does not delete the underlying documents — only the grouping is removed."
    ),
)
async def delete_collection(collection_id: str, doc_repo: DocRepoDep) -> None:
    deleted = doc_repo.delete_collection(collection_id)
    if not deleted:
        raise CollectionNotFoundError(collection_id)


@router.post(
    "/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add document to collection",
    description="Add a document to a collection. Idempotent — no error if already a member.",
)
async def add_document_to_collection(
    collection_id: str,
    document_id: str,
    doc_repo: DocRepoDep,
) -> None:
    if doc_repo.get_collection(collection_id) is None:
        raise CollectionNotFoundError(collection_id)
    doc_repo.add_document_to_collection(collection_id, document_id)


@router.delete(
    "/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove document from collection",
    description="Remove a document from a collection. No error if not a member.",
)
async def remove_document_from_collection(
    collection_id: str,
    document_id: str,
    doc_repo: DocRepoDep,
) -> None:
    if doc_repo.get_collection(collection_id) is None:
        raise CollectionNotFoundError(collection_id)
    doc_repo.remove_document_from_collection(collection_id, document_id)
