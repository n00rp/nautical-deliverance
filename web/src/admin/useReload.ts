import { useCallback, useState } from "react";
import { useFail } from "./errors";

/** A counter to put in an effect's dependencies, `reload` to bump it, and `fail` that reloads on a 409. */
export function useReload() {
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  return { tick, reload, fail: useFail(reload) };
}
