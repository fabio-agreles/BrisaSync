import type { ReactElement } from "react";

type IconName =
  | "dashboard"
  | "folder"
  | "layers"
  | "activity"
  | "conflict"
  | "settings"
  | "search"
  | "plus"
  | "play"
  | "pause"
  | "refresh"
  | "check"
  | "alert"
  | "cloud"
  | "upload"
  | "download"
  | "arrow-right"
  | "chevron-left"
  | "chevron-right"
  | "chevron-down"
  | "x"
  | "sun"
  | "moon"
  | "bell"
  | "trash"
  | "folder-open"
  | "link"
  | "shield"
  | "zap"
  | "command"
  | "file"
  | "more"
  | "external"
  | "info"
  | "clock"
  | "drive"
  | "onedrive"
  | "dropbox"
  | "nextcloud"
  | "heart"
  | "copy";

const STROKE: Record<IconName, string[]> = {
  dashboard: [
    "M3 3h7v9H3z",
    "M14 3h7v5h-7z",
    "M14 12h7v9h-7z",
    "M3 16h7v5H3z",
  ],
  folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  layers: ["M12 2 2 7l10 5 10-5z", "M2 12l10 5 10-5", "M2 17l10 5 10-5"],
  activity: ["M3 12h4l3 8 4-16 3 8h4"],
  conflict: ["M12 3 2 21h20z", "M12 9v5", "M12 17h.01"],
  settings: [
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  ],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z", "M21 21l-4.35-4.35"],
  plus: ["M12 5v14", "M5 12h14"],
  play: ["M8 5v14l11-7z"],
  pause: ["M9 5v14", "M15 5v14"],
  refresh: ["M21 12a9 9 0 1 1-2.64-6.36", "M21 3v6h-6"],
  check: ["M20 6 9 17l-5-5"],
  alert: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 8v5", "M12 16h.01"],
  cloud: ["M17.5 19a4.5 4.5 0 0 0 .5-9 6 6 0 0 0-11.6-1.6A4 4 0 0 0 7 19z"],
  upload: ["M12 16V4", "M6 10l6-6 6 6", "M4 20h16"],
  download: ["M12 4v12", "M6 10l6 6 6-6", "M4 20h16"],
  "arrow-right": ["M5 12h14", "M13 6l6 6-6 6"],
  "chevron-left": ["M15 6l-6 6 6 6"],
  "chevron-right": ["M9 6l6 6-6 6"],
  "chevron-down": ["M6 9l6 6 6-6"],
  x: ["M6 6l12 12", "M18 6 6 18"],
  sun: ["M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M12 2v2", "M12 20v2", "M2 12h2", "M20 12h2", "M5 5l1.5 1.5", "M17.5 17.5 19 19", "M19 5l-1.5 1.5", "M6.5 17.5 5 19"],
  moon: ["M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"],
  bell: ["M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9", "M10 21h4"],
  trash: ["M3 6h18", "M8 6V4h8v2", "M6 6l1 14h10l1-14"],
  "folder-open": ["M3 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v1H3z", "M3 10h18l-2 8H5z"],
  link: ["M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5", "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"],
  shield: ["M12 3l8 3v6c0 4.5-3.4 7.9-8 9-4.6-1.1-8-4.5-8-9V6z"],
  zap: ["M13 2 3 14h7l-1 8 11-13h-7z"],
  command: ["M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"],
  file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6"],
  more: ["M5 12h.01", "M12 12h.01", "M19 12h.01"],
  external: ["M14 3h7v7", "M21 3l-9 9", "M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"],
  info: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 16v-5", "M12 8h.01"],
  clock: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 7v5l3 2"],
  drive: ["M8 3h8l6 10-4 6H6l-4-6z", "M8 3l6 10", "M16 3l-6 10", "M2 13h14"],
  onedrive: ["M4 15a4 4 0 0 1 .8-7.9 6 6 0 0 1 11.5-1.4A4.5 4.5 0 0 1 20 15z"],
  dropbox: [
    "M12 3 6 7l6 4-6 4 6 4 6-4-6-4 6-4z",
    "M6 15l6 4 6-4",
  ],
  nextcloud: [
    "M12 12m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0 -7 0",
    "M5.5 12a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0 -5 0",
    "M13.5 12a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0 -5 0",
  ],
  heart: [
    "M12 20.5s-8.5-5.3-8.5-11A4.9 4.9 0 0 1 12 6.4a4.9 4.9 0 0 1 8.5 3.1c0 5.7-8.5 11-8.5 11z",
  ],
  copy: [
    "M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1z",
    "M15 6V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1",
  ],
};

const FILLED: IconName[] = ["play", "zap"];

export function Icon({
  name,
  size = 18,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}): ReactElement {
  const filled = FILLED.includes(name);
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {STROKE[name].map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
}

export type { IconName };
