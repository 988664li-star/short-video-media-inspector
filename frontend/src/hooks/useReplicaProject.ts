import { useCallback, useEffect, useState } from "react";

import { listReplicaProjects, saveReplicaProject } from "../api/replication";
import type { ReplicaProject, ReplicaProjectInput } from "../types/replication";

export function useReplicaProject() {
  const [project, setProject] = useState<ReplicaProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void listReplicaProjects()
      .then(({ projects }) => {
        if (!cancelled) setProject(projects[0] ?? null);
      })
      .catch((nextError) => {
        if (!cancelled) setError(nextError instanceof Error ? nextError.message : "读取复刻项目失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const save = useCallback(async (input: ReplicaProjectInput) => {
    setSaving(true);
    setError("");
    try {
      const { project: saved } = await saveReplicaProject({ ...input, id: project?.id });
      setProject(saved);
      return saved;
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : "保存复刻项目失败";
      setError(message);
      return null;
    } finally {
      setSaving(false);
    }
  }, [project?.id]);

  return { project, loading, saving, error, save };
}
