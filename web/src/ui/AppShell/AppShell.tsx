import { useId, useState, type ReactNode } from "react";
import type { Role } from "../RoleGate/RoleGate";
import styles from "./AppShell.module.css";

type NavItem = { href: string; label: string; disabled?: boolean; section?: string };

export type AppShellProps = {
  productName: string;
  user: { name: string; roles: Role[] } | null;
  nav: NavItem[];
  banner?: ReactNode;
  children: ReactNode;
};

export function AppShell({ productName, user, nav, banner, children }: AppShellProps) {
  const [open, setOpen] = useState(false);
  const navId = useId();
  let lastSection: string | undefined;
  return (
    <div className={styles.shell}>
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
            <span className={styles.roles}>{user.roles.join(", ")}</span>
          </p>
        )}
        {nav.length > 0 && (
          <button
            type="button"
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
          <nav id={navId} aria-label="Main" className={`${styles.nav} ${open ? styles.open : ""}`}>
            {nav.map((item) => {
              const heading = item.section !== lastSection ? item.section : undefined;
              lastSection = item.section;
              return (
                <div key={item.href} className={styles.entry}>
                  {heading && <div className={styles.group}>{heading}</div>}
                  {item.disabled ? (
                    <span className={styles.disabled}>{item.label}</span>
                  ) : (
                    <a href={item.href}>{item.label}</a>
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
