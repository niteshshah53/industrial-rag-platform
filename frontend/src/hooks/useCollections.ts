import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listCollections,
  createCollection,
  deleteCollection,
  addDocumentToCollection,
  removeDocumentFromCollection,
} from '../api/client'
import type { CollectionCreate } from '../types'

const COLLECTIONS_KEY = ['collections'] as const

export function useCollections() {
  return useQuery({
    queryKey: COLLECTIONS_KEY,
    queryFn: listCollections,
    refetchOnWindowFocus: false,
  })
}

export function useCreateCollection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CollectionCreate) => createCollection(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  })
}

export function useDeleteCollection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteCollection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  })
}

export function useAddDocumentToCollection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ collectionId, documentId }: { collectionId: string; documentId: string }) =>
      addDocumentToCollection(collectionId, documentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  })
}

export function useRemoveDocumentFromCollection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ collectionId, documentId }: { collectionId: string; documentId: string }) =>
      removeDocumentFromCollection(collectionId, documentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: COLLECTIONS_KEY }),
  })
}
