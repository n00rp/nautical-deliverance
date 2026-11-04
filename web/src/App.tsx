import { useEffect, useRef, useState } from "react";
import { fetchMe, type Me } from "./api";
import { userManager } from "./auth";
import { PRODUCT_NAME } from "./productName";

type State =
  | { kind: "loading" }
  | { kind: "signedOut" }
  | { kind: "signedIn"; me: Me }
  | { kind: "error"; message: string };

function cleanUrl() {
  window.history.replaceState({}, document.title, window.location.pathname);
}

async function load(): Promise<State> {
  const params = new URLSearchParams(window.location.search);
  if (params.has("error")) {
    cleanUrl();
    return { kind: "error", message: "Sign-in was cancelled or denied." };
  }
  if (params.has("code") && params.has("state")) {
    try {
      await userManager.signinRedirectCallback();
    } finally {
      cleanUrl();
    }
  }
  const user = await userManager.getUser();
  if (!user || user.expired) return { kind: "signedOut" };
  return { kind: "signedIn", me: await fetchMe(user.access_token) };
}

function loadSafely(): Promise<State> {
  return load().catch((err: unknown) => ({
    kind: "error",
    message: err instanceof Error ? err.message : "Unknown error",
  }));
}

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  // Kept in a ref so StrictMode's second effect run reuses the one-shot OIDC load.
  const pending = useRef<Promise<State> | null>(null);

  useEffect(() => {
    document.title = PRODUCT_NAME;
    let ignore = false;
    pending.current ??= loadSafely();
    void pending.current.then((s) => {
      if (!ignore) setState(s);
    });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <main>
      <h1>{PRODUCT_NAME}</h1>
      {state.kind === "loading" && <p role="status">Loading…</p>}
      {state.kind === "error" && <p role="alert">{state.message}</p>}
      {(state.kind === "signedOut" || state.kind === "error") && (
        <button type="button" onClick={() => void userManager.signinRedirect()}>
          Sign in
        </button>
      )}
      {state.kind === "signedIn" && (
        <dl>
          <dt>Organization</dt>
          <dd>{state.me.organization.name}</dd>
          <dt>Roles</dt>
          <dd>{state.me.roles.join(", ")}</dd>
        </dl>
      )}
    </main>
  );
}
