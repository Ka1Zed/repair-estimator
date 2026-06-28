import { useState } from "react";
import styles from "./EstimateLedger.module.css";

export interface LedgerRow {
  name: string;
  subtitle?: string;
  volume: string;
  price: string;
details: { label: string; value: string | React.ReactNode; url?: string | null }[];}

interface EstimateLedgerProps {
  rows: LedgerRow[];
}

export function EstimateLedger({ rows }: EstimateLedgerProps) {
  const [open, setOpen] = useState<Set<number>>(new Set());

  const toggle = (i: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  if (rows.length === 0) {
    return <p className={styles.empty}>Нет данных по этому разделу</p>;
  }

  return (
    <div className={styles.ledger}>
      <div className={styles.head}>
        <span>Наименование</span>
        <span className={styles.colVol}>Объём</span>
        <span className={styles.colPrice}>Цена</span>
        <span className={styles.colArrow} />
      </div>

      {rows.map((row, i) => {
        const isOpen = open.has(i);
        return (
          <div key={i} className={styles.rowWrap}>
            <button className={styles.row} onClick={() => toggle(i)} aria-expanded={isOpen}>
              <span className={styles.name}>
                <span className={styles.nameMain}>{row.name}</span>
                {row.subtitle && <span className={styles.subtitle}>{row.subtitle}</span>}
              </span>
              <span className={`${styles.colVol} ${styles.vol}`}>{row.volume}</span>
              <span className={`${styles.colPrice} ${styles.price}`}>{row.price}</span>
              <span
                className={`${styles.colArrow} ${styles.arrow} ${isOpen ? styles.arrowOpen : ""}`}
              >
                →
              </span>
            </button>

            {isOpen && (
              <div className={styles.details}>
                {row.details.map((d, j) => (
                  <div key={j} className={styles.detailItem}>
                    <span className={styles.detailLabel}>{d.label}</span>
                    <span className={styles.detailValue}>
                      {d.url ? (
                        <a 
                          href={d.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          style={{ textDecoration: 'underline', color: 'inherit' }}
                        >
                          {d.value} ↗
                        </a>
                      ) : (
                        d.value
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
