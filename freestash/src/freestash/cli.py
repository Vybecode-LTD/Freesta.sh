"""Freestash CLI. Run as `freestash ...` or `python -m freestash ...`."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from freestash.categories_data import CATEGORIES
from freestash.config import get_settings
from freestash.export import attribution_markdown, credits_html, ledger_csv
from freestash.licenses import evaluate_all, normalize_license, us_public_domain_cutoff
from freestash.models import Asset, MediaType, Tier, Trust, UseCase
from freestash.models import SearchQuery as Q
from freestash.providers import PROVIDERS

app = typer.Typer(help="Freestash: federated search for public domain and openly licensed assets.", no_args_is_help=True)
ledger_app = typer.Typer(help="The license ledger: every asset you've actually taken.", no_args_is_help=True)
app.add_typer(ledger_app, name="ledger")
admin_app = typer.Typer(help="Site admins of the hosted app. Run it on the server (railway ssh); the account must exist.",
                        no_args_is_help=True)
app.add_typer(admin_app, name="admin")
console = Console()

TIER_STYLE = {Tier.GREEN: "bold green", Tier.YELLOW: "bold yellow", Tier.RED: "bold red"}
TIER_DOT = {Tier.GREEN: "[green]●[/]", Tier.YELLOW: "[yellow]●[/]", Tier.RED: "[red]●[/]"}


def _run(coro):
    return asyncio.run(coro)


@app.command()
def search(
    q: Annotated[str, typer.Argument(help="What you're looking for")],
    media: Annotated[list[MediaType], typer.Option("--media", "-m", help="Repeatable. Default: image")] = None,  # type: ignore[assignment]
    use: Annotated[UseCase, typer.Option("--use", "-u", help="What it's for; drives the license verdict")] = UseCase.DEMO,
    max_tier: Annotated[Tier, typer.Option("--max-tier", "-t", help="Hide results worse than this")] = Tier.YELLOW,
    provider: Annotated[list[str], typer.Option("--provider", "-p", help="Repeatable. Default: all enabled")] = None,  # type: ignore[assignment]
    limit: Annotated[int, typer.Option("--limit", "-n", help="Per provider")] = 8,
    page: int = 1,
    as_json: Annotated[bool, typer.Option("--json", help="Raw JSON output")] = False,
    literal: Annotated[bool, typer.Option("--literal", help='Search every word, even "sfx" or "font"')] = False,
) -> None:
    """Search every enabled source at once and score results for your use case.

    Without --media, words like "sfx", "font" or "3d model" pick the media and leave the query."""
    from freestash.query_words import parse_query
    from freestash.search import Freestash

    if not media and not literal:
        parsed = parse_query(q)
        if parsed.picks:
            labels = {c["id"]: c["label"] for c in CATEGORIES}
            read = ", ".join(f'"{p.word}" as {labels[p.media_type.value]}' for p in parsed.picks)
            console.print(f'[dim]Read {read} · searching "{parsed.q}" (--literal keeps every word)[/]', soft_wrap=True)
            q, media = parsed.q, parsed.media_types
    query = Q(q=q, media_types=media or [MediaType.IMAGE], use_case=use, max_tier=max_tier,
              providers=provider or None, limit_per_provider=limit, page=page)

    async def go():
        async with Freestash(persist_recent=True) as engine:
            return await engine.search(query)

    with console.status(f"Searching for [bold]{q}[/] across sources…"):
        resp = _run(go())
    if as_json:
        typer.echo(resp.model_dump_json(indent=2))
        return

    table = Table(show_lines=False, header_style="bold", title=f"{len(resp.results)} results · use case: {use.value}")
    table.add_column("", width=1)
    table.add_column("uid", style="cyan", no_wrap=True, max_width=34)
    table.add_column("title", max_width=44)
    table.add_column("type", style="dim")
    table.add_column("license", max_width=26)
    table.add_column("trust", style="dim")
    for s in resp.results:
        a = s.asset
        table.add_row(TIER_DOT[s.verdict.tier], s.uid, a.title, a.media_type.value, a.license.label, a.trust.value)
    console.print(table)
    health = "  ".join(f"[green]{p.provider}[/]·{p.count}" if p.ok else f"[red]{p.provider}✗[/]" for p in resp.providers)
    console.print(f"[dim]sources:[/] {health}")
    if resp.hidden_by_tier:
        console.print(f"[dim]{resp.hidden_by_tier} result(s) hidden above --max-tier {max_tier.value}[/]")
    failed = [p for p in resp.providers if not p.ok]
    for p in failed:
        console.print(f"[dim red]  {p.provider}: {p.error}[/]")
    console.print("[dim]Next: freestash show <uid>  ·  freestash download <uid> -u <use> --project <name>[/]")


def _verdict_table(asset: Asset) -> Table:
    t = Table(header_style="bold", show_lines=True)
    t.add_column("use case")
    t.add_column("tier")
    t.add_column("why / obligations", max_width=90)
    for use, v in evaluate_all(asset).items():
        body = "\n".join(v.reasons + [f"→ {o}" for o in v.obligations])
        t.add_row(use.value, f"[{TIER_STYLE[v.tier]}]{v.tier.value.upper()}[/]", body)
    return t


@app.command()
def show(uid: Annotated[str, typer.Argument(help="provider:source_id from a search")],
         as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Full detail for one asset, with a verdict for every use case."""
    from freestash.search import Freestash

    async def go():
        async with Freestash(persist_recent=True) as engine:
            return await engine.get_asset(uid)

    scored = _run(go())
    a = scored.asset
    if as_json:
        typer.echo(a.model_dump_json(indent=2))
        return
    meta = [f"[bold]{a.title}[/]", f"{a.creator or 'Unknown creator'} · {a.date or 'n.d.'}",
            f"License: {a.license.label}  ({a.license.url or 'no URL'})", f"Trust: {a.trust.value}",
            f"Source: {a.landing_url or '-'}"]
    if a.source_name:
        meta.append(f"Via: {a.source_name}")
    console.print(Panel("\n".join(meta), title=scored.uid, border_style="cyan"))
    console.print(_verdict_table(a))
    if a.renditions:
        r = Table("rendition", "size", "url", header_style="bold")
        for x in a.renditions[:20]:
            dims = f"{x.width}×{x.height}" if x.width and x.height else (f"{x.bytes / 1e6:.1f} MB" if x.bytes else "")
            r.add_row(x.label, dims, x.url)
        console.print(r)
    console.print(f"[dim]Attribution:[/] {scored.verdict.attribution}")


@app.command()
def download(
    uid: str,
    use: Annotated[UseCase, typer.Option("--use", "-u")] = UseCase.DEMO,
    project: Annotated[str | None, typer.Option("--project", help="Groups ledger entries for credits exports")] = None,
    dest: Annotated[Path | None, typer.Option("--dest", "-d")] = None,
    rendition: Annotated[str | None, typer.Option("--rendition", "-r", help="Exact rendition label (see `show`)")] = None,
    prefer: Annotated[str, typer.Option(help="large | original | small")] = "large",
    force: Annotated[bool, typer.Option("--force", help="Download even if the verdict is RED")] = False,
) -> None:
    """Download a file with a .license.json sidecar and record it in the ledger."""
    from freestash.download import download_asset
    from freestash.search import Freestash
    from freestash.store import Store

    settings = get_settings()

    async def go():
        async with Freestash(persist_recent=True) as engine:
            scored = await engine.get_asset(uid, use)
            if scored.verdict.tier == Tier.RED and not force:
                return scored, None
            target = dest or (settings.resolved_download_dir / (project or "unsorted"))
            return scored, await download_asset(engine, scored, target, rendition_label=rendition, prefer=prefer,
                                                project=project, store=Store(settings=settings))

    try:
        scored, result = _run(go())
    except Exception as exc:  # noqa: BLE001 - show a clean message, not a traceback
        console.print(f"[red]Download failed:[/] {exc}")
        raise typer.Exit(1) from None
    v = scored.verdict
    console.print(f"[{TIER_STYLE[v.tier]}]{v.tier.value.upper()}[/] for {use.value}: " + " ".join(v.reasons))
    if result is None:
        console.print("[red]Not downloaded.[/] Re-run with --force if you have a reason the verdict doesn't know about.")
        raise typer.Exit(1)
    for o in v.obligations:
        console.print(f"  → {o}")
    console.print(f"[green]Saved[/] {result.path}  ({result.entry.bytes or 0:,} bytes, {result.rendition.label})")
    console.print(f"[dim]Sidecar {result.sidecar.name} · ledger id {result.entry.id}[/]")


@app.command()
def check(
    license_text: Annotated[str, typer.Argument(help="License name, SPDX id, or URL, e.g. 'CC BY-SA 4.0'")],
    trust: Annotated[Trust, typer.Option(help="Who is asserting it")] = Trust.UNKNOWN,
    media: Annotated[MediaType, typer.Option("--media", "-m")] = MediaType.IMAGE,
    year: Annotated[int | None, typer.Option(help="Publication year, enables the public-domain date check")] = None,
) -> None:
    """Triage any license string or URL across every use case."""
    is_url = license_text.startswith("http")
    lic = normalize_license(None if is_url else license_text, license_text if is_url else None)
    asset = Asset(provider="manual", source_id="check", title="(license check)", media_type=media, license=lic,
                  trust=trust, year=year)
    console.print(f"Recognized as [bold]{lic.label}[/] ([cyan]{lic.id}[/])")
    console.print(_verdict_table(asset))


@app.command()
def providers() -> None:
    """List sources, what they cover, and whether they're enabled."""
    settings = get_settings()
    t = Table(header_style="bold")
    for col in ("id", "name", "media", "status", "verified"):
        t.add_column(col)
    for cls in PROVIDERS:
        i = cls.info
        if cls.is_enabled(settings):
            status = "[green]on[/]" + (" [dim](key)[/]" if i.key_setting and getattr(settings, i.key_setting, None) else "")
        else:
            status = f"[red]off[/] [dim]needs {i.key_setting.upper() if i.key_setting else '?'}[/]"
        t.add_row(i.id, i.name, ", ".join(sorted(m.value for m in i.media_types)), status,
                  "[green]live[/]" if i.verified_live else "[yellow]docs[/]")
    console.print(t)
    console.print("[dim]verified: live = adapter built against real responses; docs = needs a key, built from docs.[/]")


@app.command("pd-cutoff")
def pd_cutoff() -> None:
    """What's reliably public domain in the US today (and what lands next Jan 1)."""
    today = date.today()
    nxt = date(today.year + 1, 1, 1)
    console.print(f"As of {today:%B %d, %Y}:")
    console.print(f"  • Published works: {us_public_domain_cutoff(MediaType.IMAGE, today)} and earlier")
    console.print(f"  • Sound recordings: {us_public_domain_cutoff(MediaType.AUDIO, today)} and earlier")
    console.print(f"On {nxt:%B} {nxt.day}, {nxt.year}: works from {us_public_domain_cutoff(MediaType.IMAGE, nxt)} and recordings "
                  f"from {us_public_domain_cutoff(MediaType.AUDIO, nxt)} join them.")
    console.print("[dim]US rules only. Unpublished works, foreign works, and renewals have their own rules.[/]")


# ------------------------------------------------------------------------------------- ledger
@ledger_app.command("list")
def ledger_list(project: Annotated[str | None, typer.Option("--project")] = None, limit: int = 50) -> None:
    from freestash.store import Store

    entries = Store().list_entries(project=project, limit=limit)
    t = Table(header_style="bold")
    for col in ("", "retrieved", "project", "title", "license", "use"):
        t.add_column(col)
    for e in entries:
        t.add_row(TIER_DOT[e.tier], f"{e.retrieved_at:%Y-%m-%d}", e.project or "-", e.title[:50], e.license_label, e.use_case.value)
    console.print(t)


@ledger_app.command("add")
def ledger_add(
    uid: str,
    file: Annotated[Path, typer.Option("--file", help="The file you downloaded manually")],
    use: Annotated[UseCase, typer.Option("--use", "-u")] = UseCase.DEMO,
    project: Annotated[str | None, typer.Option("--project")] = None,
) -> None:
    """Record a file you downloaded by hand (writes the sidecar and the ledger entry)."""
    import hashlib

    from freestash.search import Freestash
    from freestash.store import Store, entry_from_scored

    async def go():
        async with Freestash(persist_recent=True) as engine:
            return await engine.get_asset(uid, use)

    scored = _run(go())
    data = file.read_bytes()
    entry = Store().add_entry(entry_from_scored(scored, project=project, sha256=hashlib.sha256(data).hexdigest(),
                                                local_path=str(file.resolve()), size=len(data)))
    sidecar = file.with_name(file.name + ".license.json")
    sidecar.write_text(json.dumps({"freestash_sidecar": 1, "file": file.name, "sha256": entry.sha256,
                                   "retrieved_at": entry.retrieved_at.isoformat(), "landing_url": scored.asset.landing_url,
                                   "license": scored.asset.license.model_dump(mode="json"), "tier": scored.verdict.tier.value,
                                   "use_case": use.value, "attribution": scored.verdict.attribution,
                                   "obligations": scored.verdict.obligations}, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Recorded[/] {file.name} as {scored.verdict.tier.value.upper()} for {use.value} (ledger id {entry.id})")


@ledger_app.command("export")
def ledger_export(
    fmt: Annotated[str, typer.Option("--format", "-f", help="md | html | csv | json")] = "md",
    project: Annotated[str | None, typer.Option("--project")] = None,
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
) -> None:
    """Credits file (ATTRIBUTION.md / credits HTML) or a raw ledger export."""
    from freestash.store import Store

    entries = Store().list_entries(project=project, limit=100_000)
    body = {
        "md": lambda: attribution_markdown(entries, project),
        "html": lambda: credits_html(entries),
        "csv": lambda: ledger_csv(entries),
        "json": lambda: json.dumps([e.model_dump(mode="json") for e in entries], indent=2),
    }[fmt]()
    if out:
        out.write_text(body, encoding="utf-8")
        console.print(f"[green]Wrote[/] {out} ({len(entries)} entries)")
    else:
        typer.echo(body)


# ------------------------------------------------------------------------------------- servers
@app.command()
def serve(host: str = "127.0.0.1", port: int = 8787, reload: bool = False) -> None:
    """Run the web API (FastAPI)."""
    import uvicorn

    uvicorn.run("freestash.api.app:app", host=host, port=port, reload=reload)


@app.command()
def mcp() -> None:
    """Run the MCP server over stdio (for Claude Code / Claude Desktop)."""
    from freestash.mcp_server import main

    main()


if __name__ == "__main__":
    app()


# --------------------------------------------------------------------------------- site admins
def _admin_services():
    from freestash.accounts import AccountService
    from freestash.admin import AdminService
    from freestash.store import Store

    settings = get_settings()
    store = Store(settings=settings)
    return AccountService(store, settings), AdminService(store, settings)


def _set_admin(email: str, value: bool) -> None:
    """Out-of-band on purpose: sign-up doesn't prove an address is yours, so no address makes an admin by itself."""
    accounts, admin = _admin_services()
    user = accounts.find_user(email)
    if user is None:
        console.print(f"[red]No account for {email.strip()}.[/] Sign up on the site first, then run this again.")
        raise typer.Exit(1)
    accounts.set_flags(user.id, is_admin=value)
    admin.audit(None, "user.update", user.email, {"is_admin": value})
    console.print(f"{user.email} is {'now an admin' if value else 'no longer an admin'}.")


@admin_app.command("grant")
def admin_grant(email: Annotated[str, typer.Argument(help="An existing account's email")]) -> None:
    """Make an existing account an admin (the first admin is made this way)."""
    _set_admin(email, True)


@admin_app.command("revoke")
def admin_revoke(email: Annotated[str, typer.Argument(help="An existing account's email")]) -> None:
    """Take admin away from an account."""
    _set_admin(email, False)


@admin_app.command("list")
def admin_list() -> None:
    """Every admin account."""
    accounts, _ = _admin_services()
    for user in accounts.list_admins():
        console.print(user.email)
