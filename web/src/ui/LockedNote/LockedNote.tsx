import styles from "./LockedNote.module.css";

export function LockedNote({ what }: { what: string }) {
  return <p className={styles.note}>Hidden for your role: {what}</p>;
}
