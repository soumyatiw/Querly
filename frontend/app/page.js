// app/page.js
import Navbar from '../components/Navbar';
import React from 'react';
import HeroSection from '@/components/HeroSection';
import FeatureSection from '@/components/FeatureSection';
import styles from "./page.module.css";

// 

export default function Home() {
  return (
    <div className={styles.container}>
      <Navbar />
      <HeroSection/>
      <FeatureSection/>
    </div>
  );
}
