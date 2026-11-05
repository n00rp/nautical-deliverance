import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Role } from "../RoleGate/RoleGate";
import styles from "./AppShell.module.css";

type NavItem = { href: string; label: string; disabled?: boolean; section?: string };

export type AppShellProps = {
  productName: string;
  user: { name: string; roles: Role[] } | null;
  nav: NavItem[];
  /** href of the active nav item; it gets aria-current="page". */
  current?: string;
  banner?: ReactNode;
  children: ReactNode;
};

export function AppShell({ productName, user, nav, current, banner, children }: AppShellProps) {
  const [open, setOpen] = useState(false);
  const navId = useId();
  const menuRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    // Opening moves focus to the first nav link; Escape returns it to the Menu button.
    if (!open) return;
    navRef.current?.querySelector("a")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      menuRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  let lastSection: string | undefined;
  return (
    <div className={styles.shell}>
      {" "}
      {banner && (
        <div className={styles.banner} role="note">
          {banner}
        </div>
      )}
      <header className={styles.top}>
        <h1 className={styles.brand}>{productName}</h1>
        {user && (
          <p className={styles.user}>
            <span>{user.name}</span>
            {user.roles.length > 0 && <span className={styles.roles}>{user.roles.join(", ")}</span>}
          </p>
        )}
        {nav.length > 0 && (
          <button
            type="button"
            ref={menuRef}
            className={styles.menu}
            aria-expanded={open}
            aria-controls={navId}
            onClick={() => {
              setOpen(!open);
            }}
          >
            Menu
          </button>
        )}
      </header>
      <div className={styles.body}>
        {nav.length > 0 && (
          <nav
            ref={navRef}
            id={navId}
            aria-label="Main"
            className={`${styles.nav} ${open ? styles.open : ""}`}
          >
            {nav.map((item) => {
              const heading = item.section !== lastSection ? item.section : undefined;
              lastSection = item.section;
              return (
                <div key={item.href} className={styles.entry}>
                  {heading && <div className={styles.group}>{heading}</div>}
                  {item.disabled ? (
                    <span className={styles.disabled}>{item.label}</span>
                  ) : (
                    <a href={item.href} aria-current={item.href === current ? "page" : undefined}>
                      {item.label}
                    </a>
                  )}
                </div>
              );
            })}
          </nav>
        )}
        <main className={styles.main}>{children}</main>
      </div>
    </div>
  );
}
