import { useEffect, useState } from "react";
import { apiClient } from "../../api/client";
import { useProjectStore } from "../../store/projectStore";
import type { SharedProject } from "../../types/project";
import type { Navigate } from "../../App";
import styles from "./SharedProjectPage.module.css";

interface Props {
  token: string;
  onNavigate: Navigate;
}

const SCOPE_LABELS: Record<string, string> = {
  finish_only: "Только чистовая отделка",
  rough_and_finish: "Черновая + чистовая",
  rough_only: "Только черновая",
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function SharedProjectPage({ token, onNavigate }: Props) {
  const [project, setProject] = useState<SharedProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProject = useProjectStore((s) => s.loadProject);

  useEffect(() => {
    apiClient
      .getSharedProject(token)
      .then(setProject)
      .catch(() => setError("Проект не найден или ссылка устарела."))
      .finally(() => setLoading(false));
  }, [token]);

  const handleOpenInEditor = () => {
    if (!project) return;
    loadProject(project);
    onNavigate({ type: "workspace" });
  };

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>Загружаем проект…</div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className={styles.page}>
        <div className={styles.error}>{error ?? "Проект не найден."}</div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.eyebrow}>Просмотр проекта</div>
      <h1 className={styles.title}>{project.name}</h1>
      <div className={styles.meta}>
        {project.city} · обновлён {fmtDate(project.updated_at)}
      </div>

      <div className={styles.badge}>{SCOPE_LABELS[project.scope] ?? project.scope}</div>

      <div className={styles.roomsLabel}>Помещения</div>
      <div className={styles.rooms}>
        {project.rooms.map((room, i) => (
          <div key={i} className={styles.room}>
            <div>{room.name}</div>
            <div className={styles.roomMeta}>
              {room.points.length} точек · высота {room.height} м
            </div>
          </div>
        ))}
      </div>

      <div className={styles.actions}>
        <button className={styles.btnOpen} onClick={handleOpenInEditor}>
          Открыть в редакторе
        </button>
      </div>
    </div>
  );
}
