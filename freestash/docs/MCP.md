# MCP server

Register with Claude Code (project scope via `.mcp.json`, or user scope):

```bash
claude mcp add freestash -- python -m freestash mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "freestash": { "command": "python", "args": ["-m", "freestash", "mcp"],
  "env": { "FREESTASH_CONTACT_EMAIL": "you@studio.com" } } } }
```

## Tools

| Tool | What it does |
|---|---|
| `search_assets(query, media_types, use_case, max_tier, providers, limit_per_provider, page)` | Federated search, compact results with tier, reasons, obligations, attribution |
| `get_asset(uid)` | Full detail + renditions + verdicts for all five use cases |
| `download_asset(uid, use_case, project, dest_dir, rendition, prefer, force)` | File + `.license.json` sidecar + ledger entry. Refuses RED unless `force` |
| `check_license(license, trust, media_type, year)` | Triage any license string or URL |
| `export_credits(project, format)` | ATTRIBUTION.md / credits HTML / CSV for a project |
| `list_providers()` | Sources, coverage, enabled status |
| `public_domain_cutoff()` | Current US PD years for works vs. recordings |

The server's `instructions` tell the model to always pass the right `use_case`, relay obligations,
and never present RED results as usable.

## Example prompts

- "Use freestash to find 8 GREEN hero images for a *bundled* luxury-hotel website template. Download the
  best 4 into `./public/img` under project `aurora`, then write ATTRIBUTION.md."
- "Find CC0 rain and thunder field recordings for my granular synth's factory library (use case: bundled)."
- "Is 'CC BY-NC-SA 3.0' OK for a client site? Use check_license."
