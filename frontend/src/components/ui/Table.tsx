import { type TableHTMLAttributes } from 'react';
import styles from './Table.module.css';

export function Table({ children, className = '', ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className={styles.tableWrapper}>
      <table className={`${styles.table} ${className}`} {...props}>
        {children}
      </table>
    </div>
  );
}
