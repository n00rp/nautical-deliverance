const parts = (d: Date, timeZone: string) => {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone,
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(d)
      .map((x) => [x.type, x.value]),
  );
  return { date: `${p.day} ${p.month}`, time: `${p.hour}:${p.minute}` };
};

/** "12 Nov 06:00 UTC · 07:00 local"; only the UTC part when no timeZone is given (B1-D10). */
export function formatInstant(isoUtc: string, timeZone?: string): string {
  const d = new Date(isoUtc);
  if (Number.isNaN(d.getTime())) return isoUtc;
  const utc = parts(d, "UTC");
  const base = `${utc.date} ${utc.time} UTC`;
  return timeZone ? `${base} · ${parts(d, timeZone).time} local` : base;
}
