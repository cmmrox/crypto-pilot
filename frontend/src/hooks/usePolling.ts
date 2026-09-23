import { useEffect, useRef } from "react";

/** The part of `document` the poller watches; injectable for tests. */
export interface VisibilitySource {
  readonly visibilityState: DocumentVisibilityState;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

/**
 * Run `tick` now and every `intervalMs` while the page is visible.
 *
 * A hidden tab stops polling: each Overview poll costs the backend three Binance
 * reads, and a console left open in a background tab should cost nothing. Showing
 * the tab again refreshes immediately instead of waiting for the next interval.
 * Returns a function that stops polling.
 */
export function startVisiblePolling(
  tick: () => void,
  intervalMs: number,
  source: VisibilitySource,
): () => void {
  let timer: ReturnType<typeof setInterval> | null = null;
  const resume = () => {
    tick();
    timer ??= setInterval(tick, intervalMs);
  };
  const pause = () => {
    if (timer !== null) clearInterval(timer);
    timer = null;
  };
  const onVisibilityChange = () => (source.visibilityState === "hidden" ? pause() : resume());

  if (source.visibilityState !== "hidden") resume();
  source.addEventListener("visibilitychange", onVisibilityChange);
  return () => {
    pause();
    source.removeEventListener("visibilitychange", onVisibilityChange);
  };
}

/** Poll with the latest `tick` while the page is visible (see `startVisiblePolling`). */
export function usePolling(tick: () => void, intervalMs: number): void {
  // Always call the latest tick without restarting the timer on every render.
  const latestTick = useRef(tick);
  useEffect(() => {
    latestTick.current = tick;
  });
  useEffect(
    () => startVisiblePolling(() => latestTick.current(), intervalMs, document),
    [intervalMs],
  );
}
