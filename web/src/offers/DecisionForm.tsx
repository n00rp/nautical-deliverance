import { useState } from "react";
import { ApiError } from "../api";
import { useSave } from "../admin/useSave";
import type { DecisionReason } from "../inquiryApi";
import { REASON_LABEL } from "../offerApi";
import { Button } from "../ui/Button/Button";
import { FormSummary } from "../ui/FormSummary/FormSummary";
import { Select } from "../ui/Select/Select";
import { TextField } from "../ui/TextField/TextField";
import css from "./Comparison.module.css";

export type DecisionFormProps = {
  /** Sends the choice; a rejected 422 lands on the fields, anything else goes to `onFail`. */
  onSubmit: (body: { reason: DecisionReason; note?: string }) => Promise<void>;
  onFail: (e: unknown) => void;
  onCancel: () => void;
};

const REASONS = (Object.entries(REASON_LABEL) as [DecisionReason, string][]).map(
  ([value, label]) => ({ value, label }),
);
const FIELDS: Record<string, string> = {
  reason: "decision-reason",
  note: "decision-note",
  offer_id: "decision-reason",
};
const invalid = (field: string, message: string) => new ApiError(422, [{ field, message }]);

/** Why a higher-priced offer wins: a reason, and a note that "other" makes required (B0-D4). */
export function DecisionForm({ onSubmit, onFail, onCancel }: DecisionFormProps) {
  const [reason, setReason] = useState<DecisionReason | "">("");
  const [note, setNote] = useState("");
  const { form, issues, clear, busy, submit } = useSave(onFail);
  const err = (field: string) => issues.find((i) => i.field === field)?.message;
  const send = submit(async () => {
    const text = note.trim();
    if (!reason) throw invalid("reason", "Choose why this offer is selected");
    if (reason === "other" && !text) throw invalid("note", "Describe the reason");
    await onSubmit({ reason, ...(text ? { note: text } : {}) });
  });

  return (
    <form ref={form} aria-label="Selection rationale" noValidate onSubmit={(e) => void send(e)}>
      <p className={css.lead}>This offer is not the lowest. Say why it is selected.</p>
      <FormSummary
        errors={issues.map((i) => ({
          fieldId: FIELDS[i.field] ?? "decision-reason",
          message: i.message,
        }))}
      />
      <Select
        id="decision-reason"
        label="Reason"
        required
        value={reason}
        options={REASONS}
        error={err("reason") ?? err("offer_id")}
        onChange={(v) => {
          setReason(v);
          clear((f) => f === "reason" || f === "offer_id");
        }}
      />
      <TextField
        id="decision-note"
        label="Note"
        rows={3}
        required={reason === "other"}
        value={note}
        error={err("note")}
        onChange={(v) => {
          setNote(v);
          clear((f) => f === "note");
        }}
      />
      <div className={css.actions}>
        <Button type="submit" variant="primary" loading={busy}>
          Confirm selection
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
