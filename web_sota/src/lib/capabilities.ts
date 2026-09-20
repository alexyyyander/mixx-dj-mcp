export type ForkId = "mixxxxx" | "mixxx" | "unknown";

export type FeatureId =
  | "osc_deck_control"
  | "deck_load"
  | "effects_racks"
  | "hotcues"
  | "crossfader"
  | "library_load"
  | "video_deck"
  | "video_fullscreen"
  | "ndi_output"
  | "video_skins"
  | "stem_separation"
  | "stem_swap_transitions"
  | "rekordbox_export"
  | "phase_indicator"
  | "help_video"
  | "help_ndi"
  | "help_av_rig";

export interface FeatureCapability {
  available: boolean;
  enabled: boolean;
  reason: string | null;
}

export interface EngineCapabilities {
  fork: ForkId;
  process_running: boolean;
  osc_connected: boolean;
  is_mixxxxx: boolean;
  is_vanilla: boolean;
  summary: string;
  features: Record<FeatureId, FeatureCapability>;
}

const featureIds: FeatureId[] = [
  "osc_deck_control", "deck_load", "effects_racks", "hotcues", "crossfader", "library_load",
  "video_deck", "video_fullscreen", "ndi_output", "video_skins", "stem_separation",
  "stem_swap_transitions", "rekordbox_export", "phase_indicator", "help_video", "help_ndi", "help_av_rig",
];

export const DEFAULT_CAPABILITIES: EngineCapabilities = {
  fork: "unknown",
  process_running: false,
  osc_connected: false,
  is_mixxxxx: false,
  is_vanilla: false,
  summary: "Engine unknown — launch and probe OSC",
  features: Object.fromEntries(featureIds.map((id) => [id, {
    available: false,
    enabled: false,
    reason: "Launch Mixxx or mixxxxx and connect OSC",
  }])) as Record<FeatureId, FeatureCapability>,
};

export const HELP_TAB_FEATURES: Partial<Record<string, FeatureId>> = {
  rig: "help_av_rig",
  ndi: "help_ndi",
  video: "help_video",
  skins: "video_skins",
};

export function featureEnabled(caps: EngineCapabilities | null, feature: FeatureId): boolean {
  return Boolean(caps?.features?.[feature]?.enabled);
}

export function featureReason(caps: EngineCapabilities | null, feature: FeatureId): string | null {
  return caps?.features?.[feature]?.reason || null;
}

export function forkLabel(fork: ForkId): string {
  if (fork === "mixxxxx") return "mixxxxx";
  if (fork === "mixxx") return "Mixxx";
  return "Engine ?";
}
