import { IconConvert } from "@/components/icons/Icons";

/**
 * TweakHub's mark: a solid-coral badge (the "convert" glyph — two arcs
 * cycling into each other, standing in for "any format, into any other
 * format") plus the wordmark, set in the display face. This is a fully
 * coded lockup rather than an image, so it stays crisp at every size and
 * needs no asset pipeline — genuinely the brand mark, not a filler box.
 *
 * If a separately designed logo file ever replaces it: drop the asset at
 * apps/web/public/logo.svg and swap the JSX below for
 *   <img src="/logo.svg" alt="TweakHub" height={size} style={{ display: "block" }} />
 */
interface Props {
  /** Controls the badge size in px; the wordmark scales with it. */
  size?: number;
  /** Set false on very small/cramped placements to show just the badge. */
  withWordmark?: boolean;
}

export default function Logo({ size = 34, withWordmark = true }: Props) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.32,
        flexShrink: 0,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: size,
          height: size,
          borderRadius: size * 0.28,
          background: "var(--accent-fill)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--on-accent)",
          boxShadow: "var(--shadow-accent)",
          flexShrink: 0,
        }}
      >
        <IconConvert size={size * 0.56} strokeWidth={1.9} />
      </span>
      {withWordmark && (
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 600,
            fontSize: size * 0.62,
            letterSpacing: "-0.01em",
            color: "var(--text)",
            lineHeight: 1,
          }}
        >
          TweakHub
        </span>
      )}
    </span>
  );
}
