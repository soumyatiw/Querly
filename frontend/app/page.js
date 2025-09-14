// app/page.js
import Navbar from '../components/Navbar';
import React from 'react';
import HeroSection from '@/components/HeroSection';


// 

export default function Home() {
  return (
    <>
      <Navbar />
      <HeroSection/>
    </>
  );
}
