import type { ReactNode } from "react";
import { STATUS_LABEL, type InquiryStatus } from "../inquiryApi";
import rfqs from "../rfqs/RfqLog.module.css";
import page from "../rfqs/SupplierSelection.module.css";
import { StatusPill } from "../ui/StatusPill/StatusPill";

export type InquiryTitleProps = {
  heading: string;
  status: InquiryStatus;
  inquiryId: string;
  /** More links after "Back to inquiry". */
  children?: ReactNode;
};

/** Heading, status pill and "Back to inquiry" of a screen that works on one inquiry. */
export function InquiryTitle({ heading, status, inquiryId, children }: InquiryTitleProps) {
  return (
    <div className={page.title}>
      <h2 className={page.heading}>{heading}</h2>
      <StatusPill status={STATUS_LABEL[status]} />
      <div className={rfqs.links}>
        <a className={page.back} href={`#/inquiries/${inquiryId}`}>
          Back to inquiry
        </a>
        {children}
      </div>
    </div>
  );
}
