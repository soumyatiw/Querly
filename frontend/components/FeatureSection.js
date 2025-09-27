"use client";
import React from "react";
import styles from "./FeatureSection.module.css";
import { Zap, Brain, ShieldCheck } from "lucide-react";

export default function FeatureSection() {
  const features = [
    {
      icon: <Zap size={36} strokeWidth={2.2} color="#ad1302ff" />,
      title: "Lightning Fast",
      desc: "Generate replies in seconds",
      bg: "#ffc64bff",
    },
    {
      icon: <Brain size={36} strokeWidth={2.2} color="#ad1302ff" />,
      title: "AI-Powered",
      desc: "Smart context understanding",
      bg: "#ffc64bff",
    },
    {
      icon: <ShieldCheck size={36} strokeWidth={2.2} color="#ad1302ff" />,
      title: "Professional",
      desc: "Always appropriate tone",
      bg: "#ffc64bff",
    },
  ];

  return (
    <section className={styles.features} >
      {features.map((feature, index) => (
        <div key={index} className={styles.card}>
          <div
            className={styles.iconCircle}
            style={{ backgroundColor: feature.bg }}
          >
            {feature.icon}
          </div>
          <h3>{feature.title}</h3>
          <p>{feature.desc}</p>
        </div>
      ))}
    </section>
  );
}
