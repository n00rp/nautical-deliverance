const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const two = (n: number) => String(n).padStart(2, "0");

const localTime = (d: Date, timeZone: string) => {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(d)
      .map((x) => [x.type, x.value]),
  );
  return `${p.hour}:${p.minute}`;
};

/**
 * "12 Nov 06:00 UTC · 07:00 local"; only the UTC part when no timeZone is given (B1-D10).
 * Month names are a fixed English table, so the text never depends on the ICU version.
 */
export function formatInstant(isoUtc: string, timeZone?: string): string {
  const d = new Date(isoUtc);
  if (Number.isNaN(d.getTime())) return isoUtc;
  const month = MONTHS[d.getUTCMonth()] ?? "";
  const utc = `${two(d.getUTCDate())} ${month} ${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC`;
  return timeZone ? `${utc} · ${localTime(d, timeZone)} local` : utc;
}
