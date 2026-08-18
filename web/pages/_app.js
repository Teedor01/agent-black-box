import "../styles/globals.css";
import Link from "next/link";
import { useRouter } from "next/router";

export default function App({ Component, pageProps }) {
  const router = useRouter();

  return (
    <div className="container">
      <h1>Agent Black Box</h1>
      <p className="subtitle">A research agent that remembers what worked, and what didn't.</p>
      <nav>
        <Link href="/" className={router.pathname === "/" ? "active" : ""}>Ask</Link>
        <Link href="/memory" className={router.pathname === "/memory" ? "active" : ""}>Memory Trace</Link>
      </nav>
      <Component {...pageProps} />
    </div>
  );
}
