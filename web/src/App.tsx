import { useEffect, useState } from "react";
import { fetchMe, type Me } from "./api";
import { userManager } from "./auth";
import { PRODUCT_NAME } from "./productName";

type State =
  | { kind: "loading" }
  | { kind: "signedOut" }
  | { kind: "signedIn"; me: Me }
  | { kind: "error"; message: string };

async function load(): Promise<State> {
  const params = new URLSearchParams(window.location.search);
  if (params.has("code") && params.has("state")) {
    await userManager.signinRedirectCallback();
    window.history.replaceState({}, document.title, window.location.pathname);
  }
  const user = await userManager.getUser();
  if (!user || user.expired) return { kind: "signedOut" };
  return { kind: "signedIn", me: await fetchMe(user.access_token) };
}

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    document.title = PRODUCT_NAME;
    load().then(setState, (err: unknown) => {
      setState({ kind: "error", message: err instanceof Error ? err.message : "Unknown error" });
    });
  }, []);

  return (
    <main>
      <h1>{PRODUCT_NAME}</h1>
      {state.kind === "loading" && <p>Loading…</p>}
      {state.kind === "signedOut" && (
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
      {state.kind === "error" && <p role="alert">{state.message}</p>}
    </main>
  );
}
