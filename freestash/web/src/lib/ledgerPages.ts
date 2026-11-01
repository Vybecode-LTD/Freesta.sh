import type { LedgerEntry } from "./types";

/** Entries per page on Downloads and the Ledger (the desktop's LedgerPages.Size matches). */
export const LEDGER_PAGE = 100;

export interface LedgerQuery { project?: string; files?: boolean; before?: string; limit?: number }

/** `/api/ledger` for one page, newest first. `before` is the last entry id of the previous page. */
export function ledgerPath(q: LedgerQuery = {}): string {
  const p = new URLSearchParams();
  if (q.project) p.set("project", q.project);
  if (q.files) p.set("files", "true");
  if (q.before) p.set("before", q.before);
  p.set("limit", String(q.limit ?? LEDGER_PAGE));
  return `/api/ledger?${p}`;
}

/** The cursor for the page after `page`, or null when it was the last: the server sends a short page only at the end. */
export function nextCursor(page: LedgerEntry[], limit = LEDGER_PAGE): string | null {
  return page.length < limit ? null : page[page.length - 1].id ?? null;
}
