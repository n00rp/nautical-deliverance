import { useState } from "react";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { TextField } from "../ui/TextField/TextField";

/** Cancel with a required reason: the confirm step refuses an empty one. */
export function CancelAction({
  onCancel,
  disabled,
}: {
  onCancel: (reason: string) => void;
  disabled: boolean;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | undefined>();
  return (
    <>
      <TextField
        id="cancel-reason"
        label="Cancel reason"
        value={reason}
        error={error}
        onChange={(v) => {
          setReason(v);
          setError(undefined);
        }}
      />
      <InlineConfirm
        label="Cancel inquiry"
        confirmLabel="Confirm cancel inquiry"
        tone="crit"
        disabled={disabled}
        onConfirm={() => {
          if (reason.trim() === "") setError("Enter a reason to cancel");
          else onCancel(reason.trim());
        }}
      />
    </>
  );
}
