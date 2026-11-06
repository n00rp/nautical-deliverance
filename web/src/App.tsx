import { useEffect, useMemo, useRef, useState } from "react";
import { ADMIN_NAV, configFor } from "./admin/configs";
import { MasterDataPage } from "./admin/MasterDataPage";
import { isDashboard, parseAdmin, parseInquiries, useHash } from "./admin/routes";
import { fetchMe, type Me } from "./api";
import { userManager } from "./auth";
import { Dashboard } from "./dashboard/Dashboard";
import { createDashboardApi } from "./dashboardApi";
import { ErrorBoundary } from "./ErrorBoundary";
import type { TokenSource } from "./http";
import { InquiryPage } from "./inquiries/InquiryPage";
import { Comparison } from "./offers/Comparison";
import { OfferEntry } from "./offers/OfferEntry";
import { createNominationApi } from "./nominationApi";
import { Nomination } from "./nominations/Nomination";
import { createOfferApi } from "./offerApi";
import { RfqLog } from "./rfqs/RfqLog";
import { SupplierSelection } from "./rfqs/SupplierSelection";
import { createRfqApi } from "./rfqApi";
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

const NAV = [
  { href: "#/", label: "Dashboard" },
  { href: "#/inquiries", label: "Inquiries" },
  ...ADMIN_NAV,
];

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
  const rfqApi = useMemo(() => (signedIn ? createRfqApi(tokens) : null), [signedIn]);
  const suppliersApi = useMemo(
    () => (inquiryApi && rfqApi ? { ...inquiryApi, ...rfqApi } : null),
    [inquiryApi, rfqApi],
  );
  const offersApi = useMemo(
    () => (suppliersApi && signedIn ? { ...suppliersApi, ...createOfferApi(tokens) } : null),
    [suppliersApi, signedIn],
  );
  const dashboardApi = useMemo(() => (signedIn ? createDashboardApi(tokens) : null), [signedIn]);
  const nominationApi = useMemo(() => (signedIn ? createNominationApi(tokens) : null), [signedIn]);
  const pageApi = useMemo(
    () => (inquiryApi && nominationApi ? { ...inquiryApi, ...nominationApi } : null),
    [inquiryApi, nominationApi],
  );
  const nominationScreenApi = useMemo(
    () => (suppliersApi && nominationApi ? { ...suppliersApi, ...nominationApi } : null),
    [suppliersApi, nominationApi],
  );
  const hash = useHash();
  const route = parseAdmin(hash);
  const inquiries = parseInquiries(hash);
  const start = isDashboard(hash);

  return (
    <ToastProvider>
      <AppShell
        productName={PRODUCT_NAME}
        user={user}
        nav={user ? NAV : []}
        current={
          route ? `#/admin/${route.path}` : inquiries ? "#/inquiries" : start ? "#/" : undefined
        }
      >
        <ErrorBoundary>
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
          {user && dashboardApi && start && <Dashboard api={dashboardApi} />}
          {user && inquiryApi && inquiries && !inquiries.id && (
            <WorkList api={inquiryApi} roles={user.roles} />
          )}
          {user && suppliersApi && inquiries?.id && inquiries.view === "suppliers" && (
            <SupplierSelection
              key={inquiries.id}
              inquiryId={inquiries.id}
              api={suppliersApi}
              roles={user.roles}
            />
          )}
          {user && suppliersApi && inquiries?.id && inquiries.view === "rfqs" && (
            <RfqLog
              key={inquiries.id}
              inquiryId={inquiries.id}
              api={suppliersApi}
              roles={user.roles}
            />
          )}
          {user && offersApi && inquiries?.id && inquiries.view === "offers" && (
            <Comparison
              key={inquiries.id}
              inquiryId={inquiries.id}
              api={offersApi}
              roles={user.roles}
            />
          )}
          {user && offersApi && inquiries?.id && inquiries.view === "offer" && inquiries.rfqId && (
            <OfferEntry
              key={inquiries.rfqId}
              inquiryId={inquiries.id}
              rfqId={inquiries.rfqId}
              api={offersApi}
              roles={user.roles}
            />
          )}
          {user && nominationScreenApi && inquiries?.id && inquiries.view === "nomination" && (
            <Nomination
              key={inquiries.id}
              inquiryId={inquiries.id}
              api={nominationScreenApi}
              roles={user.roles}
            />
          )}
          {user && api && pageApi && inquiries?.id && !inquiries.view && (
            <InquiryPage
              key={inquiries.id}
              id={inquiries.id}
              api={pageApi}
              master={api}
              roles={user.roles}
            />
          )}
          {user && !route && !inquiries && !start && (
            <p>Page not found. Choose a page from the menu.</p>
          )}
        </ErrorBoundary>
      </AppShell>
      <ToastHost />
    </ToastProvider>
  );
}
