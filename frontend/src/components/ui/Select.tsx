import { useEffect, useRef, useState } from "react";
import styles from "./Select.module.css";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  /** Подсказка при наведении — актуально для disabled-опций (причина недоступности). */
  title?: string;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  /** box — бордер/радиус (тип комнаты, проёма); underline — крупный serif (город). */
  variant?: "box" | "underline";
  fullWidth?: boolean;
  ariaLabel?: string;
  id?: string;
}

/**
 * Кастомный дропдаун вместо нативного <select>.
 *
 * Нативный список опций на macOS рисует сама ОС (NSMenu) и игнорирует CSS, поэтому
 * в тёмной теме он остаётся тёмным. Здесь список — обычные DOM-элементы, всегда
 * под светлый дизайн на любой ОС/теме. Закрывается по клику вне и по Escape.
 */
export function Select({
  value,
  options,
  onChange,
  variant = "box",
  fullWidth = false,
  ariaLabel,
  id,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;

    const onDocClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleSelect = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <div
      className={`${styles.wrapper} ${fullWidth ? styles.wrapperFull : ""}`}
      ref={wrapperRef}
    >
      <button
        type="button"
        id={id}
        className={`${styles.trigger} ${styles[variant]}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{selected?.label ?? ""}</span>
        <span className={styles.caret} aria-hidden="true">▾</span>
      </button>

      {open && (
        <ul className={styles.list} role="listbox">
          {options.map((o) => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              aria-disabled={o.disabled}
              title={o.title}
              className={`${styles.option} ${o.value === value ? styles.optionSelected : ""} ${o.disabled ? styles.optionDisabled : ""}`}
              onClick={() => !o.disabled && handleSelect(o.value)}
            >
              <span className={styles.check} aria-hidden="true">
                {o.value === value ? "✓" : ""}
              </span>
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
