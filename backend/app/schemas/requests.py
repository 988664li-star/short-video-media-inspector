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
    local_analysis_id: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
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
    extra_instruction: str = Field(default="", max_length=2_000)
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


class CanvasProjectCreateRequest(StrictRequest):
    name: str = Field(default="未命名画布", min_length=1, max_length=80)


class CanvasViewportRequest(StrictRequest):
    x: float = Field(default=14, ge=-100_000, le=100_000)
    y: float = Field(default=28, ge=-100_000, le=100_000)
    scale: float = Field(default=0.9, ge=0.1, le=3)


class CanvasNodeOperationRequest(StrictRequest):
    prompt: str = Field(default="", max_length=8_000)
    model: str = Field(default="", max_length=160)
    source_url: str | None = Field(default=None, max_length=2_000)
    referenced_asset_ids: list[str] = Field(default_factory=list, max_length=32)
    style: str = Field(default="", max_length=80)
    aspect_ratio: str = Field(default="", max_length=24)
    quality: str = Field(default="", max_length=24)
    role_mode: str = Field(default="", max_length=80)
    status: Literal["idle", "running", "succeeded", "failed"] = "idle"
    error: str | None = Field(default=None, max_length=2_000)
    message: str | None = Field(default=None, max_length=600)


class CanvasShotReplacementVersionRequest(StrictRequest):
    task_node_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    # Older multi-subject clients joined IDs with "+". Keep those queued task
    # versions readable while new clients persist only the primary subject ID.
    source_object_id: str = Field(min_length=1, max_length=720, pattern=r"^[a-zA-Z0-9_+\-]+$")
    source_object_name: str = Field(min_length=1, max_length=160)
    # Transitional input only. Provider routing is derived exclusively from model.
    provider: str | None = Field(default=None, max_length=80, exclude=True)
    model: str = Field(
        default="doubao-seedance-2-0-mini-260615",
        min_length=1,
        max_length=160,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    provider_task_id: str = Field(default="", max_length=160)
    status: Literal["pending", "queued", "running", "succeeded", "failed"] = "pending"
    result_asset_id: str = Field(default="", max_length=64, pattern=r"^[a-f0-9]{32}$|^$")
    result_asset_url: str = Field(default="", max_length=1_000)
    result_asset_name: str = Field(default="", max_length=255)
    error: str = Field(default="", max_length=2_000)


class CanvasShotAssetRequest(StrictRequest):
    index: int = Field(ge=1, le=10_000)
    start_seconds: float = Field(ge=0, le=86_400)
    end_seconds: float = Field(ge=0, le=86_400)
    duration_seconds: float = Field(gt=0, le=86_400)
    asset_id: str = Field(max_length=64, pattern=r"^[a-f0-9]{32}$")
    asset_url: str = Field(max_length=1_000)
    asset_name: str = Field(min_length=1, max_length=255)
    replacement_versions: list[CanvasShotReplacementVersionRequest] = Field(default_factory=list, max_length=100)


class CanvasAnalysisKeyframeRequest(StrictRequest):
    shot_index: int = Field(ge=1, le=10_000)
    asset_id: str = Field(max_length=64, pattern=r"^[a-f0-9]{32}$")
    asset_url: str = Field(max_length=1_000)
    asset_name: str = Field(min_length=1, max_length=255)


class CanvasReplaceableActionRequest(StrictRequest):
    shot_index: int = Field(ge=1, le=10_000)
    description: str = Field(min_length=1, max_length=1_000)


class CanvasReplaceableObjectRequest(StrictRequest):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["product", "person", "background", "text", "other"]
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    shot_indices: list[int] = Field(default_factory=list, max_length=500)
    actions: list[CanvasReplaceableActionRequest] = Field(default_factory=list, max_length=500)


class CanvasReplacementShotPromptRequest(StrictRequest):
    shot_index: int = Field(ge=1, le=10_000)
    prompt: str = Field(default="", max_length=8_000)
    input_revision: int = Field(default=0, ge=0, le=5)
    status: Literal["pending", "ready", "queued", "running", "succeeded", "failed"] = "pending"
    provider_task_id: str = Field(default="", max_length=160)
    result_asset_id: str = Field(default="", max_length=64, pattern=r"^[a-f0-9]{32}$|^$")
    error: str = Field(default="", max_length=2_000)


class CanvasReplacementSubjectRequest(StrictRequest):
    source_object_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_object_kind: Literal["product", "person", "background", "text", "other"]
    source_object_name: str = Field(min_length=1, max_length=160)
    source_object_description: str = Field(default="", max_length=2_000)
    shot_indices: list[int] = Field(default_factory=list, max_length=500)
    actions: list[CanvasReplaceableActionRequest] = Field(default_factory=list, max_length=500)
    target_description: str = Field(default="", max_length=2_000)
    target_node_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )


class CanvasReplacementTaskRequest(StrictRequest):
    analysis_node_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    shot_collection_node_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    output_shot_collection_node_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    source_object_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_object_kind: Literal["product", "person", "background", "text", "other"]
    source_object_name: str = Field(min_length=1, max_length=160)
    source_object_description: str = Field(default="", max_length=2_000)
    shot_indices: list[int] = Field(default_factory=list, max_length=500)
    actions: list[CanvasReplaceableActionRequest] = Field(default_factory=list, max_length=500)
    target_description: str = Field(default="", max_length=2_000)
    subjects: list[CanvasReplacementSubjectRequest] = Field(default_factory=list, max_length=8)
    selected_shot_indices: list[int] = Field(default_factory=list, max_length=500)
    shot_prompts: list[CanvasReplacementShotPromptRequest] = Field(default_factory=list, max_length=500)


class CanvasReplacementResultRequest(StrictRequest):
    shot_index: int = Field(ge=1, le=10_000)
    source_asset_id: str = Field(max_length=64, pattern=r"^[a-f0-9]{32}$")
    source_asset_name: str = Field(min_length=1, max_length=255)
    duration_seconds: float = Field(gt=0, le=86_400)
    # Transitional input only. Provider routing is derived exclusively from model.
    provider: str | None = Field(default=None, max_length=80, exclude=True)
    model: str = Field(
        default="doubao-seedance-2-0-mini-260615",
        min_length=1,
        max_length=160,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    provider_task_id: str = Field(default="", max_length=160)
    status: Literal["pending", "queued", "running", "succeeded", "failed", "original"] = "pending"
    result_asset_id: str = Field(default="", max_length=64, pattern=r"^[a-f0-9]{32}$|^$")
    result_asset_url: str = Field(default="", max_length=1_000)
    result_asset_name: str = Field(default="", max_length=255)
    error: str = Field(default="", max_length=2_000)


class CanvasReferenceAssetRequest(StrictRequest):
    id: str = Field(max_length=64, pattern=r"^[a-f0-9]{32}$")
    url: str = Field(max_length=1_000)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=80)


class CanvasNodeRequest(StrictRequest):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal[
        "text", "image", "video", "shot_collection", "replaceable_analysis",
        "replacement_task", "extractor", "music", "audio",
    ]
    x: float = Field(ge=-100_000, le=100_000)
    y: float = Field(ge=-100_000, le=100_000)
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(default="", max_length=600)
    content: str = Field(default="", max_length=32_768)
    source_context: str = Field(default="", max_length=4_000)
    asset_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-f0-9]{32}$")
    asset_url: str | None = Field(default=None, max_length=1_000)
    asset_name: str | None = Field(default=None, max_length=255)
    source_extractor_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    source_node_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    derived_kind: Literal["shot", "keyframe"] | None = None
    shot_assets: list[CanvasShotAssetRequest] = Field(default_factory=list, max_length=500)
    analysis_keyframes: list[CanvasAnalysisKeyframeRequest] = Field(default_factory=list, max_length=500)
    replaceable_objects: list[CanvasReplaceableObjectRequest] = Field(default_factory=list, max_length=100)
    replacement_task: CanvasReplacementTaskRequest | None = None
    reference_assets: list[CanvasReferenceAssetRequest] = Field(default_factory=list, max_length=32)
    availability_message: str | None = Field(default=None, max_length=600)
    operation: CanvasNodeOperationRequest | None = None


class CanvasEdgeRequest(StrictRequest):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    source: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    target: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    sourceHandle: str | None = Field(default=None, max_length=64)
    targetHandle: str | None = Field(default=None, max_length=64)


class CanvasProjectUpdateRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=80)
    nodes: list[CanvasNodeRequest] = Field(default_factory=list, max_length=500)
    edges: list[CanvasEdgeRequest] = Field(default_factory=list, max_length=1_000)
    viewport: CanvasViewportRequest = Field(default_factory=CanvasViewportRequest)


class CanvasTextGenerateRequest(StrictRequest):
    prompt: str = Field(min_length=1, max_length=8_000)
    context: str = Field(default="", max_length=20_000)


class CanvasImageGenerateRequest(StrictRequest):
    prompt: str = Field(min_length=1, max_length=8_000)
    source_url: str | None = Field(default=None, max_length=2_000)
    source_asset_ids: list[str] = Field(default_factory=list, max_length=8)
    aspect_ratio: Literal["原比例", "9:16", "16:9", "1:1"] = "原比例"


class CanvasMediaExtractRequest(StrictRequest):
    share_text: str = Field(min_length=1, max_length=32_768)
    platform: Literal["auto", "douyin", "tiktok"] = "auto"


class CanvasVideoAssetRequest(StrictRequest):
    asset_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-f0-9]{32}$")


class CanvasVideoComparisonRequest(StrictRequest):
    video_asset_ids: list[str] = Field(min_length=2, max_length=3)
    audio_asset_id: str = Field(default="", max_length=32, pattern=r"^[a-f0-9]{32}$|^$")

    @field_validator("video_asset_ids")
    @classmethod
    def validate_video_asset_ids(cls, value: list[str]) -> list[str]:
        if any(
            len(asset_id) != 32
            or any(character not in "0123456789abcdef" for character in asset_id)
            for asset_id in value
        ):
            raise ValueError("视频素材 ID 格式不正确")
        if len(set(value)) != len(value):
            raise ValueError("对比视频不能重复使用同一个视频素材")
        return value


class CanvasReplacementAnalysisRequest(StrictRequest):
    shots: list[CanvasShotAssetRequest] = Field(min_length=1, max_length=120)
    source_context: str = Field(default="", max_length=4_000)


class CanvasReplacementPromptSubjectRequest(StrictRequest):
    source_object_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_object_kind: Literal["product", "person", "background", "text", "other"]
    source_object_name: str = Field(min_length=1, max_length=160)
    source_object_description: str = Field(default="", max_length=2_000)
    shot_indices: list[int] = Field(default_factory=list, max_length=500)
    actions: list[CanvasReplaceableActionRequest] = Field(default_factory=list, max_length=500)
    target_description: str = Field(default="", max_length=2_000)
    target_asset_ids: list[str] = Field(min_length=1, max_length=8)


class CanvasReplacementPromptBuildRequest(StrictRequest):
    source_object_name: str = Field(min_length=1, max_length=160)
    source_object_description: str = Field(default="", max_length=2_000)
    target_description: str = Field(default="", max_length=2_000)
    target_asset_ids: list[str] = Field(min_length=1, max_length=8)
    shots: list[CanvasShotAssetRequest] = Field(min_length=1, max_length=120)
    actions: list[CanvasReplaceableActionRequest] = Field(default_factory=list, max_length=500)
    subjects: list[CanvasReplacementPromptSubjectRequest] = Field(default_factory=list, max_length=8)


class CanvasReplacementTaskSubmitRequest(StrictRequest):
    task_node_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    output_shot_collection_node_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    model: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.-]+$")
    target_asset_ids: list[str] = Field(min_length=1, max_length=8)
    shots: list[CanvasShotAssetRequest] = Field(min_length=1, max_length=120)
    prompts: list[CanvasReplacementShotPromptRequest] = Field(min_length=1, max_length=120)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self) -> "CanvasReplacementTaskSubmitRequest":
        if not self.confirmed:
            raise ValueError("请确认本次逐镜头视频生成可能产生费用")
        if any(item.input_revision != 5 for item in self.prompts):
            raise ValueError("视频编辑指令使用的是旧结构，请重新生成视频编辑指令后再提交")
        return self


class CanvasReplacementTaskRefreshRequest(StrictRequest):
    model: str = Field(
        default="doubao-seedance-2-0-mini-260615",
        min_length=1,
        max_length=160,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    provider_task_id: str = Field(min_length=1, max_length=160)
    task_node_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    output_shot_collection_node_id: str | None = Field(
        default=None, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    shot: CanvasShotAssetRequest
    result_asset_id: str = Field(default="", max_length=64, pattern=r"^[a-f0-9]{32}$|^$")


class CanvasReplacementCompositionRequest(StrictRequest):
    shots: list[CanvasShotAssetRequest] = Field(min_length=1, max_length=120)
    results: list[CanvasReplacementResultRequest] = Field(min_length=1, max_length=120)
    source_audio_asset_id: str = Field(default="", max_length=32, pattern=r"^[a-f0-9]{32}$|^$")


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
