---
work: example-work
version: 見本版 第 1 話まで
spoiler: なし
sources:
  - src-001
  - src-002
---

<!--
世界観のページの雛形です。works/<slug>/world.md にコピーして書き換えます。
作品名、地域、数値はすべて架空の見本です。文の直後に sources.yml の id を付けます。
-->

# 架空の作品の世界観

物語の舞台は、川で隔てられた地域 A と地域 B です。[src-001]

## 地域のつながり

<!-- 図を置く場所: Mermaid で書きます。画像にするなら works/<slug>/figures/ に置きます。 -->

```mermaid
flowchart LR
    A["地域 A"] <-->|橋| B["地域 B"]
```

図 1: 地域 A と地域 B を結ぶ橋 [src-001]

## 地域の人口

<!-- グラフを置く場所: 数値にも出典の id を付けます。 -->

```mermaid
xychart-beta
    title "地域ごとの人口 (架空の値)"
    x-axis ["地域 A", "地域 B"]
    y-axis "人口" 0 --> 1000
    bar [800, 300]
```

図 2: 地域 A の人口は 800 人、地域 B の人口は 300 人です。[src-002]
