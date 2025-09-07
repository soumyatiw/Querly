"use client";
import React from "react";
import styles from "./HeroSection.module.css";

const icons = [
  "/1.png",
  "/2.png",
  "/3.png",
  "/4.png",
  "/5.png",
];

export default function HeroSection() {
  return (
    <div className={styles.hero}>
      <h1 className={styles.heroTitle}>Querly</h1>
      <p className={styles.heroSubtitle}>Your AI Powered Email Assistant</p>
      <button className={styles.getStarted}>Get Started</button>

      <div className={styles.orbit}>
        {icons.map((src, index) => (
          <img key={index} src={src} className={styles.icon} alt={`icon ${index + 1}`} />
        ))}
      </div>
    </div>
  );
}
