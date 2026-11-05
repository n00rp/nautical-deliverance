import styles from "./Checkbox.module.css";

export type CheckboxProps = {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
};

export function Checkbox({ id, label, checked, onChange, disabled }: CheckboxProps) {
  return (
    <div className={styles.row}>
      <input
        id={id}
        type="checkbox"
        className={styles.box}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
    </div>
  );
}
