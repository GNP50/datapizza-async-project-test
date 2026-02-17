import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"
import { Button } from "./button"

export interface PaginationInfo {
  page: number
  pageSize: number
  totalItems: number
  totalPages: number
  hasNext: boolean
  hasPrevious: boolean
}

interface PaginationProps {
  pagination: PaginationInfo
  onPageChange: (page: number) => void
  showPageNumbers?: boolean
  maxPageButtons?: number
}

export function Pagination({
  pagination,
  onPageChange,
  showPageNumbers = true,
  maxPageButtons = 5
}: PaginationProps) {
  const { page, totalPages, hasNext, hasPrevious } = pagination

  // Calculate which page numbers to show
  const getPageNumbers = () => {
    if (totalPages <= maxPageButtons) {
      return Array.from({ length: totalPages }, (_, i) => i + 1)
    }

    const half = Math.floor(maxPageButtons / 2)
    let start = Math.max(1, page - half)
    const end = Math.min(totalPages, start + maxPageButtons - 1)

    if (end - start + 1 < maxPageButtons) {
      start = Math.max(1, end - maxPageButtons + 1)
    }

    return Array.from({ length: end - start + 1 }, (_, i) => start + i)
  }

  const pageNumbers = getPageNumbers()

  return (
    <div className="flex items-center justify-between gap-2 py-4">
      <div className="text-sm text-slate-500">
        Showing {Math.min((page - 1) * pagination.pageSize + 1, pagination.totalItems)}-
        {Math.min(page * pagination.pageSize, pagination.totalItems)} of {pagination.totalItems}
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(1)}
          disabled={!hasPrevious}
          className="h-8 w-8 p-0"
        >
          <ChevronsLeft className="h-4 w-4" />
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={!hasPrevious}
          className="h-8 w-8 p-0"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>

        {showPageNumbers && (
          <>
            {pageNumbers[0] > 1 && (
              <span className="px-2 text-sm text-slate-500">...</span>
            )}

            {pageNumbers.map((pageNum) => (
              <Button
                key={pageNum}
                variant={pageNum === page ? "default" : "outline"}
                size="sm"
                onClick={() => onPageChange(pageNum)}
                className="h-8 min-w-8 px-2"
              >
                {pageNum}
              </Button>
            ))}

            {pageNumbers[pageNumbers.length - 1] < totalPages && (
              <span className="px-2 text-sm text-slate-500">...</span>
            )}
          </>
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
          className="h-8 w-8 p-0"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(totalPages)}
          disabled={!hasNext}
          className="h-8 w-8 p-0"
        >
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
