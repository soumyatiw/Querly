"use client";

import { useState } from "react";
import { auth } from "../../firebase";
import { createUserWithEmailAndPassword, GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import styles from "./page.module.css";
import Image from "next/image";

export default function SignupPage() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [message, setMessage] = useState("");

    const handleEmailSignup = async (e) => {
        e.preventDefault();
        try {
            const userCredential = await createUserWithEmailAndPassword(auth, email, password);
            setMessage(`User signed up: ${userCredential.user.email}`);
        } catch (error) {
            setMessage(error.message);
        }
    };

    const handleGoogleSignup = async () => {
        const provider = new GoogleAuthProvider();
        try {
            const result = await signInWithPopup(auth, provider);
            setMessage(`Signed in with Google: ${result.user.email}`);
        } catch (error) {
            setMessage(error.message);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.title}>Signup</h2>
                </div>
                <form className={styles.form} onSubmit={handleEmailSignup}>
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
                    <button className={styles.primaryButton} type="submit">Sign Up</button>
                </form>
                <div className={styles.divider}>
                    <span className={styles.dividerText}>OR</span>
                </div>
                <button className={styles.googleButton} type="button" onClick={handleGoogleSignup}>
                    <Image src="/google-icon.svg" alt="Google" width={24} height={24} className={styles.googleIcon} />
                    Sign up with Google
                </button>
                {message && <p className={`${styles.message} ${message.includes('User') ? styles.success : styles.error}`}>{message}</p>}
            </div>
        </div>
    );
}
