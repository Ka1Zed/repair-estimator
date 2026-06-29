import styles from './Layout.module.css';

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.wrapper}>
      <main className={styles.content}>
        {children}
      </main>
    </div>
  );
}