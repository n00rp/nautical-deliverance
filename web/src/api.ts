export type Me = {
  user_id: string;
  organization: { id: string; name: string };
  roles: string[];
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`Request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function fetchMe(accessToken: string): Promise<Me> {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/v1/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as Me;
}
