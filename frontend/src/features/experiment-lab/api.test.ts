import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../../api/client";
import { labApi } from "./api";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  apiRequest: vi.fn(),
}));

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  vi.mocked(apiRequest).mockReset();
});

describe("iteration command idempotency", () => {
  it("reuses the key after an uncertain network failure, then creates a new command", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new TypeError("connection lost"));
    await expect(labApi.run("study", "ADVISED", {})).rejects.toThrow("connection lost");
    vi.mocked(apiRequest).mockResolvedValue({ id: "iteration" });
    await labApi.run("study", "ADVISED", {});
    await labApi.run("study", "ADVISED", {});
    const calls = vi.mocked(apiRequest).mock.calls;
    expect(calls[0][1]?.headers).toEqual(calls[1][1]?.headers);
    expect(calls[1][1]?.headers).not.toEqual(calls[2][1]?.headers);
  });

  it("blocks different inputs while the previous command is unconfirmed", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new TypeError("connection lost"));
    await expect(labApi.run("study", "MANUAL", { stop_atr: "2.5" })).rejects.toThrow();
    await expect(labApi.run("study", "MANUAL", { stop_atr: "2.6" })).rejects.toThrow("unconfirmed");
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it("allows corrected inputs after a definitive validation rejection", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new ApiError(422, "invalid parameter"));
    await expect(labApi.run("study", "MANUAL", { stop_atr: "invalid" })).rejects.toThrow();
    vi.mocked(apiRequest).mockResolvedValue({ id: "iteration" });
    await expect(labApi.run("study", "MANUAL", { stop_atr: "2.5" })).resolves.toEqual({
      id: "iteration",
    });
  });
});
