from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResolveRequest(StrictRequest):
    share_text: str = Field(min_length=1, max_length=32_768)
    aweme_id: str | None = Field(default=None, max_length=30)


class TranscriptionRequest(StrictRequest):
    aweme_id: str = Field(min_length=10, max_length=30, pattern=r"^\d+$")
    context: str = Field(default="", max_length=2_000)
    media_url: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^/api/media/[a-f0-9]{32}/\d+$",
    )


class CookieRequest(StrictRequest):
    cookie: str = Field(min_length=1)


class UserProfileRequest(StrictRequest):
    sec_user_id: str = Field(min_length=10, max_length=256)


class UserPostsRequest(StrictRequest):
    sec_user_id: str = Field(min_length=10, max_length=256)
    max_cursor: int = Field(default=0, ge=0)
    count: int = Field(default=12, ge=1, le=20)


class CommentPageRequest(StrictRequest):
    aweme_id: str = Field(min_length=10, max_length=30)
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=20, ge=1, le=50)


class RelatedPostsRequest(StrictRequest):
    aweme_id: str = Field(min_length=10, max_length=30)
    count: int = Field(default=20, ge=1, le=20)


class CommentRepliesRequest(CommentPageRequest):
    comment_id: str = Field(min_length=1, max_length=64)


class UserContentRequest(StrictRequest):
    kind: Literal["posts", "likes", "mix"]
    sec_user_id: str | None = Field(default=None, max_length=256)
    mix_id: str | None = Field(default=None, max_length=64)
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=12, ge=1, le=20)

    @model_validator(mode="after")
    def validate_target(self) -> "UserContentRequest":
        if self.kind in {"posts", "likes"} and not self.sec_user_id:
            raise ValueError("用户作品和喜欢列表需要 Sec UID")
        if self.kind == "mix" and not self.mix_id:
            raise ValueError("合集作品需要合集 ID")
        return self


class ConnectionRequest(StrictRequest):
    kind: Literal["following", "followers"]
    sec_user_id: str = Field(min_length=10, max_length=256)
    user_id: str = Field(default="", max_length=64)
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=20, ge=1, le=50)


class AccountLibraryRequest(StrictRequest):
    kind: Literal["collections", "folders", "folder_posts", "music"]
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=12, ge=1, le=20)
    folder_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_folder(self) -> "AccountLibraryRequest":
        if self.kind == "folder_posts" and not self.folder_id:
            raise ValueError("收藏夹作品需要收藏夹 ID")
        return self


class FeedRequest(StrictRequest):
    kind: Literal["recommended", "following", "friends"]
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=12, ge=1, le=20)


class UserSearchRequest(StrictRequest):
    sec_user_id: str = Field(min_length=10, max_length=256)
    keyword: str = Field(min_length=1, max_length=100)
    cursor: int = Field(default=0, ge=0)
    count: int = Field(default=10, ge=1, le=20)


class SuggestRequest(StrictRequest):
    query: str = Field(min_length=1, max_length=100)
    count: int = Field(default=8, ge=1, le=20)


class LiveRoomRequest(StrictRequest):
    room_id: str = Field(min_length=1, max_length=64)


class LiveStatusRequest(StrictRequest):
    user_id: str = Field(min_length=1, max_length=64)


class LiveMessagesRequest(StrictRequest):
    room_id: str = Field(min_length=1, max_length=64)
    user_unique_id: str = Field(min_length=1, max_length=64)
