import { fmtDateTime } from "@/lib/format";
import type { Message } from "@/lib/types";

export const SUPPRESSED: Record<string, string> = {
  OPTED_OUT: "the patient opted out of reminders",
  NO_MESSAGING_CONSENT: "there is no consent for reminder messages",
  FOLLOW_UP_CLOSED: "this follow-up is already closed",
  PATIENT_ALREADY_CONFIRMED: "the patient already confirmed",
  PLAN_CANCELLED: "the plan was cancelled",
  ALREADY_REMINDED_TODAY: "the patient already got a reminder today",
};

/** Truthful wording for what happened to a reminder the moment staff asked for it. */
export function reminderOutcome(m: Message): { text: string; fail: boolean } {
  switch (m.status) {
    case "SCHEDULED":
      return { text: `Reminder scheduled for ${fmtDateTime(m.scheduled_for)} because of quiet hours.`, fail: false };
    case "SUPPRESSED":
      return { text: `Reminder not sent: ${SUPPRESSED[m.suppressed_reason] ?? m.suppressed_reason.toLowerCase()}.`, fail: true };
    case "FAILED":
      return { text: `Reminder failed (${m.last_error_code}). A task was created to contact the patient another way.`, fail: true };
    case "DELIVERED":
      return { text: "Reminder delivered (provider confirmed).", fail: false };
    case "SENT_TO_PROVIDER":
      return { text: "Reminder sent. Delivery is not confirmed yet.", fail: false };
    default:
      return { text: "Reminder queued for sending.", fail: false };
  }
}

export const OUTCOME_LABELS: Record<string, string> = {
  APPOINTMENT_CANCELLED: "Appointment cancelled; patient notified",
  APPOINTMENT_POSTPONED: "Appointment postponed; patient notified",
  APPOINTMENT_PREPONED: "Appointment moved earlier; patient notified",
  REACHED_PATIENT: "Reached the patient",
  BOOKED: "New time booked",
  FOLLOW_UP_COMPLETED: "Follow-up completed",
  ANSWERED_BY_CLINICIAN: "Clinician answered",
  PATIENT_WILL_ATTEND: "Patient will attend",
  PATIENT_DECLINED: "Patient declined",
  NO_ANSWER: "No answer after attempts",
  WRONG_NUMBER: "Wrong or unreachable number",
  REFERRED: "Referred elsewhere",
  OTHER: "Other (see note)",
};

export const CATEGORY_LABELS: Record<string, string> = {
  RESCHEDULE: "Reschedule", CALLBACK: "Call back", BARRIER: "Barrier", CLINICAL_QUESTION: "Clinical question",
  URGENT_CONCERN: "Possible urgent concern", UNCLEAR_INPUT: "Unclear message", MESSAGE_FAILURE: "Message failed",
  OVERDUE_FOLLOWUP: "Overdue follow-up", DOCUMENT_REVIEW: "Document to review", BOOKING_FAILED: "Booking failed",
};

export const BARRIER_LABELS: Record<string, string> = {
  TIMING: "Timing", TRANSPORT: "Transport", COST: "Cost", CONFUSION: "Unsure what to do", FEELING_WELL: "Feels well",
  CAREGIVER_LOGISTICS: "No one to accompany", OTHER: "Other", PREFER_NOT_TO_SAY: "Prefers not to say",
};

export const INTENT_LABELS: Record<string, string> = {
  CONFIRM_FOLLOWUP: "Confirm follow-up", RESCHEDULE_REQUEST: "Change date or time", REPORT_UPLOAD_INTENT: "Share a report",
  CALLBACK_REQUEST: "Call back", BARRIER_REPORTED: "Difficulty attending", CLINICAL_QUESTION: "Clinical question",
  URGENT_CONCERN: "Possible urgent concern", OPT_OUT: "Stop messages", OTHER_OR_UNCLEAR: "Not clear", OPT_IN: "Start messages",
};

export const ACTION_STATUS_LABELS: Record<string, string> = {
  DONE: "Done", HANDED_TO_CLINICIAN: "Handed to a clinician", HANDED_TO_STAFF: "Handed to staff",
  AWAITING_SLOT_CHOICE: "Waiting for the patient to pick a slot", AWAITING_CONFIRMATION: "Waiting for the patient to confirm",
  AWAITING_CLARIFICATION: "Asked the patient to clarify", AWAITING_UPLOAD: "Waiting for an upload",
  NO_OPEN_FOLLOW_UP: "No open follow-up", ALREADY_RECORDED: "Already recorded", SUPERSEDED: "Replaced by a correction",
  DECLINED: "Patient kept things as they were",
};

export const PROPOSAL_STATUS: Record<string, [string, "wait" | "done" | "fail" | "info" | "neutral"]> = {
  REVIEWED: ["Clinic review complete", "done"],
  EXTRACTION_PENDING: ["Reading the document", "info"],
  NEEDS_REVIEW: ["Needs review", "wait"],
  EXTRACTION_FAILED: ["Could not be read", "fail"],
  APPROVED: ["Approved into a plan", "done"],
  REJECTED: ["Rejected", "neutral"],
};

export const REVIEW_REASONS: Record<string, string> = {
  VERIFY_MEASUREMENT_AGAINST_ORIGINAL: "Check the number and unit against the original report.",
  LOW_OCR_CONFIDENCE: "Uncertain OCR: verify the value, unit and original image.",
  HANDWRITING_REQUIRES_REVIEW: "Handwriting requires clinic verification.",
  OCR_DISAGREEMENT: "Reading engines disagree. Compare each candidate with the original.",
  UNSUPPORTED_HANDWRITING_LANGUAGE: "Hindi/Telugu handwriting needs manual verification.",
  HANDWRITING_UNAVAILABLE: "The handwriting model could not read this line.",
  OCR_INCOMPLETE: "Document reading is incomplete. Check every source page.",
  OCR_FALLBACK: "PaddleOCR was unavailable. Tesseract fallback needs verification.",
  UNSUPPORTED_MEDICAL_PARAMETER: "Additional lab test: use Correct to verify its name, value and unit. A clinician-confirmed result can appear in health numbers without automatic clinical interpretation.",
  AI_MEASUREMENT_REQUIRES_REVIEW: "AI-extracted measurement: verify the result, unit and source row before confirming.",
  MEDICAL_SOURCE_NOT_GROUNDED: "The AI quote could not be matched to the OCR source. Compare the original image.",
  MEDICAL_VALUE_UNIT_NOT_GROUNDED: "The proposed value and unit do not match the quoted result clearly. Correct them from the original.",
  POSSIBLE_REFERENCE_VALUE: "This may be a reference limit rather than the patient's result. Check the source columns.",
  REFERENCE_RANGE_NOT_GROUNDED: "The proposed laboratory range could not be matched to the source.",
  MEASUREMENT_DATE_NOT_GROUNDED: "The proposed measurement date could not be verified from the source page.",
  FUTURE_MEASUREMENT_DATE: "The extracted measurement date is in the future. Check the original date.",
  UNSUPPORTED_MEASUREMENT_UNIT: "The unit may be misread. Check the original and correct the value and unit before confirming.",
  CONFLICTING_MEASUREMENTS: "Conflicting values were found. Confirm the correct one and reject the others.",
  CONFLICTING_VALUES: "The document gives different values for this field. Check which one is right.",
  NO_EXACT_DATE: "No exact date is written. Enter the date yourself or reject this field.",
  BEFORE_DOCUMENT_DATE: "This date is earlier than the document date.",
  TOO_FAR_AHEAD: "This date is more than two years ahead.",
  QUOTE_NOT_FOUND_IN_SOURCE: "The quoted text could not be found in the document.",
  NO_SOURCE_EVIDENCE: "No source location was found for this value.",
  LOW_CONFIDENCE: "The reader was not confident about this value.",
};

export const FIELD_TO_ITEM: Record<string, string> = {
  next_review_date: "Review visit", hba1c_due_date: "HbA1c test", eye_exam_due_date: "Eye (retina) check",
  foot_exam_due_date: "Foot check", kidney_test_due_date: "Kidney test", refill_due_date: "Medicine refill",
};

export const TEMPLATE_NAMES: Record<string, string> = {
  REMINDER_PRE_DUE: "Reminder before the due date",
  REMINDER_DUE: "Reminder on the due date",
  REMINDER_OVERDUE: "Reminder after a missed date",
  CONFIRM_ACK: "Thanks for confirming",
  RESCHEDULE_OPTIONS: "New times offered",
  BOOKING_CONFIRMED: "Booking confirmed",
  BOOKING_NOT_DONE: "Booking could not be completed",
  BARRIER_ACK: "Reply to a reported problem (cost, travel, work)",
  CALLBACK_ACK: "Call-back request received",
  CLINICAL_ACK: "Medical question passed to the care team",
  URGENT_ESCALATION: "Possible urgent concern: call the clinic",
  CLARIFY: "Asking the patient to say it again",
  VOICE_FAILED: "Voice note could not be understood",
  OPT_OUT_CONFIRMED: "Reminders stopped",
  REPORT_UPLOAD_LINK: "Link to share a report",
  CAREGIVER_INVITE: "Family helper invitation",
};

export const templateName = (key: string): string => TEMPLATE_NAMES[key] ?? key.toLowerCase().replace(/_/g, " ");

export const OCR_VERIFICATION_REASONS = ["LOW_OCR_CONFIDENCE", "HANDWRITING_REQUIRES_REVIEW", "OCR_DISAGREEMENT", "UNSUPPORTED_HANDWRITING_LANGUAGE", "HANDWRITING_UNAVAILABLE", "OCR_INCOMPLETE", "OCR_FALLBACK", "CONFLICTING_MEASUREMENTS", "UNSUPPORTED_MEASUREMENT_UNIT", "AI_MEASUREMENT_REQUIRES_REVIEW", "MEDICAL_SOURCE_NOT_GROUNDED", "MEDICAL_VALUE_UNIT_NOT_GROUNDED", "POSSIBLE_REFERENCE_VALUE", "REFERENCE_RANGE_NOT_GROUNDED", "MEASUREMENT_DATE_NOT_GROUNDED", "FUTURE_MEASUREMENT_DATE", "UNSUPPORTED_MEDICAL_PARAMETER"];
