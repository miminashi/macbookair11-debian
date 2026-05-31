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
- **電源管理系 (S3 ハング → s2idle へ恒久切替)**: lid open でのスリープ復帰に時々失敗
  (`PM: suspend entry (deep)` 直後にカーネルがハング、強制電源オフが必要) する問題を
  ログ解析で確認 (週 ~0.7 件)。Phase B として `i915.enable_dc=0` → `applespi` blacklist
  → `pcie_aspm=off` を順に適用したがいずれも無効で再発が続いた。
  - cold power-off で kernel ring buffer が消え、本機には pstore/ERST も無いため、
    journal では suspend hang と resume hang を区別できず、**1 パラメータ盲目適用 →
    数週間観測のループはフィードバックがゼロ**であることが判明。そこで hang が紐づく
    ACPI S3 deep の firmware 遷移そのものを使わない **s2idle へ恒久切替**
    (`mem_sleep_default=s2idle`、失敗済みの `pcie_aspm=off`/`i915.enable_dc=0` は
    s2idle の消費電力を悪化させるため除去)。
  - s2idle は浅いスリープゆえネットワーク/USB で ~84s ごとに spurious wake するため、
    `udev` で XHC1/RP01-06 の wakeup を無効化し lid-only wake に固定。この状態で
    s2idle スリープ電力は **0.70 W** (12h で 22%、約 55.7h 持続) と実測。
    resume 信頼性の長期観測フェーズへ。

## レポート一覧

`report/` 配下に時系列で蓄積。新しいものから記載する。

| 日時 (JST) | タイトル | 概要 |
|---|---|---|
| 2026-05-31 13:21 | [S3 hang 対策: スリープモードを s2idle へ恒久切替 + spurious wakeup 抑止](report/2026-05-31_132125_s3_hang_switch_to_s2idle.md) | `pcie_aspm=off` 適用から ~7 日で再発 (5/30 18:44、`PM: suspend entry (deep)` で停止)。cold off で ring buffer 消失 + pstore/ERST 不在のため診断ループはフィードバック皆無と判明し、ACPI S3 deep を使わない **s2idle へ恒久切替** (`mem_sleep_default=s2idle`、失敗済み `pcie_aspm=off`/`i915.enable_dc=0` は除去)。s2idle の spurious wake (~84s) を `udev` で XHC1/RP01-06 wakeup 無効化し lid-only に固定。スリープ電力 0.70W (12h で 22%) を実測。resume 信頼性の長期観測へ |
| 2026-05-23 14:45 | [S3 hang 再発 (1 日 2 回) と `pcie_aspm=off` 追加 + `pm_print_times` 永続化](report/2026-05-23_144518_s3_hang_pcie_aspm_off.md) | `applespi` blacklist 適用直後の 35h で hang 2 件 (両方とも `PM: suspend entry (deep)` 直後で停止、`no_console_suspend` で追加情報得られず)。前回プラン Phase B 候補 3 (`pcie_aspm=off`) を適用し、診断強化として `pm_print_times=1` を tmpfiles.d で永続化。次回 hang 時には device-level suspend timing から原因 device を直接特定可能に |
| 2026-05-22 02:20 | [lid open 復帰失敗 (S3 hang) 再発と Phase B 候補 2 (applespi blacklist) 適用](report/2026-05-22_022030_s3_hang_recurrence_applespi_blacklist.md) | `i915.enable_dc=0` 導入から 12 日後の 5/19 に S3 hang 再発を確認 (停止位置は前回より早く device suspend phase)。前回プラン通り `applespi` ブラックリスト + `no_console_suspend` 追加 + 検出スクリプト v2 (末尾ログ判定方式) へ更新。v2 で過去 1 件の見落とし hang も追加発見、頻度は 4/1 〜 5/22 で 6 件 ≒ 週 0.8 件に更新 |
| 2026-05-17 10:53 | [Debian アップデート後デグレチェック (6.12.86→6.12.88 2 段昇格)](report/2026-05-17_105358_post_update_regression_check.md) | 5/17 の 2 段カーネル昇格を含むアップデート後、NM `+broadcomfix1` hold / DKMS 全カーネル installed / `i915.enable_dc=0` / SSD SMART いずれもデグレなしを確認。5/5 で入れた DKMS 自動追従恒久対策 (`linux-headers-amd64` メタ) の初実戦テスト合格 |
| 2026-05-10 05:50 | [lid open 復帰失敗 (S3 hang) 切り分けと暫定対策](report/2026-05-10_055032_lid_open_resume_hang.md) | journal 集計で 16 boot 中 4 件の S3 ハング (`PM: suspend entry (deep)` 直後で固まる) を確認。蓋開閉対照実験 (S3 30 cycle / s2idle 10 cycle / S3+`i915.enable_dc=0` 30 cycle) では fix の経験的 validation は得られず (A-1 でも 0 件)、理論ベースの暫定設定として `i915.enable_dc=0` を残し 4-6 週間の継続観測へ |
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
