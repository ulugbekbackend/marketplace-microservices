"""Request dependencies: services kept on the application state."""

from typing import Annotated

from fastapi import Depends, Request

from app.services.reindex import Reindexer
from app.services.search import SearchService


def get_search_service(request: Request) -> SearchService:
    service: SearchService = request.app.state.search_service
    return service


def get_reindexer(request: Request) -> Reindexer:
    reindexer: Reindexer = request.app.state.reindexer
    return reindexer


Search = Annotated[SearchService, Depends(get_search_service)]
ReindexerDep = Annotated[Reindexer, Depends(get_reindexer)]
