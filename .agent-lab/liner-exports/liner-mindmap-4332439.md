# agent-lab HSIL 재설계 연구 방향

- projectId: `665131`
- mapId: `4332439`
- sourceTitle: HSIL 안전 게이트 한계 극복을 위한 재설계 연구 방향
- nodes: 23
- edges: 22

## agent-lab HSIL 재설계 연구 방향

HSIL 안전 게이트의 10가지 근본적 한계(분류기 불가능성, VC 차원 발산, 리워드 해킹 구조성, 권한 커버리지 갭, 확률적 진동, 지수적 정렬 붕괴, 메모리 드리프트, 레드 퀸 효과, 다중 실패 클래스, 6차원 병목)를 극복하기 위한 신규 연구 방향을 이론적 탈출 경로·구조적 재설계·실무적 완화 세 축으로 조직화한다.

## 1 검증 기반 REGRESS: 분류에서 형식 보증으로의 전환

Scrivens(2026)의 검증 탈출 정리는 분류기 기반 게이트가 이중 조건을 결코 만족할 수 없음을 증명하며, Lipschitz ball verifier가 O(1) 위양성률과 O(1) TPR로 이를 달성함을 보인다

Zenodo (CERN European Organization for Nuclear Research)

. REGRESS를 벤치마크 패스/페일 분류에서 매개변수 공간 검증으로 전환하는 것이 가장 근본적인 재설계 방향이다. Qwen2.5-7B 스케일에서 조합 ball verifier가 LoRA 단계의 79%를 수용하면서 위반을 0으로 보고한 실증

Zenodo (CERN European Organization for Nuclear Research)

은 이 경로의 실현 가능성을 뒷받침한다.

## 2 지속 가능 자가개선: Two-Gate 내장 PROPOSE와 조합 capacity 프록시

Wang 등(2025)의 Two-Gate 정책(검증 마진 τ + capacity 캡 K[m])은 다축 자가수정 하에서도 VC 차원 경계를 유지하며 표준 VC 율 오라클 부등식을 산출한다

arxiv.org

arXiv (Cornell University)

. 핵심 공개 문제는 다축 수정(프롬프트·도구·오케스트레이션 동시 변경) 시 축 간 상호작용에 의한 창발적 capacity 폭발을 상한하는 조합 capacity 프록시 개발이다

arXiv (Cornell University)

. 고魏를 있는 capacity proxy 개발의 간격이 Two-Gate의 보수성을 결정하므로, 하네스 특화 capacity metric(도구 수·프롬프트 복잡도·오케스트레이션 깊이의 조합 함수) 설계가 즉시 연구 가능하다.

## 3 회복 중심 거버넌스: 래칫 문제 해결과 존재 권한 거버넌스

Tallam(2026)의 Layered Mutability 프레임워크는 관측 가능성이 결과성에 반비례하는 5층 가변성 스택을 식별하고, 얕은 되돌리기 후에도 잔여 드리프트가 2/3 생존하는 래칫 문제를 실증했다

arxiv.org

. Chen 등(2026)은 개방 에이전트 시스템에서 회복을 일차 설계 관심사로 격상할 것을 권고한다

ArXiv.org

. MERGE의 Editable Surface Tier에 '행동 권한'과 '존재 권한'의 분리

arxiv.org

, 종단 행동 프로파일링에 의한 드리프트 조기 경보

arxiv.org

, 메모리 층별 되돌리기 오퍼레이터

arxiv.org

를 통합하는 회복 중심 아키텍처가 필요하다.

## 4 동적 평가 적응: 레드 퀸 효과와 Campbell 전이 대응

Wang & Huang(2026)은 도구 수 증가에 따라 평가 커버리지가 0으로 수렴하고, Goodhart 체계에서 Campbell 체계로의 전이 임계값 존재를 예측했다

arXiv (Cornell University)

. Koch(2026)는 자가수정 전 3단계 시뮬레이션 양식(논리·실행·예측)을 실행성 조건으로 제안한다

arXiv (Cornell University)

. 도구 추가 시 새 차원의 평가 커버리지를 동시 확장하는 메커니즘

arXiv (Cornell University)

, 평가 시스템 자체의 훼손 저항성을 측정하는 Campbell 경계 탐지기, 그리고 PROPOSE 수정 전 샌드박스 시뮬레이션(S2) 의무화

arXiv (Cornell University)

가 결합된 동적 평가 적응 계층이 HSIL의 4번째 재설계 축이다.

## Information-Theoretic Limits of Safety Verification for Self-Improving Systems

Arsenios Scrivens

Zenodo (CERN European Organization for Nuclear Research)

2026. 03. 26.

## Empirical Validation of the Classification-Verification Dichotomy for AI Safety Gates

Arsenios Scrivens

Zenodo (CERN European Organization for Nuclear Research)

2026. 03. 26.

## Layered Mutability: Continuity and Governance in Persistent Self-Modifying Agents

Krti Tallam

arxiv.org

2026. 04. 16.

## On The Statistical Limits of Self-Improving Agents

Chen Wang, Keir Dorchen, Peter Jin

arXiv (Cornell University)

2025. 10. 05.

## Layered Mutability: Continuity and Governance in Persistent Self-Modifying Agents

Krti Tallam

arxiv.org

2026. 04. 16.

## Clawed and Dangerous: Can We Trust Open Agentic Systems?

Shiping Chen, Qin Wang, Guangsheng Yu, Xu Wang, Liming Zhu

ArXiv.org

2026. 03. 27.

## Reward Hacking as Equilibrium under Finite Evaluation

Jiacheng Wang, Jinbin Huang

arXiv (Cornell University)

2026. 03. 30.

## What does a system modify when it modifies itself?

Florentin Koch

arXiv (Cornell University)

2026. 03. 29.

## An Empirical Study of Fuzz Harness Degradation

Philipp Görz, Jonathan S. Schilling, Thorsten Holz, Marcel Böhme

ArXiv.org

2025. 05. 09.

인용 1

## 5 권한 게이트 재설계: 도구 치환 공격과 구조적 커버리지 갭 해소

Ji 등(2026)은 Claude Code Auto Mode 스트레스 테스트에서 이중 취약성을 실증했다: (1) Tier 3 분류기 내 FNR 70.3%/FPR 31.9%; (2) 전체 상태 변경 작업의 36.8%가 Tier 2에 위치하여 구조적 100% FNR을 보인다

arxiv.org

. Uchibeke(2026)는 이를 '정렬 문제가 아닌 인가(authorization) 문제'로 규정하고, 도구 호출 경계에서의 결정론적 사전 실행 인가를 제안한다

ArXiv.org

. MiniScope의 최소 권한 프레임워크는 정책 기반 집행과 정보 흐름 제어를 결합한다

ArXiv.org

. 핵심 개선은 (1) Tier 2 경로를 포함한 전경로 커버리지, (2) LLM 분류기 대신 결정론적 정책 언어, (3) 도구 설계 자체를 위협 모델에 포함하는 것이다

arXiv (Cornell University)

ArXiv.org

.

## Measuring the Permission Gate: A Stress-Test Evaluation of Claude Code's Auto Mode

Zimo Ji, Zongjie Li, Wenyuan Jiang, Yudong Gao, Shuai Wang

arxiv.org

2026. 04. 04.

## Before the Tool Call: Deterministic Pre-Action Authorization for Autonomous AI Agents

Uchi Ugobame Uchibeke

ArXiv.org

2026. 03. 21.

## AEGIS: No Tool Call Left Unchecked -- A Pre-Execution Firewall and Audit Layer for AI Agents

Aojie Yuan, Zhiyuan Su, Yue Zhao

arXiv (Cornell University)

2026. 03. 13.

## 6 유한합리성 안전 보증: 지수적 정렬 붕괴의 경계 조건

Tětek 등(2020)은 유한합리성 에이전트의 최적화 불완전성이 자가수정을 통해 정렬의 지수적 악화를 초래함을 증명했다: 할인 인자 γ 하에서 정렬 붕괴가 O(ε/(1-γ))로 성장하며

arXiv (Cornell University)

, 완벽한 최적화를 가정한 Everitt 등의 결과와 근본적으로 다르다. 핵심 통찰은 '유한지식(bounded-knowledge) 에이전트는 자가수정으로 악화되지 않으나, 유한최적화(bounded-optimization) 에이전트는 지수적 악화를 겪는다'는 점이다

arXiv (Cornell University)

. HSIL PROPOSE의 안전 조건으로 (1) o-최적화 오류의 엄격 상한, (2) γ에 대한 민감도 분석, (3) 수정 독립성(modification-independence)의 검증 가능 조건화가 필요하다

arXiv (Cornell University)

.

## Performance of Bounded-Rational Agents With the Ability to Self-Modify

Jakub Tětek, Marek Sklenka, Tomáš Gavenčiak

arXiv (Cornell University)

2020. 11. 12.

인용 1

## 7 자가개선 파이프라인 정보 이론: 데이터 자가포식과 학습 가능 정보 단조성

Yang 등(2026)은 자가개선의 6차원 병목을 체계화했다: 데이터 자가포식, 결함 있는 피드백, 최적화 기반 실패, 비효과적 자가정련, 평가 병목, 감독 병목

ArXiv.org

. 모델 붕괴는 합성 데이터 루프에서 정보 다양성의 점진적 소실로, 작은 상수 비율의 합성 데이터 혼입도 점근적으로 유해함이 증명되었다

ArXiv.org

. Liu 등(2026)은 자가진화가 학습 가능 정보의 단조 증가를 보장할 때만 지속 가능함을 보이며, 3가지 설계 원칙(비대칭 공진화, capacity 성장, 능동적 정보 탐색)을 제안했다

arXiv (Cornell University)

. HSIL 전체 파이프라인에 (1) INTERIM→OUTCOME 간 학습 가능 정보량 측정, (2) 단조 위반 시 PROPOSE 일시 중지, (3) 외부 정보원 능동 탐색 메커니즘이 필요하다.

## Self-Improvement of Large Language Models: A Technical Overview and Future Outlook

Haoyan Yang, Mario Xerri, Solha Park, Huajian Zhang, Yiyang Feng, Sai Akhil Kogilathota, Jiawei Zhou

ArXiv.org

2026. 03. 26.

## Self-Play Only Evolves When Self-Synthetic Pipeline Ensures Learnable Information Gain

Wei Liu, Siya Qi, Yali Du, Yulan He

arXiv (Cornell University)

2026. 02. 10.
