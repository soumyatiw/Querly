"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { auth } from "../../firebase";
import { signInWithEmailAndPassword, GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import styles from "./page.module.css";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    try {
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      setMessage(`User logged in: ${userCredential.user.email}`);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const handleGoogleLogin = async () => {
    const provider = new GoogleAuthProvider();
    try {
      const result = await signInWithPopup(auth, provider);
      setMessage(`Logged in with Google: ${result.user.email}`);
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.title}>Login</h2>
        </div>
        <form className={styles.form} onSubmit={handleEmailLogin}>
          <input
            className={styles.input}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            className={styles.input}
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button className={styles.primaryButton} type="submit">Login</button>
        </form>
        <div className={styles.divider}>
          <span className={styles.dividerText}>OR</span>
        </div>
        <button className={styles.googleButton} type="button" onClick={handleGoogleLogin}>
          <Image src="/google-icon.svg" alt="Google" width={24} height={24} className={styles.googleIcon} />
          Login with Google
        </button>

        {/* Signup link */}
        <p className={styles.footer}>
          Don’t have an account?{" "}
          <Link href="/signup" className={styles.link}>Signup</Link>
        </p>

        {message && (
          <p className={`${styles.message} ${message.includes('logged in') || message.includes('Google') ? styles.success : styles.error}`}>
            {message}
          </p>
        )}
      </div>
    </div>
  );
}
