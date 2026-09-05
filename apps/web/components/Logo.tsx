/**
 * TweakHub's real logo mark, paired with the wordmark as live text.
 *
 * apps/web/public/logo-icon.png is the "TH" icon cropped out of the
 * source lockup (which stacks the icon over a "tweakhub" wordmark
 * vertically) -- at the ~32-40px height this component actually renders
 * at across the app, a shrunk raster of that wordmark text would be
 * illegible, so the name is set as real text here instead: crisp at any
 * size, and it matches the source wordmark's all-lowercase styling. The
 * icon alone is also what's installed as the favicon/PWA icons (see
 * apps/web/public/icon-*.png, favicon.ico, manifest.json) -- built for
 * exactly this "reads fine tiny" job.
 */
interface Props {
  /** Height in px — the wordmark text scales to match. */
  size?: number;
}

export default function Logo({ size = 32 }: Props) {
  return (
    <div
      role="img"
      aria-label="TweakHub"
      style={{
        display: "flex",
        alignItems: "center",
        gap: size * 0.26,
        flexShrink: 0,
      }}
    >
      <img
        src="/logo-icon.png"
        alt=""
        width={size}
        height={size}
        style={{ display: "block", width: size, height: size }}
      />
      <span
        aria-hidden="true"
        style={{
          fontSize: size * 0.6,
          fontWeight: 600,
          letterSpacing: "-0.01em",
          color: "var(--text)",
          lineHeight: 1,
        }}
      >
        tweakhub
      </span>
    </div>
  );
}
