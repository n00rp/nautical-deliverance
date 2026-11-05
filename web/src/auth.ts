import { UserManager } from "oidc-client-ts";

// Authorization code flow; oidc-client-ts adds PKCE (S256) automatically for it.
export const userManager = new UserManager({
  authority: import.meta.env.VITE_OIDC_AUTHORITY,
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID,
  redirect_uri: `${window.location.origin}/`,
  response_type: "code",
  scope: "openid",
  automaticSilentRenew: true,
});
