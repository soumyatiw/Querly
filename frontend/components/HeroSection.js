// components/HeroSection.js
import styles from './HeroSection.module.css';
import { useEffect, useRef } from 'react';

const icons = ['🤖', '✉️', '✏️', '🚀']; // replace with SVGs if needed

const HeroSection = () => {
  const containerRef = useRef();

  useEffect(() => {
    const container = containerRef.current;
    const moveIcons = () => {
      const iconsEl = container.querySelectorAll('.floating');
      iconsEl.forEach(icon => {
        const x = Math.random() * window.innerWidth;
        const y = Math.random() * (window.innerHeight / 2);
        icon.style.transform = `translate(${x}px, ${y}px)`;
      });
    };
    moveIcons();
    const interval = setInterval(moveIcons, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <section className={styles.hero} ref={containerRef}>
      {icons.map((icon, i) => (
        <span key={i} className={`${styles.icon} floating`}>{icon}</span>
      ))}
      <div className={styles.content}>
        <h1>Welcome to Querly</h1>
        <p>Your AI-powered customer support assistant</p>
        <div className={styles.buttons}>
          <button className={styles.btn}>Login</button>
          <button className={styles.btnPrimary}>Signup</button>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
