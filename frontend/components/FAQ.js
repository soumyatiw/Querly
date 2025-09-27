"use client";
import React, { useState } from "react";
import styles from "./FAQ.module.css";
import { Plus, Minus } from "lucide-react";

const faqs = [
  {
    question: "Is my Gmail data safe with Querly?",
    answer:
      "Absolutely. Querly connects securely with Google OAuth and never stores your email data. Everything is encrypted end-to-end.",
  },
  {
    question: "Can I customize the AI replies?",
    answer:
      "Yes! Querly learns your tone and style over time. You can also edit replies before sending — total control is yours.",
  },
  {
    question: "Does Querly support multiple Gmail accounts?",
    answer:
      "Right now, Querly supports one account per user. But multi-account support is on our roadmap and coming soon.",
  },
  {
    question: "Is there a free plan?",
    answer:
      "Yes. Querly offers a free tier so you can experience AI-powered email replies before upgrading to Pro for advanced features.",
  },
];

export default function FAQ() {
  const [activeIndex, setActiveIndex] = useState(null);

  const toggleFAQ = (index) => {
    setActiveIndex(activeIndex === index ? null : index);
  };

  return (
    <section className={styles.faqSection} id="faq">
      <h2 className={styles.title}>Frequently Asked Questions</h2>
      <div className={styles.faqList}>
        {faqs.map((faq, index) => (
          <div
            key={index}
            className={`${styles.faqItem} ${activeIndex === index ? styles.active : ""
              }`}
            onClick={() => toggleFAQ(index)}
          >
            <div className={styles.faqHeader}>
              <h3>{faq.question}</h3>
              {activeIndex === index ? (
                <Minus className={styles.icon} />
              ) : (
                <Plus className={styles.icon} />
              )}
            </div>
            <div className={styles.faqAnswer}>
              <p>{faq.answer}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
