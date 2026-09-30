/** Calendar day in the viewer's timezone, as YYYY-MM-DD. */
export function todayISO(now = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function addDaysISO(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() + days);
  return todayISO(dt);
}

export function formatIsoDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export type NewsletterBounds = { oldest: string; newest: string };

/**
 * Last two weeks, clamped so the defaults sit inside the stored newsletters.
 * Fourteen days inclusive: today and the thirteen days before it.
 */
export function defaultAiSearchRange(
  bounds: NewsletterBounds | null,
  now = new Date(),
): { from: string; to: string } {
  const today = todayISO(now);
  let to = today;
  let from = addDaysISO(today, -13);
  if (bounds) {
    if (to > bounds.newest) to = bounds.newest;
    if (from < bounds.oldest) from = bounds.oldest;
  }
  if (from > to) from = to;
  return { from, to };
}

/**
 * Why a from/to pair cannot be used. Empty strings mean "not set".
 * Future days are rejected. A day outside the stored span names that span.
 */
export function dateRangeError(
  from: string,
  to: string,
  bounds: NewsletterBounds | null,
  now = new Date(),
): string | null {
  const today = todayISO(now);
  if (from && from > today) return "Start date cannot be in the future.";
  if (to && to > today) return "End date cannot be in the future.";
  if (from && to && to < from) return "End date cannot be before the start date.";
  if (bounds) {
    const tooOld = (from && from < bounds.oldest) || (to && to < bounds.oldest);
    const tooNew = (from && from > bounds.newest) || (to && to > bounds.newest);
    if (tooOld || tooNew) {
      return `Available newsletters start from ${formatIsoDate(bounds.oldest)} and go up to ${formatIsoDate(bounds.newest)}.`;
    }
  }
  return null;
}
