import { describe, expect, it } from "vitest";
import { LEDGER_PAGE, ledgerPath, nextCursor } from "./ledgerPages";
import type { LedgerEntry } from "./types";

const entries = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `e${i}` }) as LedgerEntry);

describe("ledger pages", () => {
  it("asks for one page, with the cursor and the files filter only when set", () => {
    expect(ledgerPath()).toBe(`/api/ledger?limit=${LEDGER_PAGE}`);
    expect(ledgerPath({ project: "tpl 01", files: true, before: "e99" }))
      .toBe(`/api/ledger?project=tpl+01&files=true&before=e99&limit=${LEDGER_PAGE}`);
  });

  it("offers another page only after a full one, from its last entry", () => {
    expect(nextCursor(entries(LEDGER_PAGE))).toBe(`e${LEDGER_PAGE - 1}`);
    expect(nextCursor(entries(LEDGER_PAGE - 1))).toBeNull();
    expect(nextCursor([])).toBeNull();
  });
});
