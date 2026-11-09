import { Button } from "./ui/Button/Button";
import { Panel } from "./ui/Panel/Panel";
import styles from "./SignIn.module.css";

export type SignInProps = { error?: string; onSignIn: () => void };

/** Shown when sign-in fails: what the system is, the error, and a way to try again. */
export function SignIn({ error, onSignIn }: SignInProps) {
  return (
    <div className={styles.wrap}>
      <Panel>
        <h2 className={styles.title}>Bunker procurement</h2>
        <p className={styles.lead}>
          Inquiries, individual RFQs, offer comparison and nomination in one place.
        </p>
        {error && (
          <p role="alert" className={styles.error}>
            {error}
          </p>
        )}
        <Button variant="primary" className={styles.action} onClick={onSignIn}>
          Sign in
        </Button>
        <p className={styles.note}>Internal use only. Sign in with your company account.</p>
      </Panel>
    </div>
  );
}
