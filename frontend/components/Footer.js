"use client";
import React from "react";
import styles from "./Footer.module.css";
import { Twitter, Linkedin, Github } from "lucide-react";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.container}>

        <div className={styles.brand}>
          <h2>Querly</h2>
          <p>
            Your AI-powered email assistant that makes communication effortless,
            professional, and fast.
          </p>
        </div>

        <div className={styles.links}>
          <h3>Quick Links</h3>
          <ul>
            <li><a href="#howitworks">How It Works</a></li>
            <li><a href="#faq">FAQs</a></li>
            <li><a href="#contact">Contact</a></li>
          </ul>
        </div>

        <div className={styles.social}>
          <h3>Connect</h3>
          <div className={styles.icons}>
            <a
              href="https://twitter.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Twitter"
            >
              <Twitter />
            </a>
            <a
              href="https://linkedin.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="LinkedIn"
            >
              <Linkedin />
            </a>
            <a
              href="https://github.com/soumyatiw"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="GitHub"
            >
              <Github />
            </a>
          </div>
        </div>
      </div>

      <div className={styles.bottomBar}>
        <p>© {new Date().getFullYear()} Querly. All rights reserved.</p>
      </div>
    </footer>
  );
}
