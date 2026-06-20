// Brand logo for a client when we have one, else a monogram fallback.
// customer_id -> public asset. Add a logo: drop the file in /public/logos and map it here.
const LOGOS: Record<string, string> = {
  "coinbase-global": "/logos/coinbase.svg",
};

function monogram(name: string): string {
  const words = name.replace(/[^A-Za-z0-9 ]/g, "").trim().split(/\s+/);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

export function CompanyLogo({
  customerId,
  name,
  size = 48,
  className = "",
}: {
  customerId: string;
  name: string;
  size?: number;
  className?: string;
}) {
  const src = LOGOS[customerId];
  const box = { width: size, height: size };

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={`${name} logo`}
        style={box}
        className={`shrink-0 rounded-xl object-contain ${className}`}
      />
    );
  }

  return (
    <div
      style={{ ...box, background: "linear-gradient(135deg,#0d2936,#14b8a6)", fontSize: size * 0.34 }}
      className={`flex shrink-0 items-center justify-center rounded-xl font-bold text-white ${className}`}
    >
      {monogram(name)}
    </div>
  );
}
