"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "./DraftModal.module.css";


// ── Date formatter ────────────────────────────────────────────────────────────
function formatEmailDate(raw) {
  if (!raw) return null;
  try {
    const d = new Date(raw);
    if (isNaN(d)) return raw;
    return d.toLocaleString("en-IN", {
      day:    "2-digit",
      month:  "short",
      year:   "numeric",
      hour:   "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch { return raw; }
}

// ── Tone badge colours ────────────────────────────────────────────────────────
const TONE_COLORS = {
  Professional:  { bg: "#eef2ff", text: "#3730a3", border: "#c7d2fe" },
  Casual:        { bg: "#f0fdf4", text: "#166534", border: "#bbf7d0" },
  Enthusiastic:  { bg: "#fff8e5", text: "#92600a", border: "#ffe095" },
  Apologetic:    { bg: "#fef2f2", text: "#991b1b", border: "#fecaca" },
  Concise:       { bg: "#f3f4f6", text: "#374151", border: "#e5e7eb" },
};

// ── Category config ───────────────────────────────────────────────────────────
const CATEGORY_ICONS = {
  urgent:          "🔥",
  client_inquiry:  "💼",
  meeting_request: "📅",
  newsletter:      "📰",
  spam:            "🚫",
  internal:        "🏢",
  other:           "📧",
};

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ message, type, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [onDone]);

  return (
    <div className={`${styles.toast} ${type === "success" ? styles.toastSuccess : styles.toastError}`}>
      {type === "success" ? "✅" : "❌"} {message}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function DraftModal({ draft, onClose, onApprove, onReject, onEdit }) {
  const [editBody, setEditBody] = useState(draft.ai_reply_body ?? "");
  const [saving,   setSaving]   = useState(false);
  const [acting,   setActing]   = useState(false); // approve / reject in-flight
  const [toast,    setToast]    = useState(null);  // { message, type }

  // Close on Escape key
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Prevent body scroll while modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onEdit(draft.draft_id, editBody);
      showToast("Draft saved successfully.");
    } catch {
      showToast("Failed to save draft.", "error");
    }
    setSaving(false);
  };

  const handleApprove = async () => {
    setActing(true);
    try {
      await onApprove(draft.draft_id);
      showToast("Email sent! Draft approved.");
      setTimeout(onClose, 1500);
    } catch {
      showToast("Failed to send draft.", "error");
      setActing(false);
    }
  };

  const handleReject = async () => {
    setActing(true);
    try {
      await onReject(draft.draft_id);
      showToast("Draft rejected and deleted.");
      setTimeout(onClose, 1500);
    } catch {
      showToast("Failed to reject draft.", "error");
      setActing(false);
    }
  };

  const tone     = draft.tone_used ?? "Professional";
  const toneCfg  = TONE_COLORS[tone] ?? TONE_COLORS.Professional;
  const category = draft.categorization?.category;
  const catIcon  = category ? (CATEGORY_ICONS[category] ?? "📧") : null;
  const isPending = draft.status === "pending_review";

  return (
    /* Backdrop */
    <div className={styles.backdrop} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="Draft review">

        {/* ── Header ── */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h2 className={styles.headerTitle}>Review Draft</h2>
            <div className={styles.headerMeta}>
              <span
                className={styles.toneBadge}
                style={{ background: toneCfg.bg, color: toneCfg.text, borderColor: toneCfg.border }}
              >
                {tone}
              </span>
              {catIcon && (
                <span className={styles.catBadge}>
                  {catIcon} {category?.replace(/_/g, " ")}
                </span>
              )}
              {draft.categorization?.priority && (
                <span className={`${styles.priorityBadge} ${styles[`priority_${draft.categorization.priority}`]}`}>
                  {draft.categorization.priority} priority
                </span>
              )}
            </div>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {/* ── AI summary strip ── */}
        {draft.categorization?.summary && (
          <div className={styles.summaryStrip}>
            <span className={styles.summaryIcon}>💡</span>
            <span>{draft.categorization.summary}</span>
          </div>
        )}

        {/* ── Body: two-panel ── */}
        <div className={styles.panels}>

          {/* Left – original email */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelLabel}>Original Email</span>
            </div>
            <div className={styles.emailMeta}>
              <div className={styles.emailMetaRow}>
                <span className={styles.emailMetaKey}>From</span>
                <span className={styles.emailMetaVal}>{draft.original_sender}</span>
              </div>
              <div className={styles.emailMetaRow}>
                <span className={styles.emailMetaKey}>Subject</span>
                <span className={styles.emailMetaVal}>{draft.original_subject}</span>
              </div>
              {draft.email_date && (
                <div className={styles.emailMetaRow}>
                  <span className={styles.emailMetaKey}>Date</span>
                  <span className={styles.emailMetaVal}>{formatEmailDate(draft.email_date)}</span>
                </div>
              )}
            </div>
            <div className={styles.emailBody}>
              {draft.original_body_full || draft.original_body_snippet || "No body preview available."}
            </div>
          </div>

          {/* Divider */}
          <div className={styles.divider} />

          {/* Right – AI reply */}
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span className={styles.panelLabel}>AI-Generated Reply</span>
              {isPending && (
                <span className={styles.editHint}>✏️ Editable</span>
              )}
            </div>
            {draft.ai_reply_body ? (
              <textarea
                className={styles.replyTextarea}
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                readOnly={!isPending}
                rows={14}
                placeholder="No reply generated."
              />
            ) : (
              <div className={styles.noReply}>
                No AI reply was generated for this email (newsletter / spam / skipped).
              </div>
            )}
          </div>
        </div>

        {/* ── Footer actions ── */}
        {isPending && draft.ai_reply_body && (
          <div className={styles.footer}>
            <div className={styles.footerLeft}>
              <button
                className={styles.btnReject}
                onClick={handleReject}
                disabled={acting || saving}
              >
                ❌ Reject
              </button>
            </div>
            <div className={styles.footerRight}>
              <button
                className={styles.btnSave}
                onClick={handleSave}
                disabled={saving || acting || editBody === draft.ai_reply_body}
              >
                {saving ? "Saving…" : "💾 Save Edits"}
              </button>
              <button
                className={styles.btnApprove}
                onClick={handleApprove}
                disabled={acting || saving}
              >
                {acting ? <><span className={styles.spinnerSm} /> Sending…</> : "✅ Approve & Send"}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Toast ── */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDone={() => setToast(null)}
        />
      )}
    </div>
  );
}
