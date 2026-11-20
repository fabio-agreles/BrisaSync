import { idiomaAtual, locale, t } from "./i18n";

const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(value: number, digits = 1): string {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const exponent = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    UNITS.length - 1,
  );
  const scaled = value / 1024 ** exponent;
  const decimals = exponent === 0 ? 0 : scaled >= 100 ? 0 : digits;
  const numero = scaled.toFixed(decimals);
  // Português usa vírgula decimal; inglês, ponto.
  const texto = idiomaAtual() === "en" ? numero : numero.replace(".", ",");
  return `${texto} ${UNITS[exponent]}`;
}

export function formatSpeed(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  return `${formatBytes(value)}/s`;
}

export function formatEta(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 60) return `${Math.ceil(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes} min ${rest} s`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

export function relativeTime(timestamp: number | null): string {
  if (!timestamp) return t("nunca");
  const diff = Date.now() - timestamp;
  if (diff < 45_000) return t("agora");
  if (diff < 3_600_000) return t("há {n} min", { n: Math.max(1, Math.round(diff / 60_000)) });
  if (diff < 86_400_000) return t("há {n} h", { n: Math.round(diff / 3_600_000) });
  if (diff < 7 * 86_400_000) {
    const days = Math.round(diff / 86_400_000);
    return days === 1 ? t("há {n} dia", { n: days }) : t("há {n} dias", { n: days });
  }
  return new Date(timestamp).toLocaleDateString(locale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function dayLabel(timestamp: number): string {
  const date = new Date(timestamp);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (left: Date, right: Date) =>
    left.getDate() === right.getDate() &&
    left.getMonth() === right.getMonth() &&
    left.getFullYear() === right.getFullYear();
  if (sameDay(date, today)) return t("Hoje");
  if (sameDay(date, yesterday)) return t("Ontem");
  return date.toLocaleDateString(locale(), {
    day: "2-digit",
    month: "long",
  });
}

export function clock(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString(locale(), {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function parentPath(path: string): string {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

export function joinPath(base: string, name: string): string {
  return base ? `${base}/${name}` : name;
}
