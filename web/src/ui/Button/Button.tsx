import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant: "primary" | "secondary" | "ghost";
  loading?: boolean;
};

export function Button({
  variant,
  loading = false,
  disabled = false,
  type = "button",
  children,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
    >
      {children}
      {loading && <span className={styles.busy}>Working…</span>}
    </button>
  );
}
