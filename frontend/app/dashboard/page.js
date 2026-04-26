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

import {
  MdOutlineLocalFireDepartment,
  MdOutlineWork,
  MdOutlineCalendarMonth,
  MdOutlineNewspaper,
  MdBlock,
  MdOutlineCorporateFare,
  MdOutlineEmail,
  MdOutlineSettings,
  MdOutlineUploadFile,
  MdOutlineRefresh,
  MdOutlineInbox,
  MdCheckCircleOutline,
  MdErrorOutline,
  MdOutlineBolt,
  MdOutlineNotes,
  MdArrowForward,
  MdOutlineHourglassEmpty,
  MdWifiOff,
} from "react-icons/md";

const BACKEND = "http://localhost:8000";

async function apiFetch(path, options = {}) {
  const user = auth.currentUser;
  if (!user) throw new Error("Not authenticated");
  const token = await getIdToken(user, false);
  return fetch(`${BACKEND}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers ?? {}),
    },
  });
}

const CATEGORY_CONFIG = {
  urgent:          { label: "Urgent",           Icon: MdOutlineLocalFireDepartment, color: "#ef4444" },
  client_inquiry:  { label: "Client Inquiry",   Icon: MdOutlineWork,                color: "#3b82f6" },
  meeting_request: { label: "Meeting",          Icon: MdOutlineCalendarMonth,       color: "#8b5cf6" },
  newsletter:      { label: "Newsletter",       Icon: MdOutlineNewspaper,           color: "#10b981" },
  spam:            { label: "Spam",             Icon: MdBlock,                      color: "#6b7280" },
  internal:        { label: "Internal",         Icon: MdOutlineCorporateFare,       color: "#f59e0b" },
  other:           { label: "Other",            Icon: MdOutlineEmail,               color: "#64748b" },
};

const TIME_OPTIONS = [
  { value: 1,    label: "Last 24h"   },
  { value: 7,    label: "Last 7d"    },
  { value: 30,   label: "Last 30d"   },
  { value: null, label: "All time"   },
];

function formatEmailDate(raw) {
  if (!raw) return null;
  try {
    const d = new Date(raw);
    if (isNaN(d)) return raw;
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
      + ", " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch { return raw; }
}

function StatusBadge({ status }) {
  const map = {
    pending_review: { label: "Pending",  cls: styles.badgePending  },
    sent:           { label: "Sent",     cls: styles.badgeSent     },
    rejected:       { label: "Rejected", cls: styles.badgeRejected },
    skipped:        { label: "Skipped",  cls: styles.badgeSkipped  },
  };
  const cfg = map[status] ?? { label: status, cls: styles.badgePending };
  return <span className={`${styles.badge} ${cfg.cls}`}>{cfg.label}</span>;
}

function DraftCard({ draft, onClick }) {
  const catCfg  = CATEGORY_CONFIG[draft.categorization?.category];
  const CatIcon = catCfg?.Icon ?? MdOutlineEmail;

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
            <span className={styles.categoryPill} style={{ color: catCfg?.color }}>
              <CatIcon size={12} />
              {catCfg?.label ?? draft.categorization.category}
            </span>
          )}
          <StatusBadge status={draft.status} />
        </div>
      </div>

      {draft.categorization?.summary && (
        <p className={styles.draftSummary}>
          <MdOutlineNotes size={13} style={{ verticalAlign: "middle", marginRight: 4, flexShrink: 0 }} />
          {draft.categorization.summary}
        </p>
      )}

      {draft.ai_reply_body ? (
        <p className={styles.draftPreview}>
          &ldquo;{draft.ai_reply_body.slice(0, 130)}{draft.ai_reply_body.length > 130 ? "…" : ""}&rdquo;
        </p>
      ) : (
        <p className={styles.draftSkipped}>No AI reply generated for this email.</p>
      )}

      {draft.status === "pending_review" && draft.ai_reply_body && (
        <p className={styles.clickHint}>
          Review, edit &amp; approve
          <MdArrowForward size={12} style={{ verticalAlign: "middle", marginLeft: 4 }} />
        </p>
      )}
    </div>
  );
}

// ── Job status banner ─────────────────────────────────────────────────────────
function JobBanner({ message }) {
  if (!message) return null;
  const [type, ...rest] = message.split(":");
  const text = rest.join(":");
  const isDone    = type === "done";
  const isError   = type === "error";
  const isPending = type === "pending";
  return (
    <div className={`${styles.jobBanner} ${isDone ? styles.jobBannerDone : isError ? styles.jobBannerError : styles.jobBannerPending}`}>
      {isDone    && <MdCheckCircleOutline size={16} />}
      {isError   && <MdErrorOutline       size={16} />}
      {isPending && <MdOutlineHourglassEmpty size={16} />}
      <span>{text}</span>
    </div>
  );
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();

  const [user,           setUser]           = useState(null);
  const [authLoading,    setAuthLoading]    = useState(true);
  const [gmailConnected, setGmailConnected] = useState(null);
  const [connectingGmail,setConnectingGmail]= useState(false);
  const [processing,     setProcessing]     = useState(false);
  const [jobStatus,      setJobStatus]      = useState(null);
  const [jobMessage,     setJobMessage]     = useState("");
  const pollRef = useRef(null);

  const [summary,        setSummary]        = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [drafts,         setDrafts]         = useState([]);
  const [draftsLoading,  setDraftsLoading]  = useState(false);
  const [draftsError,    setDraftsError]    = useState("");

  const fileInputRef = useRef(null);
  const [uploading,  setUploading]  = useState(false);
  const [uploadMsg,  setUploadMsg]  = useState("");

  const [selectedDraft, setSelectedDraft] = useState(null);

  // Single shared time window — drives both Process and Drafts
  const [timeDays, setTimeDays] = useState(1);

  // ── auth ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      if (!u) { router.replace("/login"); return; }
      setUser(u);
      setAuthLoading(false);
    });
    return () => unsub();
  }, [router]);

  // ── data fetches ────────────────────────────────────────────────────────────
  const fetchGmailStatus = useCallback(async () => {
    try {
      const res  = await apiFetch("/gmail/status");
      const data = await res.json();
      setGmailConnected(data.connected);
    } catch { setGmailConnected(false); }
  }, []);

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res  = await apiFetch("/emails/summary");
      const data = await res.json();
      setSummary(data.summary ?? {});
    } catch { /* silent */ }
    setSummaryLoading(false);
  }, []);

  const fetchDrafts = useCallback(async (days) => {
    setDraftsLoading(true);
    setDraftsError("");
    try {
      const qs   = days ? `?days=${days}` : "";
      const res  = await apiFetch(`/drafts${qs}`);
      const data = await res.json();
      const filtered = (data.drafts ?? []).filter(
        (d) => d.type === "ai_draft" && d.status === "pending_review"
      );
      setDrafts(filtered);
    } catch (e) { setDraftsError(e.message); }
    setDraftsLoading(false);
  }, []);

  useEffect(() => {
    if (!user) return;
    fetchGmailStatus();
    fetchSummary();
    fetchDrafts(timeDays);
  }, [user, fetchGmailStatus, fetchSummary, fetchDrafts, timeDays]);

  // when time window changes, refresh drafts immediately
  const handleTimeChange = (days) => {
    setTimeDays(days);
    fetchDrafts(days);
  };

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

  // ── process emails ──────────────────────────────────────────────────────────
  const startPolling = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res  = await apiFetch(`/gmail/job/${jobId}`);
        const data = await res.json();
        setJobStatus(data);
        if (data.status === "done" || data.status === "error") {
          clearInterval(pollRef.current);
          setProcessing(false);
          setJobMessage(data.status === "done"
            ? `done:${data.result_summary || "Processing complete!"}`
            : `error:${data.result_summary}`
          );
          fetchSummary();
          fetchDrafts(timeDays);
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
        body: JSON.stringify({ days: timeDays ?? 1 }),
      });
      const data = await res.json();
      if (data.job_id) {
        const label = timeDays === 1 ? "24 hours" : timeDays ? `${timeDays} days` : "all time";
        setJobMessage(`pending:Processing emails from ${label}…`);
        startPolling(data.job_id);
      }
    } catch (e) {
      setJobMessage(`error:${e.message}`);
      setProcessing(false);
    }
  };

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── draft actions ─────────────────────────────────────────────────────────
  const handleApprove = async (draftId) => {
    await apiFetch(`/drafts/${draftId}/approve`, { method: "POST" });
    fetchDrafts(timeDays);
  };

  const handleReject = async (draftId) => {
    await apiFetch(`/drafts/${draftId}/reject`, { method: "POST" });
    fetchDrafts(timeDays);
  };

  const handleEdit = async (draftId, newBody) => {
    await apiFetch(`/drafts/${draftId}`, {
      method: "PUT",
      body: JSON.stringify({ ai_reply_body: newBody }),
    });
    fetchDrafts(timeDays);
  };

  // ── PDF upload ──────────────────────────────────────────────────────────────
  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg("");
    try {
      const token = await getIdToken(user, false);
      const form  = new FormData();
      form.append("file", file);
      const res  = await fetch(`${BACKEND}/knowledge-base/upload`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
      });
      const data = await res.json();
      setUploadMsg(data.message ?? "Uploaded!");
    } catch (err) { setUploadMsg(`Upload failed: ${err.message}`); }
    setUploading(false);
    e.target.value = "";
  };

  const handleLogout = async () => {
    await signOut(auth);
    router.replace("/login");
  };

  if (authLoading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.spinner} />
        <p>Loading your workspace…</p>
      </div>
    );
  }

  const FEATURED_CATS = ["urgent", "client_inquiry", "meeting_request", "newsletter"];
  const pendingCount  = drafts.filter((d) => d.status === "pending_review").length;

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
          <input ref={fileInputRef} type="file" accept=".pdf"
            style={{ display: "none" }} onChange={handleUpload} />
          <Link href="/dashboard/settings" className={styles.btnOutline}>
            <MdOutlineSettings size={15} />
            Settings
          </Link>
          <button className={styles.btnOutline}
            onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            <MdOutlineUploadFile size={15} />
            {uploading ? "Uploading…" : "Upload PDF"}
          </button>
          <button className={styles.btnLogout} onClick={handleLogout}>Sign Out</button>
        </div>
      </nav>

      {uploadMsg && <div className={styles.uploadBanner}>{uploadMsg}</div>}
      <JobBanner message={jobMessage} />

      {/* ── Main ── */}
      <main className={styles.main}>

        {/* ── Action row ── */}
        <section className={styles.actionRow}>

          {/* Gmail card */}
          <div className={`${styles.actionCard} ${gmailConnected ? styles.actionCardConnected : ""}`}>
            <div className={styles.actionCardIcon}>
              <Image src="/gmail.png" alt="Gmail" width={34} height={26} style={{ objectFit: "contain" }} />
            </div>
            <div className={styles.actionCardBody}>
              <h3>Gmail Account</h3>
              <p className={`${styles.actionCardStatus} ${gmailConnected ? styles.statusConnected : ""}`}>
                {gmailConnected === null
                  ? "Checking…"
                  : gmailConnected
                  ? <><MdCheckCircleOutline size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />Connected and ready</>
                  : <><MdWifiOff size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />Not connected</>
                }
              </p>
            </div>
            {!gmailConnected && (
              <button className={styles.btnPrimary} onClick={handleConnectGmail}
                disabled={connectingGmail || gmailConnected === null}>
                {connectingGmail ? "Redirecting…" : "Connect Gmail"}
              </button>
            )}
          </div>

          {/* Process card */}
          <div className={styles.actionCard}>
            <div className={styles.actionCardIcon}>
              <MdOutlineBolt size={28} color="#ffc64b" />
            </div>
            <div className={styles.actionCardBody}>
              <h3>Process Emails</h3>
              <p className={styles.actionCardStatus}>
                {processing
                  ? jobStatus?.result_summary || "Running AI on your inbox…"
                  : "Select a window and run AI on your inbox"}
              </p>
            </div>
            {/* Single combined control */}
            <div className={styles.processControls}>
              <div className={styles.timeSegment}>
                {TIME_OPTIONS.map((opt) => (
                  <button
                    key={String(opt.value)}
                    className={`${styles.segBtn} ${timeDays === opt.value ? styles.segBtnActive : ""}`}
                    onClick={() => handleTimeChange(opt.value)}
                    disabled={processing}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <button
                className={`${styles.btnPrimary} ${processing ? styles.btnLoading : ""}`}
                onClick={handleProcessEmails}
                disabled={processing || !gmailConnected}
              >
                {processing
                  ? <><span className={styles.spinnerSm} /> Processing…</>
                  : "Run Now"}
              </button>
            </div>
          </div>

        </section>

        {/* ── Email summary stats ── */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>
              Email Summary
              <span className={styles.pill}>Last 7 days</span>
            </h2>
          </div>
          {summaryLoading ? (
            <div className={styles.skeletonRow}>
              {FEATURED_CATS.map((c) => <div key={c} className={styles.skeleton} />)}
            </div>
          ) : (
            <div className={styles.statsGrid}>
              {FEATURED_CATS.map((cat) => {
                const cfg     = CATEGORY_CONFIG[cat];
                const count   = summary?.[cat] ?? 0;
                const CatIcon = cfg.Icon;
                return (
                  <div key={cat} className={styles.statCard} style={{ "--accent": cfg.color }}>
                    <span className={styles.statIcon}>
                      <CatIcon size={30} color="#ffc64b" />
                    </span>
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
              AI Drafts
              {pendingCount > 0 && (
                <span className={styles.pill}>{pendingCount} pending</span>
              )}
            </h2>
            <button className={styles.btnRefresh} onClick={() => fetchDrafts(timeDays)}>
              <MdOutlineRefresh size={15} />
              Refresh
            </button>
          </div>

          {draftsLoading ? (
            <div className={styles.draftsSkeleton}>
              <div className={styles.skeleton} style={{ height: 110 }} />
              <div className={styles.skeleton} style={{ height: 110 }} />
            </div>
          ) : draftsError ? (
            <p className={styles.errorMsg}>
              <MdErrorOutline size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />
              {draftsError}
            </p>
          ) : drafts.length === 0 ? (
            <div className={styles.emptyState}>
              <MdOutlineInbox size={52} color="#d1d5db" />
              <p>No drafts yet — process your emails above to get started.</p>
            </div>
          ) : (
            <div className={styles.draftsList}>
              {drafts.map((d) => (
                <DraftCard key={d.draft_id} draft={d} onClick={() => setSelectedDraft(d)} />
              ))}
            </div>
          )}
        </section>
      </main>

      {selectedDraft && (
        <DraftModal
          draft={selectedDraft}
          onClose={() => { setSelectedDraft(null); fetchDrafts(timeDays); }}
          onApprove={handleApprove}
          onReject={handleReject}
          onEdit={handleEdit}
        />
      )}
    </div>
  );
}
