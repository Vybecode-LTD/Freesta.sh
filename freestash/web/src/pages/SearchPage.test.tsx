// @vitest-environment jsdom
// Regression (CodeRabbit, PR #7): an older query read that answers after a newer one must not take over.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ParsedQuery } from "../lib/types";
import { DEFAULT_PREFS } from "../lib/types";

const api = vi.hoisted(() => ({ parseQuery: vi.fn(), providers: vi.fn(), collections: vi.fn() }));
const searchStream = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ api, searchStream }));
vi.mock("../lib/prefs", () => ({ usePrefs: () => ({ prefs: DEFAULT_PREFS }) }));

import { SearchPage } from "./SearchPage";

const read = (original: string, q: string, media: ParsedQuery["media_types"], word: string): ParsedQuery =>
  ({ original, q, media_types: media, picks: [{ word, media_type: media[0] }] });

let root: Root;
let host: HTMLDivElement;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  api.providers.mockResolvedValue([]);
  api.collections.mockResolvedValue([]);
  searchStream.mockResolvedValue(undefined);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});

async function submit(text: string) {
  const input = host.querySelector<HTMLInputElement>("input.lens-input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

describe("SearchPage", () => {
  it("drops a query read that answers after a newer one", async () => {
    let answerFirst!: (p: ParsedQuery) => void;
    api.parseQuery
      .mockReturnValueOnce(new Promise<ParsedQuery>((resolve) => { answerFirst = resolve; }))
      .mockResolvedValueOnce(read("anchor font", "anchor", ["font"], "font"));
    await act(async () => root.render(<SearchPage onToast={() => undefined} />));

    await submit("rain sfx");      // its read is slow
    await submit("anchor font");   // its read answers at once
    await act(async () => answerFirst(read("rain sfx", "rain", ["audio"], "sfx")));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    expect(host.querySelector<HTMLInputElement>("input.lens-input")!.value).toBe("anchor");
    expect(host.querySelector(".read-as")!.textContent).toContain("“font” → Fonts");
    expect(searchStream).toHaveBeenCalledTimes(1);
    expect(searchStream.mock.calls[0][0]).toMatchObject({ q: "anchor", media: ["font"] });
  });
});
