// GENERATED from shared/categories.json by freestash/scripts/export_shared.py. Don't edit; edit the JSON.
import type { MediaType } from "./types";

/** The result categories in display order: the Media filter, the sections and the jump bar. */
export const CATEGORIES: readonly { id: MediaType; label: string }[] = [
  { id: "image", label: "Images" },
  { id: "audio", label: "Audio" },
  { id: "video", label: "Video" },
  { id: "texture", label: "Textures" },
  { id: "hdri", label: "HDRIs" },
  { id: "model", label: "3D" },
  { id: "font", label: "Fonts" },
  { id: "icon", label: "Icons" },
  { id: "brush", label: "Brushes" },
  { id: "shape", label: "Shapes" },
  { id: "sprite", label: "Sprites" },
];

/** One-click media selections ("Game assets"); `packs` turns the Packs switch on too. */
export const PRESETS: readonly { id: string; label: string; hint: string; media: readonly MediaType[]; packs: boolean }[] = [
  { id: "game-assets", label: "Game assets", hint: "Sprites, 3D, textures, audio, icons and fonts, with packs",
    media: ["audio", "texture", "model", "font", "icon", "sprite"], packs: true },
];
