import { useEffect, useState } from "react";
import { apiClient } from "../../api/client";
import { useProjectStore } from "../../store/projectStore";
import type { ProjectSummary, Project } from "../../types/project";
import type { Navigate } from "../../App";
import styles from "./ProjectsPage.module.css";

interface Props {
  onNavigate: Navigate;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function ProjectsPage({ onNavigate }: Props) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadProject = useProjectStore((s) => s.loadProject);

  useEffect(() => {
    apiClient
      .listProjects()
      .then(setProjects)
      .catch(() => setError("Не удалось загрузить проекты. Проверьте, что бэкенд запущен."))
      .finally(() => setLoading(false));
  }, []);

  const handleOpen = async (id: number) => {
    try {
      const project: Project = await apiClient.getProject(id);
      loadProject(project);
      onNavigate({ type: "workspace", projectId: id });
    } catch {
      setError("Не удалось открыть проект.");
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await apiClient.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch {
      setError("Не удалось удалить проект.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className={styles.page}>
      <button className={styles.backBtn} onClick={() => onNavigate({ type: "workspace" })}>
        ← Назад к редактору
      </button>
      <div className={styles.eyebrow}>Проекты</div>
      <h1 className={styles.title}>Мои проекты</h1>

      {loading && <div className={styles.loading}>Загружаем список проектов…</div>}
      {error && <div className={styles.error}>{error}</div>}

      {!loading && !error && projects.length === 0 && (
        <div className={styles.empty}>
          Сохранённых проектов пока нет.
          <br />
          Постройте план в редакторе и нажмите «Сохранить проект».
        </div>
      )}

      {!loading && projects.length > 0 && (
        <div className={styles.list}>
          {projects.map((p) => (
            <div key={p.id} className={styles.card}>
              <div className={styles.cardInfo}>
                <div className={styles.cardName}>{p.name}</div>
                <div className={styles.cardMeta}>
                  {p.city} · обновлён {fmtDate(p.updated_at)}
                </div>
              </div>
              <div className={styles.cardActions}>
                <button className={styles.btnOpen} onClick={() => handleOpen(p.id)}>
                  Открыть
                </button>
                <button
                  className={styles.btnDelete}
                  onClick={() => handleDelete(p.id)}
                  disabled={deletingId === p.id}
                >
                  Удалить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
