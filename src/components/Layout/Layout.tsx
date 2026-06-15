import styles from './Layout.module.css';

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.wrapper}>
      <header className={styles.header}>
        <div className={styles.logo}>🛠️ Repair Estimator</div>
        <nav className={styles.navigation}>
          <a href="#home" className={styles.navLink}>Главная</a>
          <a href="#rooms" className={styles.navLink}>Комнаты</a>
          <a href="#estimate" className={styles.navLink}>Смета</a>
        </nav>
      </header>
      <div className={styles.mainContainer}>
        <main className={styles.content}>
          {children}
        </main>
      </div>
    </div>
  );
}