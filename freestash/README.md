# Freestash · [freesta.sh](https://freesta.sh)

**Federated search for public domain and openly licensed assets, with use-case-aware license verdicts.**

One query hits ~20 sources (The Met, Art Institute of Chicago, Cleveland, SMK, Smithsonian, NASA,
Library of Congress, Europeana, Wikimedia Commons, Openverse, Internet Archive, Poly Haven, ambientCG,
Fontsource, Iconify, V&A, Freesound, Unsplash, Pexels, Pixabay) across images, audio, video, PBR
textures, HDRIs, 3D models, fonts, and icons. Every result gets a **GREEN / YELLOW / RED** verdict for
what you're going to do with it:

| | reference | demo | client | bundled | merch |
|---|---|---|---|---|---|
| Met painting (CC0) | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| Unsplash photo | 🟢 | 🟢 | 🟢 | 🔴 | 🟡 |
| Commons photo (CC BY-SA) | 🟢 | 🟢 | 🟡 | 🟡 | 🟡 |
| Internet Archive clip "PD", dated 2025 | 🟢 | 🟡 | 🟡 | 🟡 | 🟡 |

Downloads come with a `.license.json` sidecar and a ledger entry, and one command writes your
`ATTRIBUTION.md`.

## Quick start

```bash
python -m pip install -e ".[all]"
copy .env.example .env            # set FREESTASH_CONTACT_EMAIL (macOS/Linux: cp)
python -m freestash search "art deco poster" -u demo
python -m freestash serve            # web UI at http://127.0.0.1:8787 (after `cd web && npm i && npm run build`)
claude mcp add freestash -- python -m freestash mcp
```

## Docs

- `CLAUDE.md`: project context and rules (start here if you're Claude Code)
- `IMPLEMENTATION.md`: ordered runbook of what's next
- `docs/LICENSE-POLICY.md`: how verdicts are decided
- `docs/PROVIDERS.md`: every source, its quirks, and verification status
- `docs/ARCHITECTURE.md`, `docs/MCP.md`, `docs/WEB.md`, `docs/adr/`

Not legal advice. It's a triage tool that shows its reasoning and errs toward YELLOW.
