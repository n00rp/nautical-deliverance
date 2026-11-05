import type { ReactNode } from "react";

export type Role = "admin" | "bunker_buyer" | "operator" | "viewer";

export type RoleGateProps = {
  allow: Role[];
  roles: Role[];
  fallback?: ReactNode;
  children: ReactNode;
};

export function RoleGate({ allow, roles, fallback = null, children }: RoleGateProps) {
  return roles.some((r) => allow.includes(r)) ? children : fallback;
}
