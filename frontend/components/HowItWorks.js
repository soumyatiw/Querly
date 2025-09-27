"use client";
import React, { useEffect, useRef, useState } from "react";
import styles from "./HowItWorks.module.css";

const steps = [
  {
    step: "Step 1",
    title: "Seamless Gmail Connection",
    text: "Easily and securely link your Gmail account to Querly with one click, ensuring total privacy and encryption.",
  },
  {
    step: "Step 2",
    title: "AI Understanding",
    text: "Querly’s AI deeply reads and analyzes your emails, recognizing tone, urgency, and context — just like a human assistant.",
  },
  {
    step: "Step 3",
    title: "Crafted Professional Replies",
    text: "Elegant, context-aware responses are drafted in seconds. Each reply is tailored to match your voice and style.",
  },
  {
    step: "Step 4",
    title: "Review & Send Instantly",
    text: "Simply review the AI-suggested reply and hit send. Your inbox becomes effortless, efficient, and stress-free.",
  },
];

export default function HowItWorks() {
  const timelineRef = useRef(null);
  const [lineHeight, setLineHeight] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      if (!timelineRef.current) return;

      const rect = timelineRef.current.getBoundingClientRect();
      const windowHeight = window.innerHeight;

      // take center of the screen as reference
      const center = windowHeight / 1.7;
      const start = rect.top;
      const end = rect.bottom;

      if (center < start) {
        setLineHeight(0);
      } else if (center > end) {
        setLineHeight(100);
      } else {
        const progress = ((center - start) / (end - start)) * 100;
        setLineHeight(progress);
      }
    };

    window.addEventListener("scroll", handleScroll);
    handleScroll();

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <section className={styles.timelineSection}>
      <h2 className={styles.sectionTitle} id='howitworks'>How Querly Works</h2>
      <div
        ref={timelineRef}
        className={styles.timeline}
        style={{ ["--line-progress"]: `${lineHeight}%` }}
      >
        {steps.map((step, index) => (
          <div key={index} className={styles.timelineItem}>
            <div className={styles.point}></div>
            <div className={styles.content}>
              <h4 className={styles.step}>{step.step}</h4>
              <h3 className={styles.title}>{step.title}</h3>
              <p className={styles.text}>{step.text}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
