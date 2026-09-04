/**
 * Small, hand-drawn icon set used across the marketing shell (hero, trust
 * strip, category cards, tool tabs). Deliberately not an icon-font/library
 * dependency — every icon here is a plain inline SVG so it inherits
 * currentColor, needs no extra network request, and stays visually
 * consistent (24x24 viewBox, 1.6 stroke, rounded joins) as one drawn set.
 */
import { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base(props: IconProps) {
  const { size = 22, ...rest } = props;
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...rest,
  };
}

export function IconPdf(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v4h4" />
      <path d="M8.5 17.5v-4h1.1a1.2 1.2 0 1 1 0 2.4H8.5" />
      <path d="M12.3 13.5v4h.9a1.6 1.6 0 0 0 1.6-1.6v-.8a1.6 1.6 0 0 0-1.6-1.6h-.9Z" />
      <path d="M17.5 13.5h-1.9v4M15.6 15.4h1.5" />
    </svg>
  );
}

export function IconImage(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4.5" width="18" height="15" rx="2.2" />
      <circle cx="9" cy="10" r="1.7" />
      <path d="m4 17 5-5 3.2 3.2L16 11l4 4.4" />
    </svg>
  );
}

export function IconVideo(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="5.5" width="13.5" height="13" rx="2.2" />
      <path d="M16.5 10.2 21 7.5v9l-4.5-2.7" />
      <path d="M8.3 9.6v5.8l4.6-2.9-4.6-2.9Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconAudio(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 12.5v-1.6M7.4 15.4V8.6M10.8 18V6M14.2 15.4V8.6M17.6 12.9v-1.8M21 11.7v.6" />
    </svg>
  );
}

export function IconDocument(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6.5 2.8h7.3L18.5 7.5V20a1.2 1.2 0 0 1-1.2 1.2H6.5A1.2 1.2 0 0 1 5.3 20V4A1.2 1.2 0 0 1 6.5 2.8Z" />
      <path d="M13.8 2.8v3.9a.8.8 0 0 0 .8.8h3.9" />
      <path d="M8.3 12h6.5M8.3 15h6.5M8.3 9h3" />
    </svg>
  );
}

export function IconConvert(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 9.5A8 8 0 0 1 18.6 6.2M20 4.5v3.4h-3.4" />
      <path d="M20 14.5a8 8 0 0 1-14.6 3.3M4 19.5v-3.4h3.4" />
    </svg>
  );
}

export function IconShield(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 2.6 19.5 5.4V11c0 5.3-3.2 8.7-7.5 10.4C7.7 19.7 4.5 16.3 4.5 11V5.4L12 2.6Z" />
      <path d="m9 12 2.1 2.1L15.4 9.8" />
    </svg>
  );
}

export function IconBolt(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12.8 2.6 5 13.8h5.4l-1.2 7.6L18 10.2h-5.4l1.2-7.6Z" strokeLinejoin="round" />
    </svg>
  );
}

export function IconGlobe(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9Z" />
    </svg>
  );
}

export function IconCheck(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="m4.5 12.8 4.8 4.8L19.5 7.3" />
    </svg>
  );
}

export function IconArrowRight(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4.5 12h15M13 5.5 19.5 12 13 18.5" />
    </svg>
  );
}

export function IconUpload(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 15.5V4.5M8 8.3 12 4l4 4.3" />
      <path d="M4.5 15v3.3a1.7 1.7 0 0 0 1.7 1.7h11.6a1.7 1.7 0 0 0 1.7-1.7V15" />
    </svg>
  );
}

export function IconWallet(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7.5a1.8 1.8 0 0 1 1.8-1.8h11.4A1.8 1.8 0 0 1 19 7.5v9.2a1.8 1.8 0 0 1-1.8 1.8H5.8A1.8 1.8 0 0 1 4 16.7V7.5Z" />
      <path d="M14.5 12.6h3.3a1.2 1.2 0 0 0 0-2.4h-3.3a1.2 1.2 0 0 0 0 2.4Z" />
      <path d="M4 9.6h15" />
    </svg>
  );
}

export function IconClock(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12.5" r="8.5" />
      <path d="M12 7.5V12l3.2 2" />
    </svg>
  );
}
