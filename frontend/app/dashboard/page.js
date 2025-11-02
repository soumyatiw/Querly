// app/dashboard/page.js
"use client";

import { useState } from "react";
import { auth } from "../../firebase"; // <- Import the initialized auth
import { getIdToken } from "firebase/auth";
import styles from "./page.module.css";
import Image from "next/image";

export default function DashboardPage() {
  const [connecting, setConnecting] = useState(false);
  const [message, setMessage] = useState("");

  const BACKEND_ORIGIN = "http://localhost:8000"; // Your backend URL

  const handleConnectGmail = async () => {
    setConnecting(true);
    setMessage("");

    try {
      const user = auth.currentUser;

      if (!user) {
        setMessage("⚠️ You must be logged in to connect Gmail.");
        setConnecting(false);
        return;
      }

      const idToken = await getIdToken(user, true);

      const resp = await fetch(
        `${BACKEND_ORIGIN}/auth/google/start?idToken=${idToken}`
      );

      if (!resp.ok) {
        const err = await resp.json();
        setMessage(`❌ Error: ${err.detail || "Failed to start Gmail OAuth"}`);
        setConnecting(false);
        return;
      }

      const data = await resp.json();
      window.location.href = data.url;

    } catch (error) {
      console.error(error);
      setMessage(`❌ Unexpected error: ${error.message}`);
      setConnecting(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h2 className={styles.title}>Welcome, Soumya! 👋</h2>
        <p className={styles.subtitle}>
          Connect your Gmail account to start managing support with Querly AI.
        </p>
        <button
          className={styles.connectButton}
          onClick={handleConnectGmail}
          disabled={connecting}
        >
          <Image
            src="/gmail.svg"
            alt="Gmail"
            width={24}
            height={24}
            className={styles.gmailIcon}
          />
          {connecting ? "Connecting..." : "Connect Gmail"}
        </button>
        {message && <p className={styles.message}>{message}</p>}
        <div className={styles.tipCard}>
          💡 Querly uses secure OAuth to access your inbox safely and never stores your credentials.
        </div>
      </div>
    </div>
  );
}
