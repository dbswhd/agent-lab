# plan.md

## 지금 논의 중인 것

Figma에 있는 **macOS 26 (macOS Tahoe) 컴포넌트 키트**를 내보내는 방법. 단순 이미지 에셋(PNG/SVG) 추출인지, 개발용 CSS·토큰 이식인지 목적이 아직 명확하지 않은 상태에서 논의 진행 중.

---

## 합의된 점

- **내보내기 목적에 따라 방법이 완전히 달라짐** — 에셋 추출 vs 개발 이식은 별개의 흐름
- 기본 에셋 export 흐름: 컴포넌트 선택 → 우측 패널 `Export` → `+` → 포맷(SVG/PDF/PNG) 선택 → Export 버튼
- **Liquid Glass / blur / vibrancy 효과는 PNG·SVG로 내보내도 거의 살아남지 않음** → Dev Mode 또는 CSS 쪽이 적합
- Apple 공식 키트는 **Apple Design Resources 라이선스** 적용 — 앱 UI 참고는 OK, 에셋 팩 재판매는 불가
- Community 파일은 **Duplicate** 후 내 Drafts/팀 프로젝트로 복사해야 편집 가능
- Variant가 여러 개인 컴포넌트 세트는 variant를 하나씩 선택하거나, 별도 프레임에 정리 후 프레임 단위로 export하는 것이 깔끔

---

## 쟁점 / 미결정

- **실제 목적이 무엇인지 아직 확인 안 됨**
  - 디자이너용 PNG/SVG 추출인지
  - 개발자용 CSS 토큰·스펙 이식인지
  - SwiftUI/AppKit 재구현용 참고인지
- 파일 접근 상태 불명확 — View-only 잠금인지, 편집 가능한지
- SF Symbols 최신 버전 미설치 시 아이콘 깨짐 여부 확인 필요
- 대량 export가 필요한지 (REST API / 플러그인 사용 여부)

---

## 에이전트별 핵심

- **Claude**: 목적·파일 상태 먼저 확인 필요 강조, View-only 잠금 가능성 및 라이선스 제한 주의 언급
- **Codex**: 에셋 export 단계별 흐름 정리, 개발 이식 시 Dev Mode에서 색상·spacing·radius 값 확인 후 SwiftUI로 재구현하는 방식 권장
- **Cursor**: 공식 macOS 26 키트 기준으로 Duplicate → Dev Mode → CSS 토큰 매핑 흐름 제시, Materials·Buttons·Lists·Forms·Alerts 우선 적용 추천

---

## 다음에 할 일

1. **목적 명확히 결정**: PNG/SVG 에셋 추출인지, CSS·토큰 개발 이식인지 확인
2. **파일 접근 권한 확인**: View-only인지 편집 가능한지 → View-only면 Duplicate 먼저 실행
3. **에셋 export가 목적이라면**: 컴포넌트 선택 → Export → SVG(벡터) 또는 PNG(래스터) 선택 → Export 실행
4. **개발 이식이 목적이라면**: Figma Dev Mode 켜고 spacing·radius·color·CSS snippet 복사 → `tokens.css` / `macos26.css` 변수명에 맞춰 붙이기
5. **대량 export 필요 시**: Figma REST API 또는 Variables Export 플러그인 검토
6. SF Symbols 최신 버전 설치 여부 확인 (아이콘 깨짐 방지)
