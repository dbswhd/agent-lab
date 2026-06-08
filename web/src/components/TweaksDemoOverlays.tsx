import { MacAlert } from "./MacAlert";
import { useTweaksDemo } from "../context/TweaksDemoContext";

/** MacAlert triggered from Tweaks panel (delete confirm demo). */
export function TweaksDemoOverlays() {
  const demo = useTweaksDemo();

  return (
    <MacAlert
      open={demo.showMacAlert}
      title="세션을 삭제할까요?"
      message="이 작업은 되돌릴 수 없습니다. 세션 폴더와 chat 기록이 영구 삭제됩니다."
      onClose={() => demo.setShowMacAlert(false)}
      buttons={[
        {
          label: "취소",
          variant: "cancel",
          onClick: () => demo.setShowMacAlert(false),
        },
        {
          label: "삭제",
          variant: "destructive",
          onClick: () => demo.setShowMacAlert(false),
        },
      ]}
    />
  );
}
