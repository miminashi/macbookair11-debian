# dpmwd2 デプロイ + Phase C-2 (watchdog late/noirq 拡張カーネルでの hang 再演)

## Context

- [002608](report/2026-07-03_002608_dpmwd1_hang_reproduced_no_panic_stage_narrowed.md) で dpmwd1 上の hang (1/24, BT_PAN_VALID) が **~18 分 panic 沈黙** → 停止段 ∈ {suspend_late, suspend_noirq, syscore, s2idle-enter} に絞り込み確定。H4/H2 disfavor。
- 次の手 (前セッションで事前定義済): watchdog を late/noirq 段へ拡張した `6.12.94-dpmwd2` をデプロイし、同一条件で再演する。
- **dpmwd2 の準備状況 (確認済)**:
  - パッチ commit `b90248d63` (dpmwd/6.12.94 ブランチ HEAD): `device_suspend_late/noirq` + `device_resume_early/noirq` の `dpm_run_callback` を `dpm_watchdog_set/clear` で挟む — 内容検収済
  - `.config`: `LOCALVERSION="-dpmwd2"` + `DPM_WATCHDOG=y/60` + `PM_TRACE=y` + `PM_TRACE_RTC=y` 設定済
  - **ただし deb は未生成** (src/ に dpmwd1 の deb しかない。前セッションの「ビルド進行中」は完了しなかった) → ビルドからやり直す
- 実機現状 (確認済): dpmwd1 稼働 (saved default)、pstore 空、hooks 4 本残置 (58-snapshot-only 含む)、NM 平常化済、battery 86%、/boot・/ とも空き十分
- 前セッション scratchpad (`/tmp/claude-1001/.../64e447cc-.../scratchpad/phase-bc-materials/`) に session-commands.md / transient-units-commands.sh / pstore-guard / 58-snapshot-only が残存 — 今セッションの scratchpad にコピーして使う

## Phase 0: dpmwd2 ビルド完了 (開発機、~30-40 分)

```bash
cd src/linux-6.12.y
# 検収ゲート: HEAD=b90248d63, .config に dpmwd2/PM_TRACE_RTC, kernelrelease=6.12.94-dpmwd2+
make olddefconfig                      # auto.conf 非同期の癖に注意 (必要なら rm include/config/auto.conf)
make -j12 LOCALVERSION= bindeb-pkg     # "+" 抑止 (182811 の教訓)
```

- background 実行し、完了後に検収: `linux-image-6.12.94-dpmwd2_*.deb` + headers 生成、deb 内 config で `CONFIG_DPM_WATCHDOG=y/60` + `CONFIG_PM_TRACE_RTC=y`
- パッケージ名が dpmwd1 と別なので実機で共存可能 (dpmwd1 も残置 = 多段ロールバック)

## Phase 1: 実機デプロイ (182811 と同一手順、crash テストは省略)

1. deb 2 個を scp → `sudo dpkg -i` headers → image (postinst で dkms が wl を dpmwd2 向け自動ビルド + MOK 署名、initramfs、update-grub)
2. 検収: `dkms status` で broadcom-sta built、`/boot/vmlinuz-6.12.94-dpmwd2` 存在
3. **フェイルセーフ付き初回起動**: saved default は dpmwd1 のまま、`grub-reboot <dpmwd2 エントリ>` ワンショット + **`sync`** (grubenv 教訓) → `sudo reboot` (ssh 越し。起動不能時は dpmwd1 に自動フォールバック)
4. ゲート (a): `uname -r` = 6.12.94-dpmwd2 / config (DPM_WATCHDOG=y/60, PM_TRACE_RTC=y) / cmdline に panic=15 / wl loaded + WiFi 動作 / pstore 空 / pstore-guard 正常
5. ゲート (a2): s2idle smoke 1 cycle (`rtcwake -m no -s 15` + `systemd-suspend --wait`)
6. 通過後: `grub-set-default <dpmwd2 エントリ>` + **`sync`** = 恒久化
7. crash テスト (ゲート b) は**省略** — panic → pstore → 自動復帰の経路は 182811 で 2 回検証済み (002608 引継ぎで省略可と事前定義)
8. `/sys/power/pm_trace` は **0 のまま (inert)** — dpmwd2 でも沈黙した場合の次段としてとっておく (RTC 破壊の副作用を今回は持ち込まない)

## Phase 2: Phase C-2 hang 再演セッション (002608 と同一設計、ユーザ手動 cycle)

セットアップ (Claude, ssh。コマンドは session-commands.md 逐語):

- `sysctl -w kernel.hung_task_panic=1` (reboot で消えるため毎回)
- NM: BT-PAN(iMiminashiPadPro)/GSNet autoconnect=yes、OpenWrt autoconnect=no + route-metric 800
- 58-snapshot-only は実機残置済 (再デプロイ不要、存在確認のみ)
- transient units 起動 (vpn-watcher / cycle-watcher、transient-units-commands.sh 逐語)
- smoke 1 cycle → snapshot で `wl_loaded=YES ping_running=NO` 確認
- SESSION_START epoch 記録

ユーザ依頼事項:

1. iPad テザリング ON → Claude が BT-PAN IP (172.20.10.x) + GSNet active を確認
2. Claude が detached systemd-run で `nmcli con down OpenWrt; nmcli radio wifi off` (**wl は rmmod しない** — tight reading (b'') 維持) → ssh 切断
3. コンソールゲート: `nmcli radio wifi` = disabled + `lsmod | grep wl` 残存を目視
4. 手動 lid close/open cycle 駆動 (目安 30 cycle、cycle 1 で canary 3 項目確認)

hang 時の手順 (ユーザ → Claude):

1. 即 lid open → **5 分以上待つ** (late/noirq watchdog 60s + panic=15 なら ~2 分弱で自動再起動するはず)
2. 自動再起動しなければ強制電源断 → 起動後 `nmcli radio wifi on` + OpenWrt 接続で ssh 復旧
3. Claude 回収 (順序厳守): pstore 回収 (`/sys/fs/pstore` + `/var/lib/systemd/pstore` を ~/pstore-recovered/ へ cp -a) → レコード削除 → pstore-guard stop → sysctl 再設定 → transient units 再作成 → radio off で条件復帰 (継続時)

### 解釈マトリクス (事前定義)

| 観測 | 解釈 |
|---|---|
| panic + `<driver> <dev>: unrecoverable failure` (suspend_late/noirq 側 stack) | **停止段+stall device 確定 = 機序決着へ前進** |
| resume_early/noirq 側 stack | β (復帰側) 判別決着 |
| hung_task panic | pre-freeze 段 (khungtaskd は freezable な点に留意) |
| なお panic 沈黙 | 停止段 ∈ {syscore, s2idle-enter, watchdog timer も止まる領域} → 次段 = `/sys/power/pm_trace` 有効化再演 (RTC hash 照合) or `pm_test` 段階分離 |

## Phase 3: 撤収 + レポート

- セッション終了時: hung_task_panic=0、NM 平常化 (autoconnect 戻し、OpenWrt metric -1)、radio on、transient units stop (58-snapshot-only / pstore-guard は残置)
- レポート: `report/` ルール準拠 (TZ=Asia/Tokyo date でタイムスタンプ取得)、本プランを attachment に添付、pstore dump があれば attachment に退避
- メモリ `s2idle-btvpn-hang-mechanism-ladder` に C-2 結果を反映

## 役割分担

| 作業 | 担当 |
|---|---|
| Phase 0 ビルド + 検収 | Claude (background Bash) |
| Phase 1 デプロイ・GRUB・ゲート | Claude (reboot も ssh 越し、フェイルセーフ付き) |
| Phase 2 セットアップ・回収・解釈 | Claude |
| テザリング ON・コンソールゲート・lid cycle・強制電源断 | ユーザ |

## 検証方法

- Phase 0: deb 内 config の grep 検収
- Phase 1: ゲート (a)(a2) blocking
- Phase 2: hang 再現時に pstore から stall device 入り panic が回収できること (沈黙も判別情報として記録)
