type IconName =
  | "users"
  | "folder"
  | "terminal"
  | "activity"
  | "sun"
  | "archive"
  | "key";

const PATHS: Record<IconName, string> = {
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
  terminal: "M4 17l6-6-6-6M12 19h8",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  sun:
    "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  archive: "M3 7h18v4H3V7zM5 11v8h14v-8M10 15h4",
  key:
    "M21 2l-2 2M7.5 13.5A4.5 4.5 0 1 1 12 9M15 6l3 3",
};

export function SettingsSectionIcon({ name }: { name: IconName }) {
  return (
    <svg
      className="settings-section__icon"
      viewBox="0 0 24 24"
      width={16}
      height={16}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
