"use client";

import { useSyncExternalStore } from "react";

const noop = () => () => {};

/**
 * false during SSR and hydration, true after — for values that only exist in
 * the browser (localStorage, resolved theme). Avoids the
 * `useEffect(() => setMounted(true))` pattern and its extra render.
 */
export function useMounted(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
