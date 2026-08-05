from typing import Annotated, Any, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_cookie_store, get_media_registry
from backend.app.schemas.requests import (
    AccountLibraryRequest,
    CommentPageRequest,
    CommentRepliesRequest,
    ConnectionRequest,
    FeedRequest,
    LiveRoomRequest,
    LiveMessagesRequest,
    LiveStatusRequest,
    RelatedPostsRequest,
    SuggestRequest,
    UserContentRequest,
    UserSearchRequest,
)
from backend.app.services.douyin.capabilities import (
    LoginRequiredError,
    fetch_account_library,
    fetch_account_profile,
    fetch_comment_replies,
    fetch_comments_page,
    fetch_connections,
    fetch_feed,
    fetch_following_live,
    fetch_live_room,
    fetch_live_messages,
    fetch_live_status,
    fetch_related_posts,
    fetch_suggestions,
    fetch_user_content,
    search_user_posts,
)
from backend.app.services.media import MediaRegistry
from backend.app.services.session import LoginCookieStore


router = APIRouter()
CookieStoreDependency = Annotated[LoginCookieStore, Depends(get_cookie_store)]
MediaRegistryDependency = Annotated[MediaRegistry, Depends(get_media_registry)]


async def _respond(action: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await action()
    except LoginRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"抖音能力接口请求失败：{exc}",
        ) from exc


@router.post("/comments")
async def comments(
    request: CommentPageRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_comments_page(
            request.aweme_id, request.cursor, request.count, cookie_store, registry
        )
    )


@router.post("/comment-replies")
async def comment_replies(
    request: CommentRepliesRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_comment_replies(
            request.aweme_id,
            request.comment_id,
            request.cursor,
            request.count,
            cookie_store,
            registry,
        )
    )


@router.post("/related-posts")
async def related_posts(
    request: RelatedPostsRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_related_posts(
            request.aweme_id,
            request.count,
            cookie_store,
            registry,
        )
    )


@router.post("/user-content")
async def user_content(
    request: UserContentRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_user_content(
            request.kind,
            request.sec_user_id,
            request.mix_id,
            request.cursor,
            request.count,
            cookie_store,
            registry,
        )
    )


@router.post("/connections")
async def connections(
    request: ConnectionRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_connections(
            request.kind,
            request.sec_user_id,
            request.user_id,
            request.cursor,
            request.count,
            cookie_store,
            registry,
        )
    )


@router.post("/account-library")
async def account_library(
    request: AccountLibraryRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_account_library(
            request.kind,
            request.cursor,
            request.count,
            request.folder_id,
            cookie_store,
            registry,
        )
    )


@router.post("/feed")
async def feed(
    request: FeedRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_feed(
            request.kind, request.cursor, request.count, cookie_store, registry
        )
    )


@router.post("/user-search")
async def user_search(
    request: UserSearchRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: search_user_posts(
            request.sec_user_id,
            request.keyword,
            request.cursor,
            request.count,
            cookie_store,
            registry,
        )
    )


@router.post("/suggestions")
async def suggestions(
    request: SuggestRequest,
    cookie_store: CookieStoreDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_suggestions(request.query, request.count, cookie_store)
    )


@router.post("/live-room")
async def live_room(
    request: LiveRoomRequest,
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_live_room(request.room_id, cookie_store, registry)
    )


@router.post("/live-status")
async def live_status(
    request: LiveStatusRequest,
    cookie_store: CookieStoreDependency,
) -> dict[str, Any]:
    return await _respond(lambda: fetch_live_status(request.user_id, cookie_store))


@router.post("/live-messages")
async def live_messages(
    request: LiveMessagesRequest,
    cookie_store: CookieStoreDependency,
) -> dict[str, Any]:
    return await _respond(
        lambda: fetch_live_messages(
            request.room_id,
            request.user_unique_id,
            cookie_store,
        )
    )


@router.post("/account-profile")
async def account_profile(
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(lambda: fetch_account_profile(cookie_store, registry))


@router.post("/following-live")
async def following_live(
    cookie_store: CookieStoreDependency,
    registry: MediaRegistryDependency,
) -> dict[str, Any]:
    return await _respond(lambda: fetch_following_live(cookie_store, registry))
