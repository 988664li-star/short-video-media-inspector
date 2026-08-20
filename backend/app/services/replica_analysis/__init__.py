"""爆款复刻的后处理服务目录。

packages：将自动分镜、关键帧与时间轴口播合成为镜头包。
playbook：汇总镜头包和分镜脚本，生成完整复刻方案。
common 与 templates 只提供三项服务共享的基础能力，不承载业务流程。
"""

from backend.app.services.replica_analysis.common import (
    ReplicaAnalysisError,
    ReplicaAnalysisModelError,
    ReplicaAnalysisNotReadyError,
)
from backend.app.services.replica_analysis.packages import ScenePackageService
from backend.app.services.replica_analysis.playbook import ReplicaPlaybookService

__all__ = (
    "ReplicaAnalysisError",
    "ReplicaAnalysisModelError",
    "ReplicaAnalysisNotReadyError",
    "ReplicaPlaybookService",
    "ScenePackageService",
)
