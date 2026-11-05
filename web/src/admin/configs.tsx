import type { MasterType, Rec } from "../masterApi";
import { formatInstant } from "../ui/DateTimeField/format";
import { ContactsPanel, SetPanel, type SetSpec } from "./Extras";
import type { FieldDef, MasterConfig } from "./types";

/** Current time at a port, "05 Nov 12:00 UTC · 20:00 local"; nothing for an unknown zone (B1-R08). */
function localNow(timeZone: string | undefined): string | undefined {
  if (!timeZone) return undefined;
  try {
    return formatInstant(new Date().toISOString(), timeZone);
  } catch {
    return undefined;
  }
}

const name: FieldDef = { key: "name", label: "Name", kind: "text", required: true };
const nameColumn = {
  key: "name",
  header: "Name",
  render: (r: Rec) => String(r.name),
};
const cell = (key: string, header: string) => ({
  key,
  header,
  render: (r: Rec) => String(r[key] ?? "—"),
});

const COVERAGE: SetSpec = {
  title: "Coverage",
  saveLabel: "Save coverage",
  saved: "Coverage saved",
  url: (id) => `counterparties/${encodeURIComponent(id)}/coverage`,
  rows: "ports",
  rowHeader: "Port",
  cols: "products",
  item: (port_id, product_id) => ({ port_id, product_id }),
};

const FUELS: SetSpec = {
  title: "Approved fuels",
  saveLabel: "Save approved fuels",
  saved: "Approved fuels saved",
  url: (id) => `vessels/${encodeURIComponent(id)}/approved-fuels`,
  cols: "products",
  item: (_row, product_id) => ({ product_id }),
};

const nameOnly = (path: MasterType, title: string, singular: string): MasterConfig => ({
  path,
  title,
  singular,
  fields: [name],
  columns: [nameColumn],
  refs: [],
});

export const MASTER_CONFIGS: MasterConfig[] = [
  {
    path: "legal-entities",
    title: "Legal entities",
    singular: "legal entity",
    fields: [name, { key: "code", label: "Code", kind: "text", required: true }],
    columns: [nameColumn, cell("code", "Code")],
    refs: [],
  },
  {
    path: "vessels",
    title: "Vessels",
    singular: "vessel",
    fields: [
      name,
      { key: "imo", label: "IMO", kind: "text", required: true, hint: () => "7 digits" },
      { key: "vessel_type", label: "Vessel type", kind: "text", required: true },
      { key: "dwt", label: "Deadweight tonnes", kind: "int", required: true },
      { key: "flag", label: "Flag", kind: "text", required: true },
      {
        key: "legal_entity_id",
        label: "Legal entity",
        kind: "select",
        required: true,
        optionsFrom: "legal-entities",
      },
    ],
    columns: [
      nameColumn,
      cell("imo", "IMO"),
      cell("vessel_type", "Type"),
      cell("dwt", "DWT (t)"),
      cell("flag", "Flag"),
      {
        key: "legal_entity_id",
        header: "Legal entity",
        render: (r, refs) =>
          String(
            refs["legal-entities"]?.find((e) => e.id === r.legal_entity_id)?.name ??
              r.legal_entity_id,
          ),
      },
    ],
    refs: ["legal-entities", "products"],
    aside: (ctx) => <SetPanel ctx={ctx} spec={FUELS} />,
  },
  {
    path: "ports",
    title: "Ports",
    singular: "port",
    fields: [
      { key: "locode", label: "UN/LOCODE", kind: "text", required: true, hint: () => "e.g. NLRTM" },
      name,
      {
        key: "country",
        label: "Country",
        kind: "text",
        required: true,
        hint: () => "Two capital letters, e.g. NL",
      },
      {
        key: "time_zone",
        label: "Time zone",
        kind: "text",
        required: true,
        hint: (v) => localNow(v["time_zone"]),
      },
    ],
    columns: [
      cell("locode", "UN/LOCODE"),
      nameColumn,
      cell("country", "Country"),
      cell("time_zone", "Time zone"),
      {
        key: "local",
        header: "Local time now",
        render: (r) => localNow(String(r.time_zone)) ?? "—",
      },
    ],
    refs: [],
  },
  {
    path: "counterparties",
    title: "Counterparties",
    singular: "counterparty",
    fields: [
      name,
      {
        key: "type",
        label: "Type",
        kind: "select",
        required: true,
        default: "physical_supplier",
        options: [
          { value: "physical_supplier", label: "Physical supplier" },
          { value: "trader", label: "Trader" },
          { value: "both", label: "Both" },
        ],
      },
      { key: "notes", label: "Notes", kind: "text" },
    ],
    columns: [nameColumn, cell("type", "Type")],
    refs: ["ports", "products"],
    below: (ctx) => (
      <>
        <ContactsPanel ctx={ctx} />
        <SetPanel ctx={ctx} spec={COVERAGE} />
      </>
    ),
  },
  {
    path: "products",
    title: "Products",
    singular: "product",
    fields: [
      name,
      {
        key: "default_unit",
        label: "Default unit",
        kind: "select",
        required: true,
        default: "mt",
        options: [
          { value: "mt", label: "mt (metric tonnes)" },
          { value: "m3", label: "m3 (cubic metres)" },
        ],
      },
    ],
    columns: [nameColumn, cell("default_unit", "Unit")],
    refs: [],
  },
  nameOnly("iso-spec-versions", "ISO spec versions", "ISO spec version"),
  nameOnly("bunkering-reasons", "Bunkering reasons", "bunkering reason"),
];

export const configFor = (path: MasterType): MasterConfig => {
  const config = MASTER_CONFIGS.find((c) => c.path === path);
  if (!config) throw new Error(`Unknown master-data type: ${path}`);
  return config;
};

export const ADMIN_NAV = MASTER_CONFIGS.map((c) => ({
  href: `#/admin/${c.path}`,
  label: c.title,
  section: "Master data",
}));
