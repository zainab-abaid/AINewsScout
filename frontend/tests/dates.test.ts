import { describe, expect, it } from "vitest";
import { dateRangeError, defaultAiSearchRange, todayISO } from "../src/dates";

const bounds = { oldest: "2026-08-01", newest: "2026-09-29" };
const now = new Date(2026, 8, 30); // 30 Sep 2026 local

describe("default AI search range", () => {
  it("covers the last two weeks and stops at the newest newsletter", () => {
    expect(defaultAiSearchRange(bounds, now)).toEqual({
      from: "2026-09-17",
      to: "2026-09-29",
    });
  });

  it("does not start before the oldest newsletter", () => {
    expect(
      defaultAiSearchRange({ oldest: "2026-09-25", newest: "2026-09-29" }, now),
    ).toEqual({ from: "2026-09-25", to: "2026-09-29" });
  });
});

describe("date range validation", () => {
  it("rejects an end date before the start date", () => {
    expect(dateRangeError("2026-09-20", "2026-09-10", bounds, now)).toMatch(/before/);
  });

  it("rejects a future day", () => {
    expect(dateRangeError(todayISO(now), "2026-10-02", bounds, now)).toMatch(/future/);
  });

  it("names the stored span when a day is outside it", () => {
    const msg = dateRangeError("2026-01-01", "2026-09-20", bounds, now) || "";
    expect(msg).toMatch(/Available newsletters start from/);
    expect(msg).toMatch(/go up to/);
    expect(dateRangeError("2026-09-01", "2026-09-20", bounds, now)).toBeNull();
  });
});
