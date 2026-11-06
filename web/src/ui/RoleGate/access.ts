import type { Role } from "./RoleGate";

const READERS: Role[] = ["admin", "bunker_buyer", "viewer"];
const WRITERS: Role[] = ["admin", "bunker_buyer"];

/** Who may read and who may change prices-bearing records (offers, nominations; D-072). */
export const access = (roles: Role[]) => ({
  allowed: roles.some((r) => READERS.includes(r)),
  canWrite: roles.some((r) => WRITERS.includes(r)),
});
