"""Attribution strings in TASL form (Title, Author, Source, License), plain text and HTML.

Always generated, even for CC0/PD where credit isn't required: a courtesy credit costs nothing
and keeps provenance attached to the asset wherever it travels.
"""

from __future__ import annotations

from html import escape

from freestash.licenses.catalog import lookup
from freestash.models import Asset

_PLATFORM_STYLE = {
    # The platforms' own preferred credit formats.
    "UNSPLASH": "Photo by {creator} on Unsplash",
    "PEXELS": "Photo by {creator} on Pexels",
    "PIXABAY": "Image by {creator} from Pixabay",
}


def _provider_name(provider_id: str) -> str:
    from freestash.providers import get_provider_info  # lazy: avoids an import cycle

    info = get_provider_info(provider_id)
    return info.name if info else provider_id


def build_attribution(asset: Asset) -> str:
    lic = lookup(asset.license.id)
    creator = (asset.creator or "").strip() or None

    if lic.id in _PLATFORM_STYLE:
        return _PLATFORM_STYLE[lic.id].format(creator=creator or "unknown creator")

    if asset.attribution_hint and lic.family != "public_domain":
        return asset.attribution_hint

    title = f"“{asset.title.strip()}”" if asset.title else "Untitled"
    by = f" by {creator}" if creator else ""
    source = _provider_name(asset.provider)

    if lic.family == "public_domain":
        return f"{title}{by}, via {source} ({asset.license.label})."

    lic_part = asset.license.label + (f" ({asset.license.url})" if asset.license.url else "")
    src_part = f" Source: {asset.landing_url}" if asset.landing_url else f" via {source}."
    return f"{title}{by} is licensed under {lic_part}.{src_part}".rstrip()


def build_attribution_html(asset: Asset) -> str:
    lic = lookup(asset.license.id)
    title = escape(asset.title or "Untitled")
    title_html = f'<a href="{escape(asset.landing_url)}">{title}</a>' if asset.landing_url else title
    creator = escape(asset.creator) if asset.creator else None
    if asset.creator and asset.creator_url:
        creator = f'<a href="{escape(asset.creator_url)}">{creator}</a>'
    by = f" by {creator}" if creator else ""
    lic_label = escape(asset.license.label)
    lic_html = f'<a href="{escape(asset.license.url)}">{lic_label}</a>' if asset.license.url else lic_label
    if lic.family == "public_domain":
        return f"&ldquo;{title_html}&rdquo;{by}, via {escape(_provider_name(asset.provider))} ({lic_html})."
    return f"&ldquo;{title_html}&rdquo;{by} is licensed under {lic_html}."
