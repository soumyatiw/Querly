// components/Navbar.js
import styles from './Navbar.module.css';
import Image from 'next/image';

const Navbar = () => {
  return (
    <nav className={styles.navbar}>
      <div className={styles.left}>
        <Image src="/logo.png" alt="Logo" width={40} height={40} />
        <span className={styles.brand}>Querly</span>
      </div>
      <div className={styles.right}>
        <button className={styles.btn}>Login</button>
        <button className={styles.btnPrimary}>Signup</button>
      </div>
    </nav>
  );
};

export default Navbar;
