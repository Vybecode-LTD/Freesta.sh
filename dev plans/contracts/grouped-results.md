---
feature: grouped-results
status: done
approved: 2026-11-01 (decision 0003: the owner accepted plan §3·4 and its order; "First job: PR #7" 2026-11-02)
plan: dev plans/2026-11-01-packs-web-admin-plan.md (§3 ask 4, §4 step 3)
pr: 7
---

# Contract: results grouped by category, and query words that pick categories

## 1. Goal
With two or more media selected, both apps show results in one section per category, in a fixed order, each with up
to 8 cards, a "Show all (n)" toggle and a jump bar with the counts. Words like "sfx" or "font" in a query select
their category and show as chips; removing a chip searches the word as a word again. One category selected looks
as it does today.

## 2. Interfaces
- **`shared/categories.json`** (hand-edited source): `{"categories": [{"id": MediaType, "label": str, "words": [str]}]}`.
  The array's order is the display order. `words` are lowercase; a phrase has spaces ("sound effects").
- **Engine** `freestash/src/freestash/query_words.py`: `parse_query(text: str, keep: Iterable[str] = ()) -> ParsedQuery`.
  - Tokens split on whitespace; a token matches with its surrounding punctuation stripped, case-insensitive. Phrases
    of up to 3 tokens match longest first. A word in `keep` (any case) is never picked.
  - After removing the picks, filler at either end goes: `a an the of for with and or`.
  - If nothing would be left, nothing is picked (the whole text is searched).
  - `media_types` = the picks' categories, distinct, in category order.
- **Models** (`models.py` ↔ `web/src/lib/types.ts` ↔ desktop `Models.cs`):
  `QueryPick {word: str (as typed), media_type: MediaType}` ·
  `ParsedQuery {original: str, q: str, media_types: list[MediaType], picks: list[QueryPick]}`.
- **HTTP** `GET /api/search/parse?q=<text>&keep=<word>&keep=…` → `ParsedQuery`. Takes `User`, like search. `q` ≤ 500
  characters, at most 20 `keep` (422 past either). Doesn't count against the search cap. `/api/search*` are unchanged.
- **CLI** `freestash search` gains `--literal`. Without `--media` and without `--literal` the query is parsed, and the
  picks print as `Read "sfx" as Audio · searching "rain" (--literal keeps every word)`. An explicit `--media` wins.
- **MCP** `search_assets` gains `literal: bool = False`; it parses only when `media_types` is omitted. The response
  gains `searched_for: str` and `read_as: [{word, media_type}]`.
- **Web**
  - `lib/categories.ts` (generated): `CATEGORIES: readonly {id: MediaType; label: string}[]`. `MEDIA_TYPES` derives from it.
  - `lib/results.ts`:
    - `interleave(byProvider)` (moved from `SearchPage`) and `SECTION_SIZE = 8`.
    - `isGrouped(media) = media.length > 1`.
    - `groupResults(ordered, expanded: ReadonlySet<MediaType>): ResultSection[]`, with
      `ResultSection {id, label, total, items}`. Only non-empty sections, in category order.
    - `Reading {original, q, keep, picks, before}`.
    - `readQuery(parsed, media, prev)` and `dropPick(parsed, reading)` → `{reading, media}`.
    - `needsParse(text, reading)`: false when the text is unchanged since the last parse.
  - `api.parseQuery(q, keep)`. `components/ResultSections.tsx`
    `{results, media, onOpen}` (the jump bar, the sections and their toggles). `components/QueryChips.tsx`
    `{picks, onRemove}`.
- **Desktop**
  - `Freestash.Client/Categories.g.cs` (generated): `record Category(MediaType Id, string Label)`, `Categories.All`.
  - `Freestash.Client/ResultGroups.cs`: static `Interleave`, `SectionSize`, `IsGrouped`, `Group` → `ResultSection(Id, Label,
    Total, Items)`, and `QueryReading` with `Read`, `Drop`, `NeedsParse` (the web's rules, same names in C# case).
  - `IFreestashApi.ParseQueryAsync(string q, IReadOnlyList<string> keep, CancellationToken)`.
  - `SearchViewModel` gains `Sections`, `Picks`, `IsGrouped`, `RemovePickCommand`, `ToggleSectionCommand`, `JumpCommand`.
    The Media options come from `Categories.All`.
- **Words, the same in both apps:** chip row eyebrow `Read as`; chip `“sfx” → Audio` with a ×. The chip's tooltip /
  aria-label: `Search “sfx” as a word, not as Audio`. Section head `Images` + count. Toggle `Show all (24)` /
  `Show fewer`. Jump bar items `Images 24`.

## 3. Data
None.

## 4. Files
- `shared/categories.json` (new) → `scripts/export_shared.py` writes `src/freestash/categories_data.py`,
  `web/src/lib/categories.ts` and `freestash-desktop/src/Freestash.Client/Categories.g.cs`.
- **Engine:** `query_words.py`, `models.py`, `api/app.py`, `cli.py`, `mcp_server.py`.
- **Tests:** `tests/test_query_words.py`, `test_api.py`, `test_cli.py`, `test_parity.py` (categories ↔ `MediaType`).
- **Web:** `lib/results.ts` + `results.test.ts`, `lib/api.ts`, `lib/types.ts`, `pages/SearchPage.tsx`, the two
  components, `styles.css`.
- **Desktop:** `Models.cs`, `FreestashApi.cs`, `ResultGroups.cs`, `SearchViewModel.cs`, `SearchView.axaml(.cs)`; tests
  `ResultGroupsTests.cs`, `ContractTests.cs`.
- `shared/parity.json`: rows `categories`, `grouped-results`, `query-words`.

## 5. Conventions this follows
Root `CLAUDE.md` (the parity rule; generated files are never hand-edited); `freestash/CLAUDE.md` ground rule 7 (the
three model mirrors); the export pattern of `shared/design-tokens.json`; `verify-real-pass` (rendered contrast).

## 6. Non-goals
- Packs leading each section, the "Packs" switch and pack words ("pack", "bundle"): PR #8 adds `is_pack`.
- Brush, shape and sprite categories: PR #8 adds the media types; their rows go into `categories.json` then.
- A web-results section: the web-search PR.
- Quoting to keep a word literal, and query words in other languages.
- Grouping on the server: the engine's results stay one interleaved list.

## 7. Acceptance
- `test_query_words.py`: "medieval sword sfx" → q "medieval sword", picks sfx/audio; "sound of rain" → "rain"; "sound
  effects" as a phrase; keep; only category words → no picks; punctuation and case; categories in order.
- `test_parity.py`: `categories.json` ids are exactly `MediaType`'s values; no word in two categories; all lowercase.
- `test_api.py`: the parse route (shape, keep, limits, sign-in required). `test_cli.py`: `--literal` and the read-as line.
- `results.test.ts` and `ResultGroupsTests.cs` test the same cases: order, 8 then "Show all", expanded, flat with one
  medium, `readQuery`/`dropPick`/`needsParse`.
- `export_shared.py --check` clean. Live: a dev server search for "rain sfx" with Images + Fonts selected shows the
  chip and Audio only; "lighthouse" with three media shows sections and a jump bar. Rendered-contrast gate on the
  search page in both themes at 1440 and 390, with a positive control. Desktop snapshot of the same states.

## 8. Open questions
None. The word lists are a first cut; the chips make a wrong pick one click to undo.

## Changes after approval
- 2026-11-02 (review, Codex): `keep` words are normalised like query tokens (punctuation stripped), so a chip whose
  word was typed as "SFX!" can be removed. The CLI's read-as line goes to stderr, so `--json` stdout stays one JSON
  document.
- 2026-11-02 (review, CodeRabbit): only the latest submit or chip removal applies its read (`intentRef` on the web,
  `_intent` on the desktop); an older read that answers late is dropped. Tests: `pages/SearchPage.test.tsx` and the
  snapshot tool's stale-read check.
- 2026-11-02 (build): `groupResults(ordered, expanded)` / `ResultGroups.Group(ordered, expanded)` lost the unused `media`
  argument. The desktop's jump bar sits under the results heading, above the scrolling results (the window scrolls
  only the results; the web's page scrolls whole). Both apps' example searches are now one list, and three of them
  use query words ("weathered concrete texture", "rain on a tin roof sfx", "monospace font"); the desktop's
  hard-coded media switches for its examples are gone.
