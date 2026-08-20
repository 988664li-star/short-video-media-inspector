from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResolveRequest(StrictRequest):
    share_text: str = Field(min_length=1, max_length=32_768)
    aweme_id: str | None = Field(default=None, max_length=30)
    platform: Literal["auto", "douyin", "tiktok"] = "auto"


class TranscriptionRequest(StrictRequest):
    aweme_id: str = Field(min_length=10, max_length=30, pattern=r"^\d+$")
    context: str = Field(default="", max_length=2_000)
    media_url: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^/api/media/[a-f0-9]{32}/\d+$",
    )


class ShotDetectionRequest(StrictRequest):
    aweme_id: str = Field(min_length=10, max_length=30, pattern=r"^\d+$")
    media_url: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^/api/media/[a-f0-9]{32}/\d+$",
    )


class StoryboardScriptRequest(StrictRequest):
    context: str = Field(default="", max_length=2_000)
    force: bool = False


class SeedanceReferenceAssetRequest(StrictRequest):
    slot_index: int = Field(ge=0, le=2)
    file_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(default="", max_length=255)
    label: str = Field(default="", max_length=120)


class SeedanceReplacementBindingRequest(StrictRequest):
    candidate_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    enabled: bool = False
    target_description: str = Field(default="", max_length=800)
    assets: list[SeedanceReferenceAssetRequest] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_unique_slots(self) -> "SeedanceReplacementBindingRequest":
        slots = [asset.slot_index for asset in self.assets]
        if len(slots) != len(set(slots)):
            raise ValueError("同一对象的参考图片序号不能重复")
        return self


class SeedanceWorkspaceRequest(StrictRequest):
    model: Literal[
        "doubao-seedance-2-0-mini-260615",
        "doubao-seedance-2-0-260128",
        "doubao-seedance-2-0-fast-260128",
    ] = "doubao-seedance-2-0-mini-260615"
    prompt: str = Field(default="", max_length=12_000)
    bindings: list[SeedanceReplacementBindingRequest] = Field(default_factory=list, max_length=12)


class SeedanceAnchorImageRequest(StrictRequest):
    segment_id: int = Field(ge=1, le=999)
    force: bool = False


class SeedanceAnchorImageBindingRequest(StrictRequest):
    file_id: str = Field(min_length=1, max_length=128)



class SeedanceTaskSubmitRequest(StrictRequest):
    segment_id: int | None = Field(default=None, ge=1, le=999)


class ReplicaProjectRequest(StrictRequest):
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=2, max_length=80)
    product_name: str = Field(min_length=2, max_length=160)
    platform: Literal["douyin", "tiktok"]
    market: str = Field(min_length=2, max_length=80)
    audience: str = Field(min_length=2, max_length=300)
    landing_page: str = Field(default="", max_length=500)
    target_cpa: float | None = Field(default=None, gt=0, le=1_000_000)
    brand_facts: str = Field(min_length=2, max_length=4_000)
    prohibited_claims: str = Field(default="", max_length=2_000)
    rights_mode: Literal["structure", "licensed_v2v"] = "structure"
    rights_confirmed: bool
    aigc_label_required: bool = True

    @model_validator(mode="after")
    def validate_rights(self) -> "ReplicaProjectRequest":
        if not self.rights_confirmed:
            raise ValueError("请确认拥有参考素材或其可复用结构的合法使用权")
        return self


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
