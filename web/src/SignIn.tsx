import { Button } from "./ui/Button/Button";
import styles from "./SignIn.module.css";

export type SignInProps = { error?: string; onSignIn: () => void };

/** The signed-out start page: what the system is, any sign-in error, and the way in. */
export function SignIn({ error, onSignIn }: SignInProps) {
  return (
    <section className={styles.card} aria-labelledby="sign-in-title">
      <h2 id="sign-in-title" className={styles.title}>
        Bunker procurement
      </h2>
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
    </section>
  );
}
