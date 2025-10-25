// components/Navbar.js
import styles from './Navbar.module.css';
import Image from 'next/image';
import Link from 'next/link';

const Navbar = () => {
  return (
    <nav className={styles.navbar}>
      <div className={styles.left}>
        <Image src="/logo.png" alt="Logo" width={40} height={40} />
        <span className={styles.brand}>Querly</span>
      </div>
      <div className={styles.right}>
        <Link href="/login">
          <button className={styles.btn}>Login</button>
        </Link>
        <Link href="/signup">
          <button className={styles.btnPrimary}>Signup</button>
        </Link>
      </div>
    </nav>
  );
};

export default Navbar;
