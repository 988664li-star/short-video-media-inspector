import { LoaderCircle, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  createCanvasProject,
  getCanvasProject,
  getOrCreateDefaultCanvasProject,
  listCanvasProjects,
  saveCanvasProject,
  uploadCanvasAsset,
} from "../api/canvasProjects";
import { AppHeader } from "../components/layout/AppHeader";
import { CanvasWorkspace } from "../features/canvas/CanvasWorkspace";
import type { CanvasAsset, CanvasDocument, CanvasProject, CanvasProjectSummary } from "../types/canvas";

function canvasHistoryLabel(project: CanvasProjectSummary) {
  const updatedAt = new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(project.updated_at);
  return `${project.name} · ${updatedAt}`;
}

export function CreativeCanvasPage() {
  const [projects, setProjects] = useState<CanvasProjectSummary[]>([]);
  const [project, setProject] = useState<CanvasProject | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const initialized = useRef(false);

  const upsertSummary = (saved: CanvasProject) => {
    const summary: CanvasProjectSummary = {
      id: saved.id,
      name: saved.name,
      asset_directory: saved.asset_directory,
      created_at: saved.created_at,
      updated_at: saved.updated_at,
    };
    setProjects((current) => [summary, ...current.filter((item) => item.id !== saved.id)]);
  };

  const persistProject = async (nextProject: CanvasProject) => {
    setSaving(true);
    setError("");
    try {
      const { project: saved } = await saveCanvasProject(nextProject.id, nextProject.name, nextProject);
      setProject(saved);
      upsertSummary(saved);
      return saved;
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存画布失败");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const createCanvas = async () => {
    if (project) await persistProject(project);
    setLoading(true);
    setError("");
    try {
      const { project: created } = await createCanvasProject();
      setProject(created);
      upsertSummary(created);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "新建画布失败");
    } finally {
      setLoading(false);
    }
  };

  const selectProject = async (projectId: string) => {
    if (projectId === project?.id) return;
    setLoading(true);
    setError("");
    try {
      const { project: selected } = await getCanvasProject(projectId);
      setProject(selected);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "读取画布失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    setLoading(true);
    void listCanvasProjects()
      .then(async ({ projects: history }) => {
        setProjects(history);
        if (history[0]) return getCanvasProject(history[0].id);
        return getOrCreateDefaultCanvasProject();
      })
      .then(({ project: loaded }) => {
        setProject(loaded);
        upsertSummary(loaded);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "读取画布失败"))
      .finally(() => setLoading(false));
  }, []);

  const updateName = (name: string) => {
    if (!project) return;
    setProject({ ...project, name });
  };

  const saveName = () => {
    if (project) void persistProject(project);
  };

  const updateDocument = (document: CanvasDocument) => {
    if (!project) return;
    const nextProject = { ...project, ...document };
    setProject(nextProject);
    void persistProject(nextProject);
  };

  const uploadAsset = async (file: File): Promise<CanvasAsset> => {
    if (!project) throw new Error("请先创建画布");
    try {
      return await uploadCanvasAsset(project.id, file);
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : "上传画布素材失败";
      setError(message);
      throw new Error(message);
    }
  };

  return (
    <>
      <AppHeader>
        <div className="canvas-page-toolbar">
          <h1>无限画布</h1>
          <div className="canvas-page-toolbar__controls">
            <label>
              <span>画布名称</span>
              <input
                value={project?.name ?? ""}
                disabled={!project}
                onBlur={saveName}
                onChange={(event) => updateName(event.target.value)}
                placeholder="未命名画布"
              />
            </label>
            <select
              aria-label="历史画布"
              value={project?.id ?? ""}
              disabled={loading || !project}
              onChange={(event) => void selectProject(event.target.value)}
            >
              {projects.map((item) => <option key={item.id} value={item.id}>{canvasHistoryLabel(item)}</option>)}
            </select>
            <button type="button" disabled={loading || saving} onClick={() => void createCanvas()}>
              <Plus /> {saving ? "保存中" : "新建画布"}
            </button>
          </div>
        </div>
      </AppHeader>
      <main className="workspace-main workspace-main--canvas">
        {loading || !project ? (
          <section className="creative-canvas-loading"><LoaderCircle className="spin" /><p>正在读取画布…</p></section>
        ) : (
          <section className="creative-canvas-page">
            <CanvasWorkspace key={project.id} projectId={project.id} document={project} onDocumentChange={updateDocument} onUploadAsset={uploadAsset} />
          </section>
        )}
        {error ? <p className="creative-canvas-error" role="alert">{error}</p> : null}
      </main>
    </>
  );
}
