import { useEffect, useMemo, useRef, useState } from "react";
import { ADMIN_NAV, configFor } from "./admin/configs";
import { MasterDataPage } from "./admin/MasterDataPage";
import { parseAdmin, parseInquiries, useHash } from "./admin/routes";
import { fetchMe, type Me } from "./api";
import { userManager } from "./auth";
import type { TokenSource } from "./http";
import { WorkList } from "./inquiries/WorkList";
import { createInquiryApi } from "./inquiryApi";
import { createMasterApi } from "./masterApi";
import { PRODUCT_NAME } from "./productName";
import { AppShell } from "./ui/AppShell/AppShell";
import type { Role } from "./ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "./ui/Toast/Toast";

// The engine already drops unknown roles; this guard narrows the type for the web.
const WEB_ROLES: readonly string[] = ["admin", "bunker_buyer", "operator", "viewer"];
const isRole = (r: string): r is Role => WEB_ROLES.includes(r);

type State =
  | { kind: "loading" }
  | { kind: "signedOut" }
  | { kind: "signedIn"; me: Me }
  | { kind: "error"; message: string };

// The token is read per request: oidc-client-ts renews it in the background (about 5 min).
const tokens: TokenSource = {
  token: async () => (await userManager.getUser())?.access_token ?? "",
  renew: async () => (await userManager.signinSilent())?.access_token ?? null,
};

const NAV = [{ href: "#/inquiries", label: "Inquiries" }, ...ADMIN_NAV];

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
  const signedIn = state.kind === "signedIn";
  const api = useMemo(() => (signedIn ? createMasterApi(tokens) : null), [signedIn]);
  const inquiryApi = useMemo(() => (signedIn ? createInquiryApi(tokens) : null), [signedIn]);
  const hash = useHash();
  const route = parseAdmin(hash);
  const inquiries = parseInquiries(hash);

  return (
    <ToastProvider>
      <AppShell
        productName={PRODUCT_NAME}
        user={user}
        nav={user ? NAV : []}
        current={route ? `#/admin/${route.path}` : inquiries ? "#/inquiries" : undefined}
      >
        {state.kind === "loading" && <p role="status">Loading…</p>}
        {state.kind === "error" && <p role="alert">{state.message}</p>}
        {(state.kind === "signedOut" || state.kind === "error") && (
          <button type="button" onClick={() => void userManager.signinRedirect()}>
            Sign in
          </button>
        )}
        {user && api && route && (
          <MasterDataPage
            key={route.path}
            config={configFor(route.path)}
            api={api}
            roles={user.roles}
          />
        )}
        {user && inquiryApi && inquiries && !inquiries.id && (
          <WorkList api={inquiryApi} roles={user.roles} />
        )}
        {user && inquiries?.id && <p>Inquiry details are not available yet.</p>}
        {user && !route && !inquiries && <p>Choose a master-data page from the menu.</p>}
      </AppShell>
      <ToastHost />
    </ToastProvider>
  );
}
