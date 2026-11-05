import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DateTimeField } from "./DateTimeField";
import { formatInstant } from "./format";

describe("formatInstant", () => {
  it("[B1-R08] formatInstant across DST: UTC and port-local time", () => {
    const tz = "Europe/Amsterdam";
    expect(formatInstant("2026-03-29T00:30:00Z", tz)).toBe("29 Mar 00:30 UTC · 01:30 local");
    expect(formatInstant("2026-03-29T01:30:00Z", tz)).toBe("29 Mar 01:30 UTC · 03:30 local");
    expect(formatInstant("2026-11-12T06:00:00Z", tz)).toBe("12 Nov 06:00 UTC · 07:00 local");
  });

  it("[B1-R08] formatInstant shows only UTC without a zone and passes junk through", () => {
    expect(formatInstant("2026-11-12T06:00:00Z")).toBe("12 Nov 06:00 UTC");
    expect(formatInstant("not a date", "Europe/Amsterdam")).toBe("not a date");
  });
});

describe("DateTimeField", () => {
  afterEach(cleanup);

  it("[B1-R08] shows the value as UTC with a port-local hint and emits ISO Z", () => {
    const onChange = vi.fn();
    render(
      <DateTimeField
        id="eta"
        label="ETA"
        valueUtc="2026-11-12T06:00:00.000Z"
        timeZone="Europe/Amsterdam"
        onChange={onChange}
        error="Too early"
      />,
    );
    const input = screen.getByLabelText<HTMLInputElement>("ETA (UTC)");
    expect(input.value).toBe("2026-11-12T06:00");
    expect(input.getAttribute("aria-describedby")).toBe("eta-hint eta-error");
    expect(screen.getByText("12 Nov 06:00 UTC · 07:00 local")).toBeTruthy();
    fireEvent.change(input, { target: { value: "2026-11-13T08:15" } });
    expect(onChange).toHaveBeenLastCalledWith("2026-11-13T08:15:00.000Z");
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("[B1-R08] empty value has no hint", () => {
    render(
      <DateTimeField
        id="e"
        label="ETA"
        valueUtc=""
        timeZone="Europe/Amsterdam"
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText(/local/)).toBeNull();
  });
});
