// app/dashboard/settings/page.js
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "../../../firebase";
import { getIdToken, onAuthStateChanged, signOut } from "firebase/auth";
import styles from "./page.module.css";

import {
  MdOutlineWork,
  MdOutlineSentimentSatisfied,
  MdRocketLaunch,
  MdOutlineVolunteerActivism,
  MdOutlineBolt,
  MdCheckCircleOutline,
  MdErrorOutline,
  MdOutlineUploadFile,
  MdOutlineAttachFile,
  MdOutlineSave,
  MdArrowBack,
} from "react-icons/md";

const BACKEND = "http://localhost:8000";

const TONES = [
  { value: "Professional",  label: "Professional",  Icon: MdOutlineWork,                    desc: "Polished & formal"    },
  { value: "Casual",        label: "Casual",         Icon: MdOutlineSentimentSatisfied,      desc: "Friendly & relaxed"   },
  { value: "Enthusiastic",  label: "Enthusiastic",   Icon: MdRocketLaunch,                   desc: "Energetic & upbeat"   },
  { value: "Apologetic",    label: "Apologetic",     Icon: MdOutlineVolunteerActivism,       desc: "Empathetic & careful"  },
  { value: "Concise",       label: "Concise",        Icon: MdOutlineBolt,                    desc: "Short & to the point" },
];

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

function Toast({ message, type, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500);
    return () => clearTimeout(t);
  }, [onDone]);

  const Icon = type === "success" ? MdCheckCircleOutline : MdErrorOutline;
  return (
    <div className={`${styles.toast} ${type === "success" ? styles.toastSuccess : styles.toastError}`}>
      <Icon size={17} style={{ flexShrink: 0 }} />
      {message}
    </div>
  );
}

function DropZone({ onUploadDone }) {
  const [dragging,  setDragging]  = useState(false);
  const [uploading, setUploading] = useState(false);
  const [files,     setFiles]     = useState([]);
  const [error,     setError]     = useState("");
  const inputRef = useRef(null);

  const doUpload = async (file) => {
    if (!file?.name?.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are accepted.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const token = await getIdToken(auth.currentUser, false);
      const form  = new FormData();
      form.append("file", file);
      const res  = await fetch(`${BACKEND}/knowledge-base/upload`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Upload failed");
      setFiles((prev) => [...prev, { name: file.name, chunks: data.chunks_stored }]);
      onUploadDone?.(`"${file.name}" uploaded — ${data.chunks_stored} chunks indexed.`);
    } catch (e) { setError(e.message); }
    setUploading(false);
  };

  return (
    <div
      className={`${styles.dropZone} ${dragging ? styles.dropZoneDragging : ""} ${uploading ? styles.dropZoneUploading : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); doUpload(e.dataTransfer.files?.[0]); }}
      onClick={() => !uploading && inputRef.current?.click()}
      role="button" tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" accept=".pdf" style={{ display: "none" }}
        onChange={(e) => { doUpload(e.target.files?.[0]); e.target.value = ""; }} />

      {uploading ? (
        <div className={styles.dropZoneContent}>
          <span className={styles.dropZoneSpinner} />
          <span className={styles.dropZoneText}>Indexing PDF…</span>
        </div>
      ) : (
        <div className={styles.dropZoneContent}>
          <MdOutlineUploadFile size={36} className={styles.dropZoneIcon} />
          <span className={styles.dropZoneText}>
            {dragging ? "Drop your PDF here" : "Drag & drop a PDF, or click to browse"}
          </span>
          <span className={styles.dropZoneSub}>Company FAQs, pricing sheets, product docs</span>
        </div>
      )}

      {error && <p className={styles.dropZoneError} onClick={(e) => e.stopPropagation()}>{error}</p>}

      {files.length > 0 && (
        <ul className={styles.fileList} onClick={(e) => e.stopPropagation()}>
          {files.map((f, i) => (
            <li key={i} className={styles.fileItem}>
              <MdOutlineAttachFile size={14} className={styles.fileItemIcon} />
              <span className={styles.fileItemName}>{f.name}</span>
              <span className={styles.fileItemChunks}>{f.chunks} chunks</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [user,        setUser]        = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [tone,            setTone]           = useState("Professional");
  const [businessContext, setBusinessContext] = useState("");
  const [personaNotes,    setPersonaNotes]   = useState("");
  const [loading,  setLoading]  = useState(false);
  const [saving,   setSaving]   = useState(false);
  const [toast,    setToast]    = useState(null);
  const [toneErr,  setToneErr]  = useState("");

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      if (!u) { router.replace("/login"); return; }
      setUser(u);
      setAuthLoading(false);
    });
    return () => unsub();
  }, [router]);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res  = await apiFetch("/settings");
      const data = await res.json();
      setTone(data.tone ?? "Professional");
      setBusinessContext(data.business_context ?? "");
      setPersonaNotes(data.persona_notes ?? "");
    } catch { /* use defaults */ }
    setLoading(false);
  }, []);

  useEffect(() => { if (user) fetchSettings(); }, [user, fetchSettings]);

  const handleSave = async (e) => {
    e.preventDefault();
    setToneErr("");
    if (!tone) { setToneErr("Please select a tone."); return; }
    setSaving(true);
    try {
      const res = await apiFetch("/settings", {
        method: "PUT",
        body: JSON.stringify({ tone, business_context: businessContext, persona_notes: personaNotes }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail ?? "Save failed"); }
      setToast({ message: "Settings saved!", type: "success" });
    } catch (err) { setToast({ message: err.message, type: "error" }); }
    setSaving(false);
  };

  if (authLoading || loading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.spinner} />
        <p>Loading settings…</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <nav className={styles.navbar}>
        <div className={styles.navLeft}>
          <Link href="/dashboard" className={styles.brand}>Querly</Link>
          <span className={styles.navDot} />
          <span className={styles.navLabel}>Settings</span>
        </div>
        <div className={styles.navRight}>
          <Link href="/dashboard" className={styles.btnBack}>
            <MdArrowBack size={15} />
            Dashboard
          </Link>
          <button className={styles.btnLogout} onClick={async () => { await signOut(auth); router.replace("/login"); }}>
            Sign Out
          </button>
        </div>
      </nav>

      <main className={styles.main}>
        <div className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>AI Reply Settings</h1>
          <p className={styles.pageSubtitle}>
            Customise how Querly&apos;s AI generates email replies on your behalf.
          </p>
        </div>

        <form className={styles.form} onSubmit={handleSave} noValidate>

          {/* Tone */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Reply Tone</h2>
              <p className={styles.cardDesc}>Choose how your AI replies sound. Applied to every draft generated.</p>
            </div>
            <div className={styles.toneGrid}>
              {TONES.map((t) => {
                const ToneIcon = t.Icon;
                return (
                  <label key={t.value} className={`${styles.tonePill} ${tone === t.value ? styles.tonePillActive : ""}`}>
                    <input type="radio" name="tone" value={t.value} checked={tone === t.value}
                      onChange={() => { setTone(t.value); setToneErr(""); }} className={styles.hiddenRadio} />
                    <span className={styles.toneIcon}>
                      <ToneIcon size={20} />
                    </span>
                    <span className={styles.toneName}>{t.label}</span>
                    <span className={styles.toneDesc}>{t.desc}</span>
                  </label>
                );
              })}
            </div>
            {toneErr && <p className={styles.fieldError}>{toneErr}</p>}
          </div>

          {/* Business Context */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Business Context</h2>
              <p className={styles.cardDesc}>Background about you or your company so Gemini can write more relevant replies.</p>
            </div>
            <textarea className={styles.textarea} rows={4} value={businessContext}
              onChange={(e) => setBusinessContext(e.target.value)} maxLength={1000}
              placeholder="Describe your company and how you like to communicate..." />
            <div className={styles.charCount}>{businessContext.length} / 1000</div>
          </div>

          {/* Style Notes */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Style Notes</h2>
              <p className={styles.cardDesc}>Quirks or rules you want Gemini to always follow.</p>
            </div>
            <textarea className={styles.textarea} rows={3} value={personaNotes}
              onChange={(e) => setPersonaNotes(e.target.value)} maxLength={500}
              placeholder="e.g. I never use exclamation marks. Always sign off with 'Best,'. Prefer bullet points." />
            <div className={styles.charCount}>{personaNotes.length} / 500</div>
          </div>

          {/* Knowledge Base */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Knowledge Base</h2>
              <p className={styles.cardDesc}>Upload PDFs so Querly can reference them when drafting replies.</p>
            </div>
            <DropZone onUploadDone={(msg) => setToast({ message: msg, type: "success" })} />
          </div>

          {/* Save */}
          <div className={styles.saveRow}>
            <button type="submit" className={styles.btnSave} disabled={saving}>
              {saving
                ? <><span className={styles.spinnerSm} /> Saving…</>
                : <><MdOutlineSave size={16} /> Save Settings</>
              }
            </button>
          </div>

        </form>
      </main>

      {toast && <Toast message={toast.message} type={toast.type} onDone={() => setToast(null)} />}
    </div>
  );
}
