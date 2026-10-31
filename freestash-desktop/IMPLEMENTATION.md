# IMPLEMENTATION.md — ordered runbook

Work top to bottom; update **Last Completed Task** in `CLAUDE.md` after each.

## D0 — Run it on Windows

1. Install the .NET 10 SDK. Have the `freestash` repo installed: `python -m pip install -e ".[all]"` in it.
2. `dotnet test --project tests/Freestash.Client.Tests` → 21 passed.
3. `dotnet run --project src/Freestash.Desktop`. The status pill should go yellow ("Starting engine…") then green.
   If it goes red, open Settings → Engine: check the Python command (`python`, `py`, or a venv path like
   `C:\dev\freestash\.venv\Scripts\python.exe`) and the engine log.
4. Smoke test: search "lighthouse" → open a result → Download → Downloads shows SIDECAR + LEDGER pills →
   drag the finished file onto the desktop (the `.license.json` comes along).
5. Paste a few links into Downloads, pick a folder, download. Toggle "Watch clipboard", copy a URL in a browser,
   confirm the banner appears.

**Done when:** all of the above works on Windows 11 with native caption buttons sitting cleanly in the
title bar's reserved 150px on the right. Adjust `MainWindow.axaml.cs` margins if Windows 10 differs.

## D1 — Windows polish

- Verify DPAPI secrets survive an app restart (and that copying `secrets.bin` to another account yields an
  empty store + `.unreadable` backup, by design).
- Mica/Acrylic: `TransparencyLevelHint="Mica, AcrylicBlur, None"` on MainWindow with the canvas brush at ~85%
  alpha in Ember Dark. Gate it behind a Settings toggle (some GPUs make it muddy).
- Taskbar progress for active downloads (Windows `ITaskbarList3` via a tiny interop, or skip if it fights Avalonia).
- App icon: replace `Assets/freestash.ico` with a designed mark (current one is generated: ember dot on graphite).
- Installer: MSIX or Velopack (Velopack recommended: delta updates, no admin).

## D2 — Live font previews

Font cards currently show "Aa" in Geist. Download the Fontsource TTF (`https://cdn.jsdelivr.net/fontsource/fonts/{id}@latest/latin-400-normal.ttf`)
to the cache and register it with an Avalonia 12 custom `FontCollection` so cards render in the actual face.

## D3 — Audio preview

Inline play/stop on audio cards and in the detail panel (Freesound/NASA/Internet Archive previews). Options:
LibVLCSharp.Avalonia (heavy, robust) or NAudio (Windows-only, light). Add a waveform strip via a quick peak scan.
This is the big one for granular-synth sample hunting.

## D4 — Secrets on macOS/Linux

Swap the AES-GCM key file for Keychain (macOS) / libsecret (Linux). `SecretStore` already writes a version byte;
add format 3 and migrate on first load.

## D5 — Team sign-in

Remote mode currently takes a pasted Supabase access token. Add the magic-link flow: open the browser to the team
web app's login with a `freestash-desktop://auth` redirect (register the URI scheme), receive the session, store the
refresh token in `SecretStore`, refresh on 401.

## D6 — Engine contract additions (in the `freestash` repo)

- `POST /api/ledger`: accept `sha256`, `local_path`, `bytes` so desktop downloads record the same detail as CLI downloads.
- `GET /api/assets/{uid}` for providers without a detail endpoint relies on the server's recent-results cache;
  if the server restarted, it 404s. Have the desktop send the asset back (`POST /api/assets/resolve`) as a fallback.

## D7 — Nice-to-haves

- Command palette (Ctrl+K already focuses search; extend to "go to page / switch use case / open downloads").
- Watch folders: pick a project folder, flag files without a `.license.json`, offer to look them up.
- Virtualized results (switch the AdaptiveGrid ItemsControl to a virtualizing panel once result sets exceed ~500).
- Snapshot-diff CI: run `tools/Freestash.Desktop.Snapshots` against a recorded-fixture engine and compare PNGs.
