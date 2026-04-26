// app/dashboard/page.js
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "../../firebase";
import { getIdToken, signOut, onAuthStateChanged } from "firebase/auth";
import Image from "next/image";
import styles from "./page.module.css";
import DraftModal from "../../components/DraftModal/DraftModal";

const BACKEND = "http://localhost:8000";

// ── tiny helper ───────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const user = auth.currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await getIdToken(user, /* forceRefresh= */ false);
  return fetch(`${BACKEND}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
}

// ── category display helpers ──────────────────────────────────────────────────
const CATEGORY_CONFIG = {
  urgent:          { label: "Urgent",           icon: "🔥", color: "#ef4444" },
  client_inquiry:  { label: "Client Inquiries", icon: "💼", color: "#3b82f6" },
  meeting_request: { label: "Meetings",         icon: "📅", color: "#8b5cf6" },
  newsletter:      { label: "Newsletters",      icon: "📰", color: "#10b981" },
  spam:            { label: "Spam",             icon: "🚫", color: "#6b7280" },
  internal:        { label: "Internal",         icon: "🏢", color: "#f59e0b" },
  other:           { label: "Other",            icon: "📧", color: "#64748b" },
};


// ── Date formatter ────────────────────────────────────────────────────────────
function formatEmailDate(raw) {
  if (!raw) return null;
  try {
    const d = new Date(raw);
    if (isNaN(d)) return raw;
    // If today, show time only; otherwise show date + time
    const now  = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    }
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
      + ", " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch { return raw; }
}

// ── STATUS BADGE ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    pending_review: { label: "Pending Review", cls: styles.badgePending },
    sent:           { label: "Sent",           cls: styles.badgeSent    },
    rejected:       { label: "Rejected",       cls: styles.badgeRejected},
    skipped:        { label: "Skipped",        cls: styles.badgeSkipped },
  };
  const cfg = map[status] ?? { label: status, cls: styles.badgePending };
  return <span className={`${styles.badge} ${cfg.cls}`}>{cfg.label}</span>;
}

// ── DRAFT CARD ────────────────────────────────────────────────────────────────
function DraftCard({ draft, onClick }) {
  return (
    <div className={styles.draftCard} onClick={onClick} role="button" tabIndex={0}
         onKeyDown={(e) => e.key === "Enter" && onClick()}>
      <div className={styles.draftHeader}>
        <div className={styles.draftMeta}>
          <span className={styles.draftSender}>{draft.original_sender}</span>
          <span className={styles.draftSubject}>{draft.original_subject}</span>
          {draft.email_date && (
            <span className={styles.draftTime}>{formatEmailDate(draft.email_date)}</span>
          )}
        </div>
        <div className={styles.draftRight}>
          {draft.categorization?.category && (
            <span className={styles.categoryPill}>
              {CATEGORY_CONFIG[draft.categorization.category]?.icon ?? "📧"}{" "}
              {CATEGORY_CONFIG[draft.categorization.category]?.label ?? draft.categorization.category}
            </span>
          )}
          <StatusBadge status={draft.status} />
        </div>
      </div>

      {draft.categorization?.summary && (
        <p className={styles.draftSummary}>📝 {draft.categorization.summary}</p>
      )}

      {draft.ai_reply_body ? (
        <p className={styles.draftPreview}>
          &ldquo;{draft.ai_reply_body.slice(0, 120)}{draft.ai_reply_body.length > 120 ? "…" : ""}&rdquo;
        </p>
      ) : (
        <p className={styles.draftSkipped}>No AI reply generated for this email.</p>
      )}

      {draft.status === "pending_review" && draft.ai_reply_body && (
        <p className={styles.clickHint}>Click to review, edit & approve →</p>
      )}
    </div>
  );
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router   = useRouter();

  // auth state
  const [user,        setUser]        = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  // gmail connect
  const [gmailConnected,  setGmailConnected]  = useState(null); // null = loading
  const [connectingGmail, setConnectingGmail] = useState(false);

  // process emails / job polling
  const [processing,  setProcessing]  = useState(false);
  const [jobStatus,   setJobStatus]   = useState(null); // { status, result_summary }
  const [jobMessage,  setJobMessage]  = useState("");
  const pollRef = useRef(null);

  // category summary
  const [summary,        setSummary]        = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // drafts
  const [drafts,        setDrafts]        = useState([]);
  const [draftsLoading, setDraftsLoading] = useState(false);
  const [draftsError,   setDraftsError]   = useState("");

  // upload
  const fileInputRef  = useRef(null);
  const [uploading,   setUploading]   = useState(false);
  const [uploadMsg,   setUploadMsg]   = useState("");

  // modal
  const [selectedDraft, setSelectedDraft] = useState(null);

  // time window
  const [processDays, setProcessDays] = useState(1);   // for triggering
  const [draftsDays,  setDraftsDays]  = useState(null); // null = all time

  // ── auth guard ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      if (!u) { router.replace("/login"); return; }
      setUser(u);
      setAuthLoading(false);
    });
    return () => unsub();
  }, [router]);

  // ── fetch gmail status ──────────────────────────────────────────────────────
  const fetchGmailStatus = useCallback(async () => {
    try {
      const res  = await apiFetch("/gmail/status");
      const data = await res.json();
      setGmailConnected(data.connected);
    } catch { setGmailConnected(false); }
  }, []);

  // ── fetch summary ───────────────────────────────────────────────────────────
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res  = await apiFetch("/emails/summary");
      const data = await res.json();
      setSummary(data.summary ?? {});
    } catch { /* silent */ }
    setSummaryLoading(false);
  }, []);

  // ── fetch drafts ────────────────────────────────────────────────────────────
  const fetchDrafts = useCallback(async (days) => {
    setDraftsLoading(true);
    setDraftsError("");
    try {
      const qs   = days ? `?days=${days}` : "";
      const res  = await apiFetch(`/drafts${qs}`);
      const data = await res.json();
      // PROBLEM 2 FIX: client-side safety filter — only show real AI drafts pending review
      const filtered = (data.drafts ?? []).filter(
        (d) => d.type === "ai_draft" && d.status === "pending_review"
      );
      setDrafts(filtered);
    } catch (e) { setDraftsError(e.message); }
    setDraftsLoading(false);
  }, []);

  // bootstrap everything once user is ready
  useEffect(() => {
    if (!user) return;
    fetchGmailStatus();
    fetchSummary();
    fetchDrafts(draftsDays);
  }, [user, fetchGmailStatus, fetchSummary, fetchDrafts, draftsDays]);

  // ── connect gmail ───────────────────────────────────────────────────────────
  const handleConnectGmail = async () => {
    setConnectingGmail(true);
    try {
      const token = await getIdToken(user, false);
      const res   = await fetch(`${BACKEND}/auth/google/start?idToken=${token}`);
      const data  = await res.json();
      if (data.url) window.location.href = data.url;
      else setConnectingGmail(false);
    } catch { setConnectingGmail(false); }
  };

  // ── process emails (trigger + poll) ────────────────────────────────────────
  const startPolling = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res  = await apiFetch(`/gmail/job/${jobId}`);
        const data = await res.json();
        setJobStatus(data);
        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          setProcessing(false);

          if (data.status === "done") {
            // PROBLEM 3 FIX: parse result_summary into a readable toast
            // result_summary format: "Done: 2 draft(s) created, 5 already processed, 1 skipped (not actionable), 1 skipped (AI error)."
            const summary = data.result_summary || "Processing complete!";
            setJobMessage(`✅ ${summary}`);
          } else {
            setJobMessage(`❌ Error: ${data.result_summary}`);
          }

          fetchSummary();
          fetchDrafts();
        }
      } catch { clearInterval(pollRef.current); setProcessing(false); }
    }, 3000);
  };

  const handleProcessEmails = async () => {
    setProcessing(true);
    setJobMessage("");
    setJobStatus(null);
    if (pollRef.current) clearInterval(pollRef.current);
    try {
      const res  = await apiFetch("/gmail/trigger", {
        method: "POST",
        body: JSON.stringify({ days: processDays }),
      });
      const data = await res.json();
      if (data.job_id) {
        const label = processDays === 1 ? "24 hours" : `${processDays} days`;
        setJobMessage(`⏳ Processing emails from the last ${label}…`);
        startPolling(data.job_id);
      }
    } catch (e) {
      setJobMessage(`❌ ${e.message}`);
      setProcessing(false);
    }
  };

  // cleanup polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── draft actions ─────────────────────────────────────────────────────────
  const handleApprove = async (draftId) => {
    try {
      await apiFetch(`/drafts/${draftId}/approve`, { method: "POST" });
      fetchDrafts();
    } catch (e) { throw e; }
  };

  const handleReject = async (draftId) => {
    try {
      await apiFetch(`/drafts/${draftId}/reject`, { method: "POST" });
      fetchDrafts();
    } catch (e) { throw e; }
  };

  const handleEdit = async (draftId, newBody) => {
    try {
      await apiFetch(`/drafts/${draftId}`, {
        method: "PUT",
        body: JSON.stringify({ ai_reply_body: newBody }),
      });
      fetchDrafts();
    } catch (e) { throw e; }
  };

  // ── PDF upload ──────────────────────────────────────────────────────────────
  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg("");
    try {
      const token   = await getIdToken(user, false);
      const form    = new FormData();
      form.append("file", file);
      const res  = await fetch(`${BACKEND}/knowledge-base/upload`, {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}` },
        body:    form,
      });
      const data = await res.json();
      setUploadMsg(data.message ?? "Uploaded!");
    } catch (err) { setUploadMsg(`❌ ${err.message}`); }
    setUploading(false);
    e.target.value = "";
  };

  // ── logout ──────────────────────────────────────────────────────────────────
  const handleLogout = async () => {
    await signOut(auth);
    router.replace("/login");
  };

  // ── loading screen ──────────────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.spinner} />
        <p>Loading your workspace…</p>
      </div>
    );
  }

  // ── stat cards list ─────────────────────────────────────────────────────────
  const FEATURED_CATS = ["urgent", "client_inquiry", "meeting_request", "newsletter"];

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className={styles.page}>
      {/* ── Navbar ── */}
      <nav className={styles.navbar}>
        <div className={styles.navLeft}>
          <span className={styles.brand}>Querly</span>
          <span className={styles.navDot} />
          <span className={styles.navEmail}>{user?.email}</span>
        </div>
        <div className={styles.navRight}>
          {/* PDF upload */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            style={{ display: "none" }}
            onChange={handleUpload}
          />
          <Link href="/dashboard/settings" className={styles.btnOutline}>
            ⚙️ Settings
          </Link>
          <button
            className={styles.btnOutline}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "📄 Upload PDF"}
          </button>
          <button className={styles.btnLogout} onClick={handleLogout}>
            Sign Out
          </button>
        </div>
      </nav>

      {uploadMsg && <div className={styles.uploadBanner}>{uploadMsg}</div>}

      {/* ── Main content ── */}
      <main className={styles.main}>

        {/* ── Action row ── */}
        <section className={styles.actionRow}>
          {/* Gmail connection card */}
          <div className={`${styles.actionCard} ${gmailConnected ? styles.actionCardConnected : ""}`}>
            <div className={styles.actionCardIcon}>
              <Image src="/gmail.svg" alt="Gmail" width={36} height={36} />
            </div>
            <div className={styles.actionCardBody}>
              <h3>Gmail Account</h3>
              <p className={styles.actionCardStatus}>
                {gmailConnected === null
                  ? "Checking connection…"
                  : gmailConnected
                  ? "✅ Connected and ready"
                  : "Not connected yet"}
              </p>
            </div>
            {!gmailConnected && (
              <button
                className={styles.btnPrimary}
                onClick={handleConnectGmail}
                disabled={connectingGmail || gmailConnected === null}
              >
                {connectingGmail ? "Redirecting…" : "Connect Gmail"}
              </button>
            )}
          </div>

          {/* Process card */}
          <div className={styles.actionCard}>
            <div className={styles.actionCardIcon}>⚡</div>
            <div className={styles.actionCardBody}>
              <h3>Process Emails</h3>
              <p className={styles.actionCardStatus}>
                {jobMessage || (processing ? jobStatus?.result_summary || "Running…" : "Run AI on your unread inbox")}
              </p>
            </div>
            <div className={styles.processControls}>
              <select
                className={styles.windowSelect}
                value={processDays}
                onChange={(e) => setProcessDays(Number(e.target.value))}
                disabled={processing || !gmailConnected}
              >
                <option value={1}>Last 24h</option>
                <option value={7}>Last 7 days</option>
                <option value={30}>Last 30 days</option>
              </select>
              <button
                className={`${styles.btnPrimary} ${processing ? styles.btnLoading : ""}`}
                onClick={handleProcessEmails}
                disabled={processing || !gmailConnected}
              >
                {processing ? (
                  <><span className={styles.spinnerSm} /> Processing…</>
                ) : (
                  "Process Now"
                )}
              </button>
            </div>
          </div>
        </section>

        {/* ── Email summary stats ── */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Email Summary <span className={styles.pill}>Last 7 days</span></h2>
          {summaryLoading ? (
            <div className={styles.skeletonRow}>
              {FEATURED_CATS.map((c) => <div key={c} className={styles.skeleton} />)}
            </div>
          ) : (
            <div className={styles.statsGrid}>
              {FEATURED_CATS.map((cat) => {
                const cfg   = CATEGORY_CONFIG[cat];
                const count = summary?.[cat] ?? 0;
                return (
                  <div key={cat} className={styles.statCard} style={{ "--accent": cfg.color }}>
                    <span className={styles.statIcon}>{cfg.icon}</span>
                    <span className={styles.statCount}>{count}</span>
                    <span className={styles.statLabel}>{cfg.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ── Drafts list ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>
              AI Drafts{" "}
              {drafts.filter((d) => d.status === "pending_review").length > 0 && (
                <span className={styles.pill}>
                  {drafts.filter((d) => d.status === "pending_review").length} pending
                </span>
              )}
            </h2>
            <div className={styles.draftsControls}>
              <select
                className={styles.windowSelect}
                value={draftsDays ?? "all"}
                onChange={(e) => {
                  const v = e.target.value;
                  const days = v === "all" ? null : Number(v);
                  setDraftsDays(days);
                  fetchDrafts(days);
                }}
              >
                <option value="all">All time</option>
                <option value={1}>Last 24h</option>
                <option value={7}>Last 7 days</option>
                <option value={30}>Last 30 days</option>
              </select>
              <button className={styles.btnRefresh} onClick={() => fetchDrafts(draftsDays)}>↻ Refresh</button>
            </div>
          </div>

          {draftsLoading ? (
            <div className={styles.draftsSkeleton}>
              <div className={styles.skeleton} style={{ height: 110 }} />
              <div className={styles.skeleton} style={{ height: 110 }} />
            </div>
          ) : draftsError ? (
            <p className={styles.errorMsg}>❌ {draftsError}</p>
          ) : drafts.length === 0 ? (
            <div className={styles.emptyState}>
              <span className={styles.emptyIcon}>📭</span>
              <p>No drafts yet. Process your emails to get started.</p>
            </div>
          ) : (
            <div className={styles.draftsList}>
              {drafts.map((d) => (
                <DraftCard
                  key={d.draft_id}
                  draft={d}
                  onClick={() => setSelectedDraft(d)}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {/* ── Draft Review Modal ── */}
      {selectedDraft && (
        <DraftModal
          draft={selectedDraft}
          onClose={() => { setSelectedDraft(null); fetchDrafts(); }}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEdit}
        />
      )}
    </div>
  );
}
