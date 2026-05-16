export const APP_NAME = "Quarrel";
export const APP_CODENAME = "Tarka";
export const APP_TAGLINE = "The AI that won't let you lie to yourself.";

export const TIERS = ["free", "pro", "max"] as const;
export type Tier = (typeof TIERS)[number];

export const MODES = [
  "argue",
  "roast",
  "mediate",
  "council",
  "negotiate",
  "custom",
  "roast_my_x",
  "decision_killer",
  "cope_detector",
  "steelman",
  "future_self",
  "past_self",
  "drill_sergeant",
] as const;
export type Mode = (typeof MODES)[number];
