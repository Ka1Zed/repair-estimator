import { useState } from "react";
import styles from "./EstimateLedger.module.css";

export interface LedgerRowVariant {
  mode: "min" | "avg" | "max";
  title: string;
  name: string;
  price: string;
  url?: string | null;
  // Приписка под названием варианта (напр. «среднее по источникам» для «Стандарт»,
  // когда цена — блендинг нескольких источников и не живёт на одной карточке).
  note?: string | null;
  // Закрепить этот вариант для строки поверх глобального уровня цены;
  // повторный клик по уже закреплённому варианту снимает закрепление.
  onClick?: () => void;
}

export interface LedgerRow {
  name: string;
  subtitle?: string;
  volume: string;
  /** Цена за единицу — показывается мелко под итогом */
  price: string;
  /** Итог по позиции (с резервом) — главное число в свёрнутой строке */
  total?: string;
  details: { label: string; value: string; url?: string | null }[];
  variants?: LedgerRowVariant[];
  activeMode?: "min" | "avg" | "max";
  /** Строка закреплена на уровне, отличном от глобального */
  isOverridden?: boolean;
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
        <span className={styles.colPrice}>Итог</span>
        <span className={styles.colArrow} />
      </div>

      {rows.map((row, i) => {
        const isOpen = open.has(i);
        return (
          <div key={i} className={styles.rowWrap}>
            <button className={styles.row} onClick={() => toggle(i)} aria-expanded={isOpen}>
              <span className={styles.name}>
                <span className={styles.nameMain}>
                  {row.name}
                  {row.isOverridden && row.activeMode && (
                    <span className={styles.overrideBadge} title="Уровень закреплён для этой позиции">
                      {row.activeMode === "min" ? "эконом" : row.activeMode === "max" ? "премиум" : "стандарт"}
                    </span>
                  )}
                </span>
                {row.subtitle && <span className={styles.subtitle}>{row.subtitle}</span>}
              </span>
              <span className={`${styles.colVol} ${styles.vol}`}>{row.volume}</span>
              <span className={`${styles.colPrice} ${styles.priceCell}`}>
                <span className={styles.totalMain}>{row.total ?? row.price}</span>
                {row.total && (
                  <span className={styles.unitPriceSub}>{row.price} / ед.</span>
                )}
              </span>
              <span
                className={`${styles.colArrow} ${styles.arrow} ${isOpen ? styles.arrowOpen : ""}`}
              >
                →
              </span>
            </button>

            <div className={`${styles.details} ${!isOpen ? styles.hiddenOnScreen : ""}`}>
              {/* Блок вариантов уровня — материал (разный товар) или работа (та же услуга, другая цена) */}
              {row.variants && row.variants.length > 0 && (
                <div className={styles.variantsBlock}>
                  <div className={styles.variantsTitle}>Варианты по уровню:</div>
                  {row.variants.map((v) => {
                    const isActive = v.mode === row.activeMode;
                    return (
                      <div
                        key={v.mode}
                        role={v.onClick ? "button" : undefined}
                        tabIndex={v.onClick ? 0 : undefined}
                        onClick={v.onClick}
                        onKeyDown={
                          v.onClick
                            ? (e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  v.onClick!();
                                }
                              }
                            : undefined
                        }
                        title={v.onClick ? (isActive ? "Снять закрепление уровня для этой позиции" : "Закрепить этот уровень для этой позиции") : undefined}
                        className={`${styles.variantItem} ${isActive ? styles.variantActive : ""} ${v.onClick ? styles.variantClickable : ""}`}
                      >
                        <div className={styles.variantHeader}>
                          <span className={styles.variantBadge}>{v.title}</span>
                          <span className={styles.variantPrice}>{v.price}</span>
                        </div>
                        <div className={styles.variantName}>
                          {v.url ? (
                            <a
                              href={v.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={styles.sourceLink}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {v.name} ↗
                            </a>
                          ) : (
                            v.name
                          )}
                          {v.note && <span className={styles.variantNote}> · {v.note}</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Стандартные детали позиции */}
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
