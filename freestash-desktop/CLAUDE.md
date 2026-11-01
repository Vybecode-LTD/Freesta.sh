# CLAUDE.md — Freestash Desktop

The desktop app of **Freesta.sh** (monorepo root: `../CLAUDE.md`, read it first: the web/desktop parity rule
lives there). Same account, same screens, same look as the website. C# / .NET 10 / **Avalonia 12.1.4**,
MVVM with CommunityToolkit.Mvvm 8.4 (partial-property style).

Verified 2026-10-31: 0 warnings / 0 errors, 27 tests pass (33 on 2026-11-01), every screen rendered headless (`docs/screenshots/`),
and sign-up + key/pref sync proven end to end against a live accounts server. Not yet driven live on screen.

**Start here:** `IMPLEMENTATION.md` is the ordered runbook. Work it top to bottom.

---

## Ground rules

1. **The desktop app never reimplements the engine.** Search, license verdicts, trust, attribution all come
   from the Freestash HTTP API (ADR 0001 in the freestash repo). If a verdict looks wrong, fix it in `freestash`.
2. **Never work around a host's bot protection.** 401/403/429 on a download → `DownloadStatus.Blocked` +
   "Open in browser". No UA spoofing, no retries with a different identity. Hard rule.
3. **Avalonia 12, not 11.** Things that changed and *will* bite you if you paste v11 code:
   - Drag/drop + clipboard: `DataTransfer` / `DataTransferItem.CreateFile()` / `DragDrop.DoDragDropAsync(PointerPressedEventArgs, …)`,
     `e.DataTransfer.Contains(DataFormat.Text)` / `TryGetText()`. `DataObject`, `DataFormats.*`, `GetFileNames()` are gone.
   - Clipboard: `clipboard.TryGetTextAsync()` / `SetTextAsync()` (extension methods).
   - Window chrome: `ExtendClientAreaToDecorationsHint` + `WindowDecorationProperties.ElementRole="TitleBar"`;
     `ExtendClientAreaChromeHints` / `SystemDecorations` are gone.
   - `TextBox.Watermark` → `PlaceholderText`. Compiled bindings are on by default (every view has `x:DataType`).
   - `x:DataType` can't name generic types → filter options derive from non-generic `OptionBase`.
   - No `Avalonia.Diagnostics` package (removed in v12).
   - Headless tests use xUnit **v3**; `dotnet test` on .NET 10 needs MTP (`global.json` opts in).
4. **Every color is a DynamicResource set in `Services/ThemeManager.cs`** from the generated
   `Services/DesignTokens.g.cs` (`../shared/design-tokens.json`; never hand-edit the .g.cs). Glass/Frost × four accents.
   Words never use `TextFaintBrush` (3:1); `TextBlock.faint` already maps to the readable secondary colour.
5. **Engine threads ≠ UI thread.** `DownloadJob` raises PropertyChanged on worker threads; the UI binds to
   `DownloadItemViewModel`, which re-raises on the dispatcher. Keep that pattern for anything async.
6. **Secrets** live only in `SecretStore` (DPAPI on Windows, AES-GCM + 0600 key file elsewhere), never in
   `settings.json`, never in logs. The account session (`SessionStore`, `FREESTASH_SESSION`) is never passed to the local engine, and its token goes
   only to the server that issued it (`TokenFor(uri)`; tested).
8. **Hosted by default.** New installs use `https://freesta.sh` and show `SignInView` until signed in; keys and
   preferences then live in the account (`AccountClient`). The local Python engine is the advanced option.
7. Python CLI commands use `python -m …` (the owner's machine has no pip/python scripts on PATH).

## Commands

```bash
dotnet build Freestash.Desktop.sln
dotnet test --project tests/Freestash.Client.Tests        # 33 tests, ~3s, no network
dotnet run --project src/Freestash.Desktop                # the app (auto-starts `python -m freestash serve`)

# visual check: render every screen to PNG against a running engine
python -m freestash serve --port 8787                     # in the freestash repo
dotnet run --project tools/Freestash.Desktop.Snapshots -- http://127.0.0.1:8787 docs/screenshots [http://127.0.0.1:8790]
# third arg = an accounts-mode server (../freestash/scripts/dev_accounts.py): adds sign-in, sign-up and sync checks
# FREESTASH_DESKTOP_HOME=<folder> runs the real app with its own settings/session (keeps your own clean)

# release build (Windows, self-contained single file)
dotnet publish src/Freestash.Desktop -c Release -r win-x64 --self-contained -p:PublishSingleFile=true
```

## Layout

```
src/Freestash.Client/          UI-free core, reusable by other C# apps (SoundPacker, KitRoll tooling…)
  Models.cs                 mirrors freestash models.py (snake_case JSON, lowercase enums)
  FreestashApi.cs              IFreestashApi + FreestashApiClient (+ SSE streaming search)
  Sse.cs                    Server-Sent Events reader
  Downloads/                DownloadEngine (queue, Range resume, SHA-256, blocked detection),
                            DownloadJob, FileNames, LinkParser, Sidecar (.license.json)
  Settings/                 AppSettings, SettingsStore, SecretStore (encrypted), ProviderKeys
  Engine/EngineHost.cs      health check + spawn/stop `python -m freestash serve` with keys as env vars
src/Freestash.Desktop/         Avalonia app
  Services/                 AppServices (composition root), ThemeManager, ImageLoader, PlatformServices, ToastService
  Controls/                 Icon (stroke icons), AsyncImage (remote thumbs + SVG), AdaptiveGrid (responsive cards)
  Styles/                   Controls.axaml (all control styling), Icons.axaml (24×24 stroke geometry)
  ViewModels/ Views/        one per page: Search, AssetDetail, Collections, Downloads, Ledger, LicenseCheck, Sources, Settings
tests/Freestash.Client.Tests/  contract tests against payloads produced by the real Python API (Samples/)
tools/Freestash.Desktop.Snapshots/  headless Skia renderer → PNGs
```

## Key decisions

- **Hosted engine + account by default** (decision `../docs/decisions/0001`). Local engine sidecar optional:
  `EngineHost` launches the Python engine with the locally stored keys as environment variables.
- **Key help comes from the engine's catalog**, embedded from `../shared/provider-keys.json` (`ProviderKeys.All`).
- **Downloads happen in C#**, not via the API: the desktop app writes the file + sidecar locally, then records the
  ledger entry via `POST /api/ledger` (when "Record in ledger" is on).
- **Sidecars match the Python CLI's format** (`freestash_sidecar: 1`), so `freestash audit` can read both.
- **Openverse thumbnails** go to the direct CDN URL, not Openverse's `/thumb/` proxy (20s+ at times).

---

## Last Completed Task

**2026-10-31: one account with the web, Aperture redesign (PR #1, merged 2026-11-01).**
Sign-in screen; hosted engine default; keys + prefs synced with the account; key help under every input;
rail + lens + `ApertureRing` + spectrum + glass cards; Geist Mono; 27 tests. Live on-screen check still owed
(the owner declined computer-use this session): see `../docs/HANDOFF.md`.
