import Link from "next/link";

/**
 * Site-wide footer — the only place these policy pages are linked from
 * today. There was no shared footer component before this (just an
 * inline "Forgot your password?" link on the homepage, which is
 * untouched). Rendered once from RootLayout (apps/web/app/layout.tsx) so
 * it appears on every page without each page wiring it in itself.
 */
export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="legal-footer">
      <span>© {year} TweakHub. All rights reserved.</span>
      <nav aria-label="Legal">
        <Link href="/terms">Terms of Service</Link>
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/refund-policy">Refund Policy</Link>
        <Link href="/acceptable-use">Acceptable Use</Link>
      </nav>
    </footer>
  );
}
