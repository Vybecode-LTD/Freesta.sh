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
  ({ original, q, media_types: media, packs: false, picks: [{ word, media_type: media[0], packs: false }] });

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

  // contract packs-and-new-kinds
  it("a pack word turns Packs on, searching once with packs", async () => {
    api.parseQuery.mockResolvedValueOnce({
      original: "sword sfx pack", q: "sword", media_types: ["audio"], packs: true,
      picks: [{ word: "sfx", media_type: "audio", packs: false }, { word: "pack", media_type: null, packs: true }],
    } satisfies ParsedQuery);
    await act(async () => root.render(<SearchPage onToast={() => undefined} />));
    await submit("sword sfx pack");

    expect(searchStream).toHaveBeenCalledTimes(1);
    expect(searchStream.mock.calls[0][0]).toMatchObject({ q: "sword", media: ["audio"], packs: true });
    expect(host.querySelector('[aria-label="Packs"] [aria-pressed="true"]')!.textContent).toBe("On");
    expect(host.querySelector(".read-as")!.textContent).toContain("“pack” → Packs");
  });

  it("filters changed while the query is being read are the ones searched (CodeRabbit, PR #8)", async () => {
    let answer!: (p: ParsedQuery) => void;
    api.parseQuery.mockReturnValueOnce(new Promise<ParsedQuery>((resolve) => { answer = resolve; }));
    await act(async () => root.render(<SearchPage onToast={() => undefined} />));

    await submit("knight");  // its read is slow
    const preset = [...host.querySelectorAll<HTMLButtonElement>("button.pill")].find((b) => b.textContent === "Game assets")!;
    await act(async () => { preset.click(); });
    await act(async () => answer({ original: "knight", q: "knight", media_types: [], packs: false, picks: [] }));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });

    expect(searchStream).toHaveBeenCalledTimes(1);
    expect(searchStream.mock.calls[0][0]).toMatchObject({
      q: "knight", media: ["audio", "texture", "model", "font", "icon", "sprite"], packs: true,
    });
    expect(preset.getAttribute("aria-pressed")).toBe("true");
  });

  it("Game assets picks its media and packs, and searches again once", async () => {
    api.parseQuery.mockResolvedValueOnce({ original: "knight", q: "knight", media_types: [], packs: false, picks: [] } satisfies ParsedQuery);
    await act(async () => root.render(<SearchPage onToast={() => undefined} />));
    await submit("knight");
    const preset = [...host.querySelectorAll<HTMLButtonElement>("button.pill")].find((b) => b.textContent === "Game assets")!;
    await act(async () => { preset.click(); });

    expect(searchStream).toHaveBeenCalledTimes(2);
    expect(searchStream.mock.calls[1][0]).toMatchObject({
      q: "knight", media: ["audio", "texture", "model", "font", "icon", "sprite"], packs: true,
    });
    expect(preset.getAttribute("aria-pressed")).toBe("true");
  });
});
