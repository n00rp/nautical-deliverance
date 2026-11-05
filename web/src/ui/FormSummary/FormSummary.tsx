import styles from "./FormSummary.module.css";

export type FormSummaryError = { fieldId: string; message: string };

export function FormSummary({ errors }: { errors: FormSummaryError[] }) {
  if (errors.length === 0) return null;
  return (
    <div role="alert" className={styles.summary}>
      <p className={styles.title}>
        {errors.length === 1 ? "1 problem to fix" : `${errors.length} problems to fix`}
      </p>
      <ul className={styles.list}>
        {errors.map((e) => (
          <li key={e.fieldId}>
            <a
              href={`#${e.fieldId}`}
              onClick={(ev) => {
                ev.preventDefault();
                document.getElementById(e.fieldId)?.focus();
              }}
            >
              {e.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
