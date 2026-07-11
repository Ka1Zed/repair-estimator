import { useState } from "react";
import styles from "./EstimateLedger.module.css";

export interface LedgerRowVariant {
  mode: "min" | "avg" | "max";
  title: string;
  name: string;
  price: string;
  url?: string | null;
}

export interface LedgerRow {
  name: string;
  subtitle?: string;
  volume: string;
  price: string;
  details: { label: string; value: string; url?: string | null }[];
  variants?: LedgerRowVariant[];
  activeMode?: "min" | "avg" | "max";
}

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

            {/* Детали прячем через CSS класс hiddenOnScreen */}
            <div className={`${styles.details} ${!isOpen ? styles.hiddenOnScreen : ""}`}>
              
              {/* Блок вариантов материалов (если они переданы бэкендом) */}
              {row.variants && row.variants.length > 0 && (
                <div className={styles.variantsBlock}>
                  <div className={styles.variantsTitle}>Варианты материалов:</div>
                  {row.variants.map((v, idx) => (
                    <div 
                      key={idx} 
                      className={`${styles.variantItem} ${v.mode === row.activeMode ? styles.variantActive : ""}`}
                    >
                      <div className={styles.variantHeader}>
                        <span className={styles.variantBadge}>{v.title}</span>
                        <span className={styles.variantPrice}>{v.price}</span>
                      </div>
                      <div className={styles.variantName}>
                        {v.url ? (
                          <a href={v.url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>
                            {v.name} ↗
                          </a>
                        ) : (
                          v.name
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Стандартные детали (кол-во, упаковки, запас и т.д.) */}
              {row.details.map((d, j) => (
                <div key={j} className={styles.detailItem}>
                  <span className={styles.detailLabel}>{d.label}</span>
                  <span className={styles.detailValue}>
                    {d.url ? (
                      <a
                        className={styles.sourceLink}
                        href={d.url}
                        target="_blank"
                        rel="noopener noreferrer"
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
          </div>
        );
      })}
    </div>
  );
}