# macOS 26 Figma → Agent Lab

## 소스

- 작업 파일: `qItC49QfAY1jfSIcDAsNK1`
- 라이브러리: **macOS 26** (71 components)
- 내보내기: Figma **CSS** (Dev Mode 없이 레이어 Copy CSS)

## 파일

| 파일 | 용도 |
|------|------|
| `macos26-library.json` | 컴포넌트 키 ↔ React/CSS 클래스 매핑 |
| `exports/macos26-figma-export.css` | Figma에서 복사한 **원본 CSS** (참조용, 앱에서 import 안 함) |

## 앱에 반영되는 CSS

`web/src/styles/macos26.css` — Figma 값을 **flex 레이아웃**으로 변환해 적용.

우선순위: Alerts → Buttons → Segmented → Menus → Forms (Checkbox, Text Field)

## SVG / PNG

- **SVG**: 아이콘만 `web/public/icons/`
- **PNG**: 앱 아이콘만 (`assets/icon-master.png`)

## 새 컴포넌트 추가

1. Figma에서 레이어 선택 → CSS 복사
2. `exports/macos26-figma-export.css`에 `/* ComponentName */` 블록 추가
3. 채팅 또는 PR에서 `macos26.css` 매핑 요청
