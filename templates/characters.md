---
work: example-work
version: 見本版 第 1 話まで
spoiler: なし
sources:
  - src-001
  - src-002
---

<!--
キャラクターのページの雛形です。works/<slug>/characters.md にコピーして書き換えます。
作品名、地域、人物はすべて架空の見本です。文と表の行に sources.yml の id を付けます。
-->

# 架空の作品のキャラクター

主な人物は、人物 A と人物 B の 2 人です。[src-001]

## 人物の関係

<!-- 図を置く場所: Mermaid で書きます。画像にするなら works/<slug>/figures/ に置きます。 -->

```mermaid
flowchart LR
    A["人物 A"] -->|案内を頼む| B["人物 B"]
```

図 1: 人物 A は人物 B に案内を頼みます。[src-001]

## 人物の一覧

| 人物 | 住んでいる地域 | 出典 |
| --- | --- | --- |
| 人物 A | 地域 A | [src-001] |
| 人物 B | 地域 B | [src-002] |
