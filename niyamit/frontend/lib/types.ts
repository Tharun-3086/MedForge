// Shapes returned by the FastAPI backend (see backend/app/serializers.py).

export type Provenance = "PATIENT_REPORTED" | "AI_PROPOSED" | "STAFF_CONFIRMED" | "CLINICIAN_APPROVED" | "SYSTEM_EVENT";

export interface Me {
  user: { id: string; name: string; email: string; role: string; label: string };
  clinic: { id: string; name: string; short_name: string; phone: string; timezone: string; is_synthetic: boolean };
  permissions: string[];
  demo_mode: boolean;
}

export interface PatientBrief {
  id: string;
  name: string;
  phone: string;
  language: string;
  channel: string;
  opted_out: boolean;
  is_synthetic: boolean;
  external_ref: string;
  birth_year: number | null;
  last_visit_at: string | null;
}

export interface Item {
  id: string;
  kind: string;
  label: string;
  due_date: string;
  status: string;
  days_overdue: number;
  source_field_id: string | null;
  patient_confirmed_at: string | null;
  completed_at: string | null;
}

export interface Plan {
  id: string;
  status: string;
  version: number;
  source: string;
  approved_at: string | null;
  approved_by: string | null;
  notes: string;
  proposal_id: string | null;
  source_artifact_id: string | null;
  items: Item[];
  created_at: string;
}

export interface TaskEvent { from: string | null; to: string; by: string; note: string; at: string }

export interface Task {
  id: string;
  patient_id: string;
  category: string;
  category_label?: string;
  queue: string;
  priority: string;
  status: string;
  title: string;
  barrier_category: string | null;
  patient_statement: string | null;
  assignee_user_id: string | null;
  assignee: string | null;
  due_at: string;
  escalated_at: string | null;
  outcome: string;
  outcome_note: string;
  created_at: string;
  resolved_at: string | null;
  source_type: string;
  source_id: string;
  overdue?: boolean;
  patient?: { id: string; name: string; phone: string; language: string };
  events?: TaskEvent[];
  source?: Reply | AppointmentRequest | Message | null;
}

export interface Message {
  id: string;
  patient_id: string;
  kind: string;
  template_key: string;
  language: string;
  channel: string;
  simulated: boolean;
  body: string;
  status: string;
  status_label: string;
  essential: boolean;
  scheduled_for: string;
  sent_at: string | null;
  delivered_at: string | null;
  failed_at: string | null;
  attempts: number;
  last_error_code: string;
  suppressed_reason: string;
  created_at: string;
  patient_name?: string;
}

export interface ReplyAction {
  intent: string;
  label?: string;
  status: string;
  patient_text?: string | null;
  question?: string;
  question_key?: string;
  options?: string[];
  slots?: Slot[];
  request_id?: string;
  task_id?: string;
  barrier?: string;
  booking_reference?: string;
  candidate_date?: string | null;
  day_words?: string | null;
  due_date?: string | null;
  date_options?: string[];
  note?: string;
}

export interface Reply {
  id: string;
  patient_id: string;
  channel: string;
  input_mode: string;
  choice_label?: string | null;
  status: string;
  text: string | null;
  transcript: string | null;
  corrected_text: string | null;
  detected_language: string | null;
  language_confidence: number | null;
  asr_provider: string;
  understanding: {
    intents?: string[];
    confidence?: number;
    english_gloss?: string | null;
    requested_day_text?: string | null;
    barrier_category?: string | null;
    needs_clarification?: boolean;
    clarification_reason?: string | null;
  };
  understanding_source: string;
  provider_notes: string[];
  actions: ReplyAction[];
  error_code: string;
  via_caregiver: boolean;
  created_at: string;
  processed_at: string | null;
}

export interface Slot { id: string; starts_at: string; provider: string; label: string; date: string; source: string }

export interface AppointmentRequest {
  id: string;
  status: string;
  status_label: string;
  requested_day_text: string | null;
  requested_date: string | null;
  requested_time_window: string | null;
  patient_statement: string | null;
  requested_by: string;
  failure_reason: string;
  created_at: string;
  patient?: PatientBrief;
}

export interface Appointment { id: string; status: string; reference: string; slot_label: string | null; created_by: string; committed_at: string }

export interface TimelineEvent {
  id: string;
  type: string;
  summary: string;
  provenance: Provenance;
  actor_type: string;
  actor: string;
  patient_words: string | null;
  source_type: string;
  source_id: string;
  visibility: string;
  at: string;
}

export interface Field {
  id: string;
  name: string;
  label: string;
  value: string | null;
  proposed_value: string | null;
  extracted_value: string | null;
  status: string;
  confidence: number | null;
  evidence: {
    quote?: string | null;
    block_ids?: string[];
    page?: number | null;
    bboxes?: { page: number; bbox: [number, number, number, number] }[];
    computed?: string;
  };
  review_reasons: string[];
  reviewed_at: string | null;
  provenance: Provenance;
}

export interface Artifact {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  page_count: number;
  source_type: string;
  uploaded_by_patient: boolean;
  is_synthetic: boolean;
  created_at: string;
  content_url: string;
  page_url: string;
}

export interface Proposal {
  id: string;
  status: string;
  created_at: string;
  processed_at: string | null;
  ocr_provider: string;
  extractor: string;
  model_version: string;
  pipeline_version: string;
  error_code: string;
  notes: string[];
  plan_id: string | null;
  fields: Field[];
  artifact: Artifact | null;
  patient: PatientBrief | null;
  page_sizes: { page: number; width: number; height: number }[];
  blocks?: { id: string; page: number; text: string; bbox: [number, number, number, number] | null }[];
  can_approve?: boolean;
  today?: string;
  plan?: Plan;
}

export interface WorklistRow {
  patient: PatientBrief;
  item: Item;
  days_overdue: number;
  due_in_days: number;
  state: string;
  next_action: string;
  latest_statement: string | null;
  latest_choice: string | null;
  latest_reply_status: string | null;
  latest_reply_at: string | null;
  last_message: { status: string; label: string; channel: string; at: string } | null;
  open_tasks: { id: string; category: string; queue: string; priority: string; status: string; assignee: string | null; escalated: boolean; source_id: string }[];
}

export interface Dashboard {
  today: string;
  overdue: number;
  due_this_week: number;
  open_tasks: number;
  open_tasks_by_queue: Record<string, number>;
  urgent_open: number;
  failed_messages_7d: number;
  documents_to_review: number;
  waiting_on_patient_choice: number;
}

export interface StaffMember { id: string; name: string; role: string }
