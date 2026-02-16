import { useState, useCallback } from "react"
import { AxiosResponse } from "axios"

export interface PaginationInfo {
  page: number
  pageSize: number
  totalItems: number
  totalPages: number
  hasNext: boolean
  hasPrevious: boolean
}

export interface PaginatedResult<T> {
  data: T
  pagination: PaginationInfo | null
}

export function parsePaginationHeaders(response: AxiosResponse): PaginationInfo | null {
  const page = response.headers["x-page"]
  const pageSize = response.headers["x-page-size"]
  const totalItems = response.headers["x-total-items"]
  const totalPages = response.headers["x-total-pages"]
  const hasNext = response.headers["x-has-next"]
  const hasPrevious = response.headers["x-has-previous"]

  if (!page || !pageSize || !totalItems || !totalPages) {
    return null
  }

  return {
    page: parseInt(page),
    pageSize: parseInt(pageSize),
    totalItems: parseInt(totalItems),
    totalPages: parseInt(totalPages),
    hasNext: hasNext === "true",
    hasPrevious: hasPrevious === "true",
  }
}

export function usePagination(initialPage: number = 1, initialPageSize: number = 20) {
  const [page, setPage] = useState(initialPage)
  const [pageSize, setPageSize] = useState(initialPageSize)

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
  }, [])

  const handlePageSizeChange = useCallback((newPageSize: number) => {
    setPageSize(newPageSize)
    setPage(1) // Reset to first page when changing page size
  }, [])

  const reset = useCallback(() => {
    setPage(initialPage)
    setPageSize(initialPageSize)
  }, [initialPage, initialPageSize])

  return {
    page,
    pageSize,
    setPage: handlePageChange,
    setPageSize: handlePageSizeChange,
    reset,
  }
}
