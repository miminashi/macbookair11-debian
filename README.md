# MacBook Air 11" (2015) Debian パッチプロジェクト

MacBook Air 11-inch (Early 2015) で Debian 13 (trixie) を安定動作させるための、
ハードウェア互換性パッチ・ワークアラウンドの記録プロジェクト。

## 対象環境

- ハードウェア: MacBook Air 11-inch, Early 2015 (Broadwell-U)
  - SSD: APPLE SSD SM0128G (128GB, SATA)
  - Wi-Fi: Broadcom BCM4360 802.11ac (PCI 03:00.0)
- OS: Debian 13 (trixie)
- 主な利用ドライバ: broadcom-sta-dkms (`wl`)

## 目的

MacBook Air 11" で Debian 13 を安定運用するために必要な
ハードウェア互換性パッチ・ワークアラウンドを実装し、
その手順と検証結果をレポートとして蓄積する。

## 適用済みパッチ・ワークアラウンドの概要

- **ストレージ系**: 出荷時 SSD のハードウェア故障 (不良セクタ・SMART 無応答) を診断し、
  同型品への交換と交換後の健全性検査を実施。
- **Wi-Fi 系**: BCM4360 + `wl` ドライバが WPA-PSK-SHA256 非対応のため、
  AP 側 (OpenWrt) の WPA2+WPA3 トランジション設定下で接続不可となる問題に対処。
  暫定的に wpa_supplicant + systemd-networkd へ置き換えたのち、
  最終的に NetworkManager 1.52.1 のソースへ PMF=disable バグ修正パッチを適用し、
  GNOME GUI からの操作を復旧。
- **Wi-Fi 系 (DKMS 追従)**: その後 Debian カーネル更新 (`6.12.85+deb13-amd64`) で
  `broadcom-sta-dkms` が新カーネル向けに再ビルドされず `wl.ko` が消失し Wi-Fi が再喪失。
  根本原因は `linux-headers-amd64` メタパッケージ未投入で、
  メタを投入して DKMS が今後のカーネル更新に自動追従するよう恒久対策を実施。

## レポート一覧

`report/` 配下に時系列で蓄積。新しいものから記載する。

| 日時 (JST) | タイトル | 概要 |
|---|---|---|
| 2026-05-05 00:09 | [カーネル更新で消えた Wi-Fi の修復 (broadcom-sta DKMS 再ビルド)](report/2026-05-05_000905_kernel_dkms_recovery.md) | Debian アップデートで `6.12.85+deb13-amd64` が入り `wl.ko` が消失。`linux-headers-amd64` メタを投入し DKMS 再ビルドで復旧、今後のカーネル追従を恒久化 |
| 2026-04-01 18:20 | [NetworkManager WPA-PSK-SHA256 パッチ適用](report/2026-04-01_182006_networkmanager_patch.md) | NM 1.52.1 のソースに PMF=disable バグ修正パッチを適用し、GNOME GUI からの Wi-Fi 操作を復旧 |
| 2026-04-01 08:01 | [Wi-Fi 接続問題 調査・修正](report/2026-04-01_080116_wifi_fix.md) | BCM4360 + `wl` ドライバが WPA-PSK-SHA256 非対応で接続不可。wpa_supplicant + systemd-networkd へ置き換えるワークアラウンド |
| 2026-03-30 18:54 | [SSD 健全性レポート (交換後)](report/2026-03-30_185423_sda_health_check.md) | 交換後 SSD (S2PBNYAGB28065) の SMART・dd・I/O カウンタ検査 → PASSED |
| 2026-03-30 14:31 | [SSD ディスク調査レポート](report/2026-03-30_143128_sda_investigation.md) | 旧 SSD (S29BNYDG874781) の不良セクタ・I/O タイムアウト・SMART 無応答を診断、ハードウェア故障と判定 |

その他の関連ファイル:

- `ssd_diagnosis_192.168.1.238.txt` — 初期 SSD 故障調査の生ログ (Samsung S4LN058A01[SSUBX] コントローラ故障)

## ディレクトリ構成

```
.
├── CLAUDE.md                      # レポート作成ルール (Claude Code 用)
├── README.md                      # このファイル
├── report/                        # 検証・修正レポート (Markdown)
│   ├── YYYY-MM-DD_HHMMSS_*.md
│   └── attachment/                # 各レポートに紐づくプランファイル等
│       └── <レポートファイル名>/
├── .ssh/                          # GitHub deploy key 運用 (鍵本体は .gitignore で除外)
│   ├── README.md
│   ├── git.sh                     # GIT_SSH_COMMAND 経由の git ラッパー
│   └── known_hosts
└── ssd_diagnosis_192.168.1.238.txt
```

## レポート作成ルール

レポートのファイル名規約・添付ファイル運用などは
[CLAUDE.md](CLAUDE.md) を参照。
