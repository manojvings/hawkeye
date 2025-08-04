# app/core/pagination.py
"""
Automatic pagination system that works as a base for all list endpoints
"""
from typing import TypeVar, Generic, List, Optional, Dict, Any, Type
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import select, func, Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Query
from fastapi import Query as QueryParam, Depends, Request
from math import ceil

T = TypeVar('T')


class PaginationParams(BaseModel):
    """Base pagination parameters used across all endpoints"""
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    size: int = Field(20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: str = Field("asc", regex="^(asc|desc)$", description="Sort order")
    search: Optional[str] = Field(None, description="Search term")

    @computed_field
    @property
    def offset(self) -> int:
        """Calculate offset for database query"""
        return (self.page - 1) * self.size


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response that all list endpoints will use
    """
    items: List[T]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool
    links: Optional[Dict[str, Optional[str]]] = None

    class Config:
        from_attributes = True


class AutoPaginator:
    """
    Automatic paginator that can be used as a base for all list endpoints
    """

    @staticmethod
    async def paginate(
            db: AsyncSession,
            model: Type[T],
            params: PaginationParams,
            response_schema: Optional[Type[BaseModel]] = None,
            filters: Optional[Dict[str, Any]] = None,
            search_fields: Optional[List[str]] = None,
            base_query: Optional[Select] = None,
            request: Optional[Request] = None
    ) -> PaginatedResponse[T]:
        """
        Automatically paginate any SQLAlchemy model

        Args:
            db: Database session
            model: SQLAlchemy model class
            params: Pagination parameters
            response_schema: Pydantic schema for response serialization
            filters: Dictionary of field:value filters
            search_fields: Fields to search in
            base_query: Optional base query to build upon
            request: FastAPI request for building links
        """
        # Start with base query or create new one
        if base_query is None:
            query = select(model)
        else:
            query = base_query

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(model, field) and value is not None:
                    query = query.where(getattr(model, field) == value)

        # Apply search
        if params.search and search_fields:
            from sqlalchemy import or_
            search_conditions = []
            for field in search_fields:
                if hasattr(model, field):
                    search_conditions.append(
                        getattr(model, field).ilike(f"%{params.search}%")
                    )
            if search_conditions:
                query = query.where(or_(*search_conditions))

        # Apply sorting
        if params.sort_by and hasattr(model, params.sort_by):
            order_column = getattr(model, params.sort_by)
            if params.sort_order == "desc":
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        elif hasattr(model, 'id'):
            # Default sort by id if no sort specified
            query = query.order_by(model.id.desc())

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)
        total = total or 0

        # Calculate pages
        pages = ceil(total / params.size) if total > 0 else 0

        # Apply pagination
        query = query.offset(params.offset).limit(params.size)

        # Execute query
        result = await db.execute(query)
        items = result.scalars().all()

        # Convert to response schema if provided
        if response_schema:
            items = [response_schema.from_orm(item) for item in items]

        # Build links if request provided
        links = None
        if request:
            base_url = str(request.url).split('?')[0]
            links = AutoPaginator._build_links(base_url, params, pages)

        return PaginatedResponse(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=pages,
            has_next=params.page < pages,
            has_prev=params.page > 1,
            links=links
        )

    @staticmethod
    def _build_links(base_url: str, params: PaginationParams, total_pages: int) -> Dict[str, Optional[str]]:
        """Build HATEOAS-style pagination links"""
        links = {
            "self": f"{base_url}?page={params.page}&size={params.size}",
            "first": None,
            "prev": None,
            "next": None,
            "last": None
        }

        if total_pages > 0:
            links["first"] = f"{base_url}?page=1&size={params.size}"
            links["last"] = f"{base_url}?page={total_pages}&size={params.size}"

            if params.page > 1:
                links["prev"] = f"{base_url}?page={params.page - 1}&size={params.size}"

            if params.page < total_pages:
                links["next"] = f"{base_url}?page={params.page + 1}&size={params.size}"

        # Add search and sort parameters if present
        for link_type, link in links.items():
            if link:
                if params.search:
                    link += f"&search={params.search}"
                if params.sort_by:
                    link += f"&sort_by={params.sort_by}&sort_order={params.sort_order}"
                links[link_type] = link

        return links


# FastAPI dependency for pagination
def get_pagination(
        page: int = QueryParam(1, ge=1, description="Page number"),
        size: int = QueryParam(20, ge=1, le=100, description="Items per page"),
        sort_by: Optional[str] = QueryParam(None, description="Sort field"),
        sort_order: str = QueryParam("asc", regex="^(asc|desc)$", description="Sort order"),
        search: Optional[str] = QueryParam(None, description="Search term")
) -> PaginationParams:
    """Dependency to extract pagination parameters"""
    return PaginationParams(
        page=page,
        size=size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search
    )


# Decorator for automatic pagination (optional approach)
def paginated(
        model: Type[T],
        response_schema: Optional[Type[BaseModel]] = None,
        search_fields: Optional[List[str]] = None
):
    """
    Decorator to automatically add pagination to list endpoints

    Usage:
        @router.get("/users", response_model=PaginatedResponse[UserResponse])
        @paginated(model=User, response_schema=UserResponse, search_fields=["email", "name"])
        async def list_users(
            db: AsyncSession = Depends(get_db),
            pagination: PaginationParams = Depends(get_pagination),
            request: Request = None
        ):
            # The decorator handles pagination automatically
            return await AutoPaginator.paginate(
                db, model, pagination, response_schema,
                search_fields=search_fields, request=request
            )
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # The actual pagination is handled in the function
            # This decorator could be extended to automatically inject pagination
            return await func(*args, **kwargs)

        return wrapper

    return decorator