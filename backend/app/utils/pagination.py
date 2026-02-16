from typing import TypeVar, Generic, Sequence
from pydantic import BaseModel
from fastapi import Response
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')


class PaginationInfo(BaseModel):
    """Pagination metadata"""
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    items: Sequence[T]
    pagination: PaginationInfo


def add_pagination_headers(
    response: Response,
    page: int,
    page_size: int,
    total_items: int
) -> None:
    """
    Add pagination information to response headers.

    Headers added:
    - X-Page: Current page number
    - X-Page-Size: Number of items per page
    - X-Total-Items: Total number of items
    - X-Total-Pages: Total number of pages
    - X-Has-Next: Whether there is a next page
    - X-Has-Previous: Whether there is a previous page
    """
    total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 0
    has_next = page < total_pages
    has_previous = page > 1

    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Items"] = str(total_items)
    response.headers["X-Total-Pages"] = str(total_pages)
    response.headers["X-Has-Next"] = str(has_next).lower()
    response.headers["X-Has-Previous"] = str(has_previous).lower()


async def paginate_query(
    db: AsyncSession,
    query: Select,
    page: int | None = None,
    page_size: int | None = None,
    max_page_size: int = 100
) -> tuple[Sequence, int]:
    """
    Paginate a SQLAlchemy query.

    Args:
        db: Database session
        query: SQLAlchemy select query
        page: Page number (1-indexed), if None returns all results
        page_size: Number of items per page, if None returns all results
        max_page_size: Maximum allowed page size

    Returns:
        Tuple of (items, total_count)
    """
    # Get total count
    count_query = query.with_only_columns(func.count()).order_by(None)
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # If pagination is not requested, return all items
    if page is None or page_size is None:
        result = await db.execute(query)
        items = result.scalars().all()
        return items, total_count

    # Validate and apply pagination
    page = max(1, page)
    page_size = min(max(1, page_size), max_page_size)

    offset = (page - 1) * page_size
    paginated_query = query.offset(offset).limit(page_size)

    result = await db.execute(paginated_query)
    items = result.scalars().all()

    return items, total_count
