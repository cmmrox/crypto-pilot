import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startVisiblePolling, type VisibilitySource } from "./usePolling";

class FakeDocument implements VisibilitySource {
  visibilityState: DocumentVisibilityState = "visible";
  private listeners = new Set<() => void>();
  addEventListener(_type: "visibilitychange", listener: () => void) {
    this.listeners.add(listener);
  }
  removeEventListener(_type: "visibilitychange", listener: () => void) {
    this.listeners.delete(listener);
  }
  show(state: DocumentVisibilityState) {
    this.visibilityState = state;
    this.listeners.forEach((listener) => listener());
  }
  get listenerCount() {
    return this.listeners.size;
  }
}

describe("startVisiblePolling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ticks immediately, then on every interval while visible", () => {
    const tick = vi.fn();
    const stop = startVisiblePolling(tick, 4000, new FakeDocument());
    expect(tick).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(12000);
    expect(tick).toHaveBeenCalledTimes(4);
    stop();
  });

  it("stops while hidden and refreshes at once when shown again", () => {
    const tick = vi.fn();
    const page = new FakeDocument();
    const stop = startVisiblePolling(tick, 4000, page);
    page.show("hidden");
    vi.advanceTimersByTime(60000);
    expect(tick).toHaveBeenCalledTimes(1);
    page.show("visible");
    expect(tick).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(4000);
    expect(tick).toHaveBeenCalledTimes(3);
    stop();
  });

  it("does no work for a tab opened in the background until it is shown", () => {
    const tick = vi.fn();
    const page = new FakeDocument();
    page.visibilityState = "hidden";
    const stop = startVisiblePolling(tick, 4000, page);
    vi.advanceTimersByTime(60000);
    expect(tick).not.toHaveBeenCalled();
    page.show("visible");
    expect(tick).toHaveBeenCalledTimes(1);
    stop();
  });

  it("never runs two intervals after repeated visible events", () => {
    const tick = vi.fn();
    const page = new FakeDocument();
    const stop = startVisiblePolling(tick, 4000, page);
    page.show("visible");
    page.show("visible");
    tick.mockClear();
    vi.advanceTimersByTime(4000);
    expect(tick).toHaveBeenCalledTimes(1);
    stop();
  });

  it("stop() clears the timer and the listener", () => {
    const tick = vi.fn();
    const page = new FakeDocument();
    const stop = startVisiblePolling(tick, 4000, page);
    stop();
    vi.advanceTimersByTime(60000);
    page.show("visible");
    expect(tick).toHaveBeenCalledTimes(1);
    expect(page.listenerCount).toBe(0);
  });
});
