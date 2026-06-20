/**
 * AMINA wordmark — geometric recreation of the brand logo (open chevron A's,
 * thin strokes, rounded caps). Inline SVG so it inherits color via currentColor
 * (white on the dark sidebar, petrol on light). Swap for the official vector by
 * dropping it at public/amina-logo.svg and replacing this with an <img>.
 */
export function AminaLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 190 52"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="AMINA"
    >
      {/* A */}
      <polyline points="6,44 21,9 36,44" />
      {/* M */}
      <polyline points="48,44 48,9 66,30 84,9 84,44" />
      {/* I */}
      <line x1="98" y1="9" x2="98" y2="44" />
      {/* N */}
      <polyline points="112,44 112,9 142,44 142,9" />
      {/* A */}
      <polyline points="154,44 169,9 184,44" />
    </svg>
  );
}
