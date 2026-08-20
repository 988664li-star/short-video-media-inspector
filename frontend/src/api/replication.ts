import { apiRequest } from "./client";
import type { ReplicaProject, ReplicaProjectInput } from "../types/replication";

export function listReplicaProjects() {
  return apiRequest<{ projects: ReplicaProject[] }>(
    "/api/replication/projects",
    {},
    "读取复刻项目失败",
  );
}

export function saveReplicaProject(project: ReplicaProjectInput) {
  return apiRequest<{ project: ReplicaProject }>(
    "/api/replication/projects",
    { method: "POST", body: JSON.stringify(project) },
    "保存复刻项目失败",
  );
}
