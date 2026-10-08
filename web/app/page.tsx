import { API_URL } from "@/lib/config";
import styles from "./page.module.css";

// Checked on every request, not once at build time (the API isn't running during `next build`)
export const dynamic = "force-dynamic";

// Step 1 placeholder: proves the page can reach FastAPI. Asked server-side, so it
// calls the API directly instead of going through the /api rewrite.
const isApiUp = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
};

export default async function Home() {
  const apiUp = await isApiUp();

  return (
    <main className={styles.main}>
      <h1 className={styles.title}>OpenArt</h1>
      <p className={styles.lead}>
        Find open calls for artists, check your eligibility and prepare your application.
      </p>
      <p className={styles.status}>
        API:{" "}
        {apiUp ? (
          <span className={styles.ok}>connected</span>
        ) : (
          <span className={styles.error}>not reachable</span>
        )}
      </p>
    </main>
  );
}
