type IconProps = {
  size?: number;
};

export function LogoMark({ size = 38 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="12" fill="currentColor" />
      <path
        d="M12 13.5h16v4H18v3h9v4h-9v6h-6v-17Z"
        fill="white"
      />
    </svg>
  );
}

export function RefreshIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M20 11a8 8 0 1 0-2.34 5.66M20 11V5m0 6h-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
