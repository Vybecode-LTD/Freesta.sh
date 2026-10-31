# Design

Two looks from one token set (`src/Freestash.Desktop/Services/ThemeManager.cs`); every XAML color is a DynamicResource.

**Ember Dark.** The VybeCod.ing identity: `#0A0A0A` canvas, surfaces stepping up in warm greys (`#131211` → `#191816`
→ `#211F1C`), Ember `#E8440A` accent with a soft glow on the brand mark, an ambient accent radial in the top-left.

**Machined Light.** Warm-graphite canvas (`#D3CEC6`, not white), raised "machined" surfaces with a white top-edge
highlight over soft warm shadows, carved inset inputs, champagne hairline (`#B89A5E`) reserved for the DESKTOP tag.

**Accents.** Ember `#E8440A`, Iris `#7C6CF2`, Teal `#12A594`, Cobalt `#3B6CF6`. Fluent's `SystemAccentColor*` follow,
so toggles, progress bars, and focus states match.

**Type.** Geist (UI) + JetBrains Mono (labels, metadata, captions in tracked caps). Both bundled, OFL.

**Surfaces.** `Border.card` (16px radius, card shadow), `Border.raised` (12px, raised shadow), `Border.inset`
(carved), `Border.pill`, `Border.tier.{green|yellow|red}` (+ `.overlay` frosted variant for badges on images).

**Motion.** Cards lift 3px on hover (180ms cubic-out), thumbnails fade in over 220ms, button backgrounds cross-fade 120ms.

**Layout.** 232px nav rail; pages sit in a rounded inset panel (18px radius) so the window reads as a single object.
Result cards use `AdaptiveGrid`: as many columns as fit at 228px min, stretched to fill (no ragged right edge).
