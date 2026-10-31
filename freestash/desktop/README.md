# Freestash Desktop (planned): C# / .NET 9 / Avalonia 11

Not started. This is the spec so Claude Code can scaffold it when we get to P6.

## Why a desktop app at all

The web UI covers search and the team ledger. The desktop app earns its place with things a browser can't do:

1. **Drag out with provenance.** Drag a result into Explorer, a DAW, Figma, or an Avalonia/JUCE project
   folder: the file lands *with* its `.license.json` sidecar, and the ledger entry is written.
2. **Watch folders.** Point it at `assets/` in a repo; any file without a sidecar gets flagged, and
   dropping a Freestash result there auto-records it under that project.
3. **Offline collections.** Pull a collection to disk and browse it without network.
4. **Audio-first preview** for sample hunting: waveform, loop region, and keyboard audition of
   Freesound/NASA/Internet Archive results before you take them (pairs with the granular synth work).

## Architecture

- Talks to the Freestash HTTP API only (ADR 0001). Local mode spawns `python -m freestash serve --port 8787`
  as a child process if nothing is listening; team mode points at the hosted URL with a Supabase token.
- MVVM with CommunityToolkit.Mvvm. `HttpClient` + `System.Text.Json` source-generated contexts for the
  models in `src/freestash/models.py` (mirror `web/src/lib/types.ts`).
- SSE client for `/api/search/stream` (read the response stream line by line; same format as the web UI).
- Drag-out: Avalonia `DataObject` with file paths after downloading to a temp dir via `/api/assets/{uid}`
  plus the rendition URL. Write the sidecar next to the file before starting the drag.
- Settings stored in `%APPDATA%/Freestash/settings.json`; token in Windows Credential Manager.

## Suggested structure

```
desktop/
  Freestash.Desktop.sln
  src/Freestash.Desktop/            App, Views, ViewModels
  src/Freestash.Client/             API client, models, SSE reader (reusable, e.g. by SoundPacker)
  tests/Freestash.Client.Tests/
```

`Freestash.Client` as its own library means other C#/Avalonia apps (SoundPacker, KitRoll tooling) can
search and record assets through the same ledger.
