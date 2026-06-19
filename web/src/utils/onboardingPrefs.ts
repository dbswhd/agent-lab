const FIRST_RUN_ONBOARDING_DISMISSED_KEY =
  "agent-lab-first-run-onboarding-dismissed";
const FIRST_RUN_ONBOARDING_VERSION_KEY =
  "agent-lab-first-run-onboarding-version";
const FIRST_RUN_ONBOARDING_VERSION = "p1f";

export function getFirstRunOnboardingDismissed(): boolean {
  try {
    return (
      localStorage.getItem(FIRST_RUN_ONBOARDING_VERSION_KEY) ===
      FIRST_RUN_ONBOARDING_VERSION
    );
  } catch {
    return false;
  }
}

export function setFirstRunOnboardingDismissed(dismissed: boolean): void {
  if (dismissed) {
    localStorage.setItem(
      FIRST_RUN_ONBOARDING_VERSION_KEY,
      FIRST_RUN_ONBOARDING_VERSION,
    );
    localStorage.setItem(FIRST_RUN_ONBOARDING_DISMISSED_KEY, "1");
    return;
  }
  localStorage.removeItem(FIRST_RUN_ONBOARDING_VERSION_KEY);
  localStorage.removeItem(FIRST_RUN_ONBOARDING_DISMISSED_KEY);
}
