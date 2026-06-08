type IconName =
  | "list"
  | "bolt"
  | "flask"
  | "play"
  | "gitMerge"
  | "doc"
  | "alert"
  | "x"
  | "refresh"
  | "activity"
  | "eyeCheck"
  | "unlock"
  | "merge";

const PATHS: Record<IconName, string> = {
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  bolt: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  flask: "M9 3h6M10 3v6.5L4.5 18a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9.5V3",
  play: "M8 5v14l11-7L8 5z",
  gitMerge: "M18 16.08V7.12a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 0 13 6.18V16M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 9v12",
  doc: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM14 2v6h6",
  alert: "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
  x: "M18 6L6 18M6 6l12 12",
  refresh: "M21 12a9 9 0 1 1-3-6.7M21 3v6h-6",
  activity: "M22 12h-4l-3 9L9 3 6 12H2",
  eyeCheck: "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7zM9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0",
  unlock: "M7 11V7a5 5 0 0 1 9.9-1M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z",
  merge: "M8 18l4-4-4-4M16 6l-4 4 4 4",
};

export function WorkPlanIcon({
  name,
  size = 16,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
