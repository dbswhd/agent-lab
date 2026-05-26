# Apple Design Resources — macOS 26 / iOS 26 Kit 스펙

> Figma 커뮤니티 "Apple Design Resources – macOS Tahoe" 키트에서 추출한 공식 컴포넌트 스펙.
> 본인 `web/src/styles/tokens.css` 및 `macos26.css` 와 대조하는 source of truth.

## Surfaces (창/표면)

| 컴포넌트 | 사이즈 | Border Radius | Shadow |
|---|---|---|---|
| **Window** | 500×300 | **26px** | `0px 0px 0px 1px rgba(0,0,0,0.23), 0px 16px 48px rgba(0,0,0,0.35)` |
| Utility Panel | 300×300 | 15px | `0px 5px 20px rgba(0,0,0,0.3)` |
| Alert | 260×218 | 10px | `drop-shadow(0 0 1px rgba(0,0,0,0.2)) drop-shadow(0 17px 45px rgba(0,0,0,0.5))` |
| Sheet | 300×300 | 10px | — |
| Popover | 200×200 | — | — |
| Tooltip | 97×18 | 1px | bg `rgba(246,246,246,0.72)` blur 10px, `0px 1px 3px rgba(0,0,0,0.2)` |

## Controls — Inline (24px 높이가 표준)

| 컴포넌트 | 사이즈 | Padding | Radius |
|---|---|---|---|
| **Push Button** | 67×24 | 0 16px | 6px |
| Pop-Up Button | 100×24 | 0 0 0 12px | 6px |
| Pulldown Button | 100×24 | 0 0 0 12px | 6px |
| Combo Box | 100×24 | 2px 2px 2px 0 | — |
| Text Field | 120×24 | 0 4px 0 8px | — |
| Search Field | 120×24 | 0 4px 0 8px | — |
| **Segmented Control** | 108×24 | 0 | 6px, bg `rgba(0,0,0,0.02)` |
| Stepper (Inside/Outside) | 120×24 | — | 6px |
| Stepper (No Field) | 20×24 | — | 6px |
| Switch | 54×24 | 2px | 1000px (pill) |
| Arrow / Disclosure Button | 24×24 | — | 1000px |

## Controls — Toolbar (36px 높이 — 더 큼)

| 컴포넌트 | 사이즈 | Padding | Radius |
|---|---|---|---|
| Window/Button | 36×36 | 4px | — |
| Window/Button Group | 72×36 | 4px, gap 4 | — |
| Window/Pop-Up Button | 63×36 | 6.5px 8px 7.5px | — |
| Window/Pull Down Button | 50×36 | 0 8px | — |
| **Window/Search** | 130×36 | 0 10px, gap 6 | **100px (pill)** |
| Window/Segmented Control | 71×36 | 4px | — |

## Sidebar / List

| 컴포넌트 | 사이즈 | Padding | Radius |
|---|---|---|---|
| Folder | 270×24 | 0 10px | **5px** (6 아님!) |
| Item | 270×24 | 0 10px | **5px** |
| Section Header | 270×34 | 15px 12px 5px **18px** | — |
| Group Title | 200×53 | **32px 8px 7px 48px** | — |
| Column Header | 150×28 | 4px 0 5px | bottom border 1px rgba(0,0,0,0.05) |
| Group Box | 200×200 | — | 12px, bg rgba(0,0,0,0.03) opacity 0.5 |

## Menu / Notification

| 컴포넌트 | 사이즈 | Padding | gap |
|---|---|---|---|
| Menu | 250×328 | 5px 12px | — |
| Notification | **344×72** | 12px 9px 12px 13px | 13px |
| Menu Bar | 1008×34 | 5px 10px | 98 |

## Form Controls (16px 높이)

| 컴포넌트 | 사이즈 | gap |
|---|---|---|
| Checkbox | 54×16 | 3px |
| Radio Button | 54×16 | 3px |

## Liquid Glass (iOS 26)

- Large/Medium: 160×160
- Small: 48×48

## Color Well

28×28, radius 100px, 색상환 그라디언트:
```
radial-gradient(50% 50% at 50% 50%, #FFFFFF 4%, rgba(255,255,255,0.66) 41.35%, rgba(255,255,255,0.330806) 73.56%, rgba(255,255,255,0) 96%),
conic-gradient(from 180deg at 50% 50%, #FF0000 0deg, #FB00FF 72deg, #00A1FF 144deg, #44FF00 216deg, #FFF700 288deg, #FF0000 360deg);
```

## Window Controls (Traffic Lights)

- Standard: 62×16, padding 1px, gap 9px
- Utility: 50×16, padding 3px, gap 7px
- 개별 dot: 12×12, radius 50%, inset shadow 0.5px

## 페이지 레이아웃 컨텍스트

- Desktop Template: 1512×982
- Header (메인 영역 헤더): 1400×208, gap 32
