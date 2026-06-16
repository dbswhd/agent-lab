const FIRST_RUN_ONBOARDING_DISMISSED_KEY =
  "agent-lab-first-run-onboarding-dismissed";

export function getFirstRunOnboardingDismissed(): boolean {
  try {
    return localStorage.getItem(FIRST_RUN_ONBOARDING_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setFirstRunOnboardingDismissed(dismissed: boolean): void {
  if (dismissed) {
    localStorage.setItem(FIRST_RUN_ONBOARDING_DISMISSED_KEY, "1");
    return;
  }
  localStorage.removeItem(FIRST_RUN_ONBOARDING_DISMISSED_KEY);
}
