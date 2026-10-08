import Link from "next/link";
import styles from "./layout.module.css";

// The frame shared by /login and /signup: the black brand panel on the left,
// the form (the page itself) on the right. Two columns on desktop, stacked on phones.
export default function AuthLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={styles.shell}>
      <section className={styles.brand} aria-label="OpenArt">
        <Link href="/" className={styles.wordmark}>
          OpenArt
        </Link>
        <div>
          <p className={styles.headline}>
            Find the calls that fit your practice<span className={styles.stop}>.</span>
          </p>
          <ul className={styles.pills}>
            <li>Residencies</li>
            <li>Grants</li>
            <li>Commissions</li>
          </ul>
        </div>
      </section>
      <main id="main" className={styles.formPanel}>
        <div className={styles.formColumn}>{children}</div>
      </main>
    </div>
  );
}
