import styles from "./LockedNote.module.css";

/** Says what is hidden for the role, or (with `message`) why a field cannot change. */
export function LockedNote(props: { what: string } | { message: string }) {
  return (
    <p className={styles.note}>
      {"message" in props ? props.message : `Hidden for your role: ${props.what}`}
    </p>
  );
}
