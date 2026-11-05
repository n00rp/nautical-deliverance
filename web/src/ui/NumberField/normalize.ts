const AMBIGUOUS =
  "Ambiguous: one separator followed by 3 digits. Use a decimal point (1234.567) or no separator.";
const INVALID = "Enter a number such as 1234.56";

type Result = { value: string } | { error: string };

const groupsOk = (s: string, sep: string): boolean =>
  new RegExp(`^[1-9]\\d{0,2}(?:\\${sep}\\d{3})+$`).test(s);

/**
 * Exact decimal text -> canonical "-?\d+(\.\d+)?" string. Pure string work, no float is ever
 * involved (D-074). "," and "." both work as decimal separator when unambiguous; spaces group.
 */
export function normalizeDecimal(input: string, decimals: number): Result {
  const s = input.replace(/\s/g, ""); // \s covers NBSP and narrow NBSP too
  if (s === "") return { value: "" };
  const m = /^(-?)([\d.,]*)$/.exec(s);
  const sign = m?.[1] ?? "";
  const body = m?.[2] ?? "";
  if (!/\d/.test(body)) return { error: INVALID };

  const seps = body.replace(/\d/g, "");
  let int = body;
  let frac = "";
  if (seps !== "") {
    const dec = seps.slice(-1);
    const other = dec === "." ? "," : ".";
    const at = body.lastIndexOf(dec);
    const head = body.slice(0, at);
    const tail = body.slice(at + 1);
    if (!head.includes(dec)) {
      // The last separator occurs once: it is the decimal point; `other` may only group.
      if (tail === "" || (head.includes(other) && !groupsOk(head, other))) {
        return { error: INVALID };
      }
      // A head of 0 (or none) cannot carry a thousands group, so 0.125 is a decimal.
      const grouping = head !== "" && !head.startsWith("0");
      if (seps.length === 1 && tail.length === 3 && grouping) return { error: AMBIGUOUS };
      int = head.split(other).join("");
      frac = tail;
    } else if (seps.includes(other) || !groupsOk(body, dec)) {
      return { error: INVALID };
    } else {
      // Repeated same separator: grouping only, no decimal part.
      int = body.split(dec).join("");
    }
  }
  if (frac.length > decimals) {
    return { error: decimals === 0 ? "Whole numbers only" : `At most ${decimals} decimal places` };
  }
  int = int.replace(/^0+(?=\d)/, "") || "0";
  const zero = int === "0" && /^0*$/.test(frac); // no negative zero
  return { value: `${zero ? "" : sign}${int}${frac ? `.${frac}` : ""}` };
}
