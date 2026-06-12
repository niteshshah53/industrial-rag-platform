import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listDocuments, uploadDocument, deleteDocument } from '../api/client'
import type { DocumentRecord } from '../types'

const DOCS_KEY = ['documents'] as const

/**
 * Fetch all documents. Polls every 2 s while any document is PENDING or
 * PROCESSING so the sidebar status badges update automatically.
 */
export function useDocuments() {
  return useQuery({
    queryKey: DOCS_KEY,
    queryFn: listDocuments,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const docs: DocumentRecord[] = query.state.data ?? []
      const hasActive = docs.some(
        (d) => d.status === 'pending' || d.status === 'processing',
      )
      return hasActive ? 2_000 : false
    },
  })
}

/** Upload a file — invalidates the document list on success. */
export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: DOCS_KEY }),
  })
}

/** Delete a document — invalidates the document list on success. */
export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: DOCS_KEY }),
  })
}
