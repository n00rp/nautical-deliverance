export type Me = {
  user_id: string;
  organization: { id: string; name: string };
  roles: string[];
};

/** One 422 field error from the engine: `{"detail": [{"field", "message"}]}`. */
export type FieldIssue = { field: string; message: string };

export class ApiError extends Error {
  readonly status: number;
  readonly issues: FieldIssue[];
  /** The engine's text when `detail` is a plain string (409 reasons); null otherwise. */
  readonly detail: string | null;

  constructor(status: number, issues: FieldIssue[] = [], detail: string | null = null) {
    super(`Request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
    this.issues = issues;
    this.detail = detail;
  }
}

function isMe(v: unknown): v is Me {
  if (typeof v !== "object" || v === null) return false;
  const m = v as Record<string, unknown>;
  const org = m.organization as Record<string, unknown> | null | undefined;
  return (
    typeof m.user_id === "string" &&
    typeof org === "object" &&
    org !== null &&
    typeof org.id === "string" &&
    typeof org.name === "string" &&
    Array.isArray(m.roles) &&
    m.roles.every((r) => typeof r === "string")
  );
}

export async function fetchMe(accessToken: string): Promise<Me> {
  const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "");
  const response = await fetch(`${base}/api/v1/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new ApiError(response.status);
  const body: unknown = await response.json();
  if (!isMe(body)) throw new Error("Unexpected response from the server");
  return body;
}
