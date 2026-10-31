"""Download an asset with provenance: the file, a `<file>.license.json` sidecar, and a ledger entry."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from freestash.models import LedgerEntry, Rendition, ScoredAsset
from freestash.providers import build
from freestash.search import Freestash
from freestash.store import Store, entry_from_scored

_ORIGINAL = re.compile(r"\b(orig(inal)?|full|max|raw|native|16k|8k)\b", re.I)
_LARGE = re.compile(r"\b(large\w*|print|1686w?|1600px|4k|2k|regular|hq|high)\b", re.I)


class DownloadTooLarge(RuntimeError):
    pass


class DownloadBlocked(RuntimeError):
    """The file host refused an automated download (often bot protection on datacenter IPs). Never work around it."""


@dataclass
class DownloadResult:
    path: Path
    sidecar: Path
    entry: LedgerEntry
    rendition: Rendition


def slugify(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:max_len].rstrip("-") or "asset"


def pick_rendition(renditions: list[Rendition], prefer: str = "large", max_bytes: int | None = None) -> Rendition | None:
    """prefer: 'large' (best size under the cap), 'original', or 'small'. Explicit labels win in `choose`."""
    usable = [r for r in renditions if not (max_bytes and r.bytes and r.bytes > max_bytes)]
    if not usable:
        return None

    def klass(r: Rendition) -> int:
        if _ORIGINAL.search(r.label):
            return 0
        if _LARGE.search(r.label):
            return 1
        return 2

    order = {"original": (0, 1, 2), "large": (1, 0, 2), "small": (2, 1, 0)}.get(prefer, (1, 0, 2))
    return sorted(usable, key=lambda r: (order.index(klass(r)), -(r.bytes or 0)))[0]


def _filename(scored: ScoredAsset, rendition: Rendition, content_type: str | None) -> str:
    ext = Path(unquote(urlparse(rendition.url).path)).suffix.lower()
    if not ext or len(ext) > 6:
        ext = mimetypes.guess_extension((content_type or rendition.mime or "").split(";")[0].strip()) or ".bin"
    sid = slugify(scored.asset.source_id, 40)
    return f"{slugify(scored.asset.title)}--{scored.asset.provider}-{sid}{ext}"


async def download_asset(
    engine: Freestash,
    scored: ScoredAsset,
    dest: Path,
    *,
    rendition_label: str | None = None,
    prefer: str = "large",
    project: str | None = None,
    store: Store | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
) -> DownloadResult:
    if scored.asset.detail_required or not scored.asset.renditions:
        scored = await engine.get_asset(scored.uid, scored.verdict.use_case)

    max_bytes = engine.settings.max_download_mb * 1024 * 1024
    if rendition_label:
        rendition = next((r for r in scored.asset.renditions if r.label == rendition_label), None)
        if not rendition:
            raise LookupError(f"no rendition '{rendition_label}'. Available: {[r.label for r in scored.asset.renditions]}")
    else:
        rendition = pick_rendition(scored.asset.renditions, prefer, max_bytes)
    if not rendition:
        raise LookupError("asset has no downloadable rendition under the size cap")

    dest.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    size = 0
    async with engine.http.raw.stream("GET", rendition.url, headers={"Accept": "*/*"}) as resp:
        if resp.status_code in (401, 403, 429):
            raise DownloadBlocked(
                f"{urlparse(rendition.url).netloc} refused the download (HTTP {resp.status_code}). "
                f"Grab it manually from {scored.asset.landing_url or rendition.url}, then record it with "
                f"`freestash ledger add {scored.uid} --file <path>`.")
        resp.raise_for_status()
        declared = int(resp.headers.get("content-length") or 0)
        if declared > max_bytes:
            raise DownloadTooLarge(f"{declared / 1e6:.0f} MB exceeds the {engine.settings.max_download_mb} MB cap")
        path = dest / _filename(scored, rendition, resp.headers.get("content-type"))
        tmp = path.with_suffix(path.suffix + ".part")
        with tmp.open("wb") as fh:
            async for chunk in resp.aiter_bytes(1 << 16):
                size += len(chunk)
                if size > max_bytes:
                    fh.close()
                    tmp.unlink(missing_ok=True)
                    raise DownloadTooLarge(f"stream passed the {engine.settings.max_download_mb} MB cap")
                sha.update(chunk)
                fh.write(chunk)
        tmp.replace(path)

    try:
        await build(scored.asset.provider, engine.http, engine.settings).on_download(scored.asset)
    except Exception:  # noqa: BLE001 - a failed analytics ping must not fail the download
        pass

    entry = entry_from_scored(scored, project=project, file_url=rendition.url, sha256=sha.hexdigest(),
                              local_path=str(path), size=size, user_id=user_id, team_id=team_id)
    if store:
        entry = store.add_entry(entry)

    sidecar = path.with_name(path.name + ".license.json")
    sidecar.write_text(json.dumps({
        "freestash_sidecar": 1,
        "file": path.name,
        "sha256": entry.sha256,
        "retrieved_at": entry.retrieved_at.isoformat(),
        "source_url": rendition.url,
        "landing_url": scored.asset.landing_url,
        "license": scored.asset.license.model_dump(mode="json"),
        "trust": scored.asset.trust.value,
        "use_case": scored.verdict.use_case.value,
        "tier": scored.verdict.tier.value,
        "attribution": scored.verdict.attribution,
        "obligations": scored.verdict.obligations,
        "reasons": scored.verdict.reasons,
        "asset": scored.asset.model_copy(update={"renditions": [rendition]}).model_dump(mode="json"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return DownloadResult(path=path, sidecar=sidecar, entry=entry, rendition=rendition)
