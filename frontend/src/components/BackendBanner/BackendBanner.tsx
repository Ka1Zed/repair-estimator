import styles from "./BackendBanner.module.css";
import { useBackendStatus } from "../../store/backendStatus";

export function BackendBanner() {
  const isBackendDown = useBackendStatus((s) => s.isBackendDown);
  if (!isBackendDown) return null;

  return (
    <div className={styles.banner} role="alert">
      Внимание: бэкенд недоступен. Расчёт сметы временно не работает.
    </div>
  );
}
