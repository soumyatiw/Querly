
import Navbar from '../components/Navbar';
import React from 'react';
import HeroSection from '@/components/HeroSection';
import FeatureSection from '@/components/FeatureSection';
import HowItWorks from '@/components/HowItWorks';
import styles from "./page.module.css";
import Footer from '@/components/Footer';
import FAQ from '@/components/FAQ';



export default function Home() {
  return (
    <div className={styles.container}>
      <Navbar />
      <HeroSection />
      <HowItWorks />
      <FeatureSection />
      <FAQ />
      <Footer />
    </div>
  );
}
