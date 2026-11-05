import { useEffect, useRef, useState } from "react";
import { fetchMe, type Me } from "./api";
import { userManager } from "./auth";
import { PRODUCT_NAME } from "./productName";
import { AppShell } from "./ui/AppShell/AppShell";
import type { Role } from "./ui/RoleGate/RoleGate";

// The engine still issues S0 roles until Part B; only roles the web knows are shown.
const WEB_ROLES: readonly string[] = ["admin", "bunker_buyer", "operator", "viewer"];
const isRole = (r: string): r is Role => WEB_ROLES.includes(r);

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

  const user =
    state.kind === "signedIn"
      ? { name: state.me.organization.name, roles: state.me.roles.filter(isRole) }
      : null;

  return (
    <AppShell productName={PRODUCT_NAME} user={user} nav={[]}>
      {state.kind === "loading" && <p role="status">Loading…</p>}
      {state.kind === "error" && <p role="alert">{state.message}</p>}
      {(state.kind === "signedOut" || state.kind === "error") && (
        <button type="button" onClick={() => void userManager.signinRedirect()}>
          Sign in
        </button>
      )}
    </AppShell>
  );
}
