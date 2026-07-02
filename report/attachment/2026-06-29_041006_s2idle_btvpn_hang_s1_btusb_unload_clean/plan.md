# s2idle + BT-PAN + VPN + 手動 lid close ハングの段階的切り分け

## Context

MacBook Air 11" 2015 / Debian 13 trixie / カーネル 6.12.94+deb13-amd64 で、**s2idle + BT-PAN テザリング + VPN-over-BT-PAN + 手動 lid close** の組合せに限ってハング (iPhone 3/10, iPad 1/22)。他の組合せ (BT-PAN 単独 25/25, VPN-over-WiFi 11/11, 無線無し 9/9, `systemctl suspend` 0/15) は全てクリーン。S3 deep の本採用は 2026-06-27 に no-go で s2idle にロールバック済だが、s2idle でも本条件で再発する。

2026-06-28(c) でカーネルソース (Debian patched v6.12.94) を精読し、ハングが freeze 後の `dpm_suspend` 段で発生し DPM_WATCHDOG 未有効 + `no_console_suspend` 有効でも `pm_debug_messages=0` のため device 単位で停止点が無音、という構造を確認した。仮説 H1/H2/H4 を立てた状態で、まだ「どの仮説が正しいか」を **判別する実験** を一つも回していない。本プランはその段階的判別を行う。

なお Phase 1 調査で以下が判明し、当初想定からアップデートされた:
- **`no_console_suspend` は既に cmdline に入っている** (074509 の「console suspend 済で無音永久化」より緩和)
- **journald に `unregister_netdevice: waiting` 出現なし** (過去 30 日) → **H1 (xfrm→bnep ref leak) の確度大幅低下**、H2/H4 が有力
- suspend_stats: success=60, fail=0 (ハングは watchdog 無効のため sysfs 未記録)
- **memory note s2idle-observation-phase.md の「lid wake は s2idle で構造的に不可能」(2026-06-18 結論) は現状と整合しない**: 当時は S3 deep 評価期で LID0 を `/proc/acpi/wakeup` で凍結していた文脈の話。現状は `LID0 *enabled` で 141226 の driver 実験 2a/2b が 60 cycle 全 wake 成功し、表 (β) で「lid open → LID0 GPE → resume」が動作前提として記述されている。S0.5 の lid open 比較対照はこの最新観測に従う。

### 設計原則
- **統計の非対称性**: 1 hang = 介入失敗の決定的証拠。clean は確率的不在証明にすぎないため、**各 S は 30 cycle (S5 は 60 cycle) を pre-register**。最近の baseline で 5% 仮定なら N=30 clean が ~79% 信頼。
- **条件成立の retrospective 検証**: 各サイクルが「BT-PAN+VPN active+lid close 経由」を本当に満たしたか、journald の `deleting IKE_SA … 172.20.10.X` と `s3-soak.log` の SLEEP/WAKE で事後確認。**未成立サイクルは分母から除外**。
- **可逆性**: 全 S は 1 ファイル追加 or grub-reboot 一発で完全ロールバック (`s3-deep-apply.service` と同じ流儀)。
- **リビルドは dev 機で**: `make bindeb-pkg` で deb 化 → scp → 実機で `dpkg -i`。MacBook Air 上でビルドしない。
- **DKMS と MOK 署名**: 新カーネル導入時は broadcom-sta-dkms autoinstall + wl.ko の MOK 署名を事前に dev 機で通過確認。

## 実験ラダー

### S0: パッシブ観測装置 + pstore 検証 (前提条件 gating)

**目的**: hang 時に stock kernel でも dmesg tail が pstore に残るか確認 (= S4 が必要かどうかの分岐)。同時に suspend 突入直前の in-flight 状態を pre フックで durable に取得 (post は hang 時には走らない = pre スナップショットが唯一の証拠)。

**実装** (実機 ssh):
1. pstore 動作確認:
   - `ls /sys/fs/pstore /sys/module/ramoops`、`dmesg | grep -iE "pstore|ramoops|efi.*kmsg"`
   - 何も出ない場合は GRUB cmdline に `pstore.backend=efi printk.devkmsg=on` を追加検討 (efi-pstore は EFI vars に kmsg を残す)
2. `/etc/systemd/system-sleep/70-h4-probe` を新規作成:
   - pre: `ip xfrm state`, `ip xfrm policy`, `ip -o link show`, `cat /proc/net/dev`, `lsmod | grep -E "btusb|btintel|bnep|bluetooth"`, `cat /sys/bus/usb/devices/*/power/runtime_status`, `dmesg -T | tail -300`, `journalctl -n 200 -k` を `/var/log/h4-probe/$(date +%s).pre` に出力 → 末尾で `sync`
   - post: 同内容を `.post` に出力
3. `pm_debug_messages` 有効化 (pre フックで毎回 `echo 1 > /sys/power/pm_debug_messages` 設定、再起動で消える)

**観測**: 各 cycle の pre snapshot に teardown 残留 (`nm-xfrm-N` netdev、bypass policy、`bnep0` ref count、btusb URB anchor) があるか / hang 時 pstore に dmesg tail が残るか。

**判定**:
- pstore 動作 → S4 で DPM_WATCHDOG の backtrace 回収が可能
- 動作不可 → S4 で GRUB に ramoops 領域追加 or 別手段
- pre snapshot 個別の所見で **S1/S2/S3 の優先順位**を示唆

**所要**: 1 セッション (フック投入 + 20〜30 cycle 駆動 ~30〜60 分) / **ロールバック**: フックファイル `rm` のみ

---

### S0.5: α/β 判別子 (機序ラダー前の必須 gate)

**目的**: 「停止が **入眠** (α: logind handler/dpm_suspend) か **復帰** (β: LID0 GPE wake) のどちらか」を分離する。141226 で未解決だった分岐。この分離なしに S1 以降の機序ラダーへ進むと、btusb-drain ラダー全体が見当違いになる可能性。

**手順** (ユーザ手動):
1. BT-PAN + VPN active、AC 接続。
2. lid close 前に SSH 越しに `sudo rtcwake -m no -s 60` (alarm のみセット、suspend は logind に任せる)。原典 141226 の driver は同コマンド直後に `systemctl suspend` を呼ぶので 30s で足りたが、**手動 lid close は 5〜10s の遅延を含むため 60s に拡張**。
3. 手動 lid close → 約 60 秒待つ → RTC alarm で起こす → 起きた場合は **lid open しない** (lid open でも wake してしまうとどちらが効いたか不明になる)。
4. 別セッションで「lid close → 60 秒待つ → lid open で起こす」を比較対照 (lid open による wake は 141226 表 (β) で動作前提)。

**判定**:
- **RTC wake 中も hang** → α (入眠側) 確定 → **S1 へ進む**
- **RTC wake clean × lid open で hang** → β (LID0/i915 resume) 確定 → **本ラダー打切**、LID0 wake 凍結 + i915 resume 経路調査へ転回
- **どちらも clean (= 発生確率の問題)** → 3 因子相互作用 → ラダーは続けるが S1 以降の cycle 数を増やす

**所要**: 半日 / 15〜20 cycle / **ロールバック**: なし (rtcwake は揮発)

---

### S1: btusb pre-unload (H4 経路の有無検証)

**目的**: `modprobe -r bnep btusb btintel` で device-suspend 経路から btusb を物理的に除き、H4 (URB drain 永久ブロック) が経路上にあるか判定。

**実装**: `/etc/systemd/system-sleep/55-btusb-down`:
```sh
#!/bin/sh
case "$1" in
  pre)  modprobe -r bnep btusb btintel 2>&1 | logger -t 55-btusb-down ;;
  post) modprobe btintel; modprobe btusb; modprobe bnep 2>&1 | logger -t 55-btusb-down ;;
esac
```
bluetoothd は active のまま (USB ドライバだけ抜く)。

**判定**: 0 hang/30 cycle → btusb suspend が critical path にある → **S5 へ** / 1+ hang → **S2 へ**

**所要**: 1〜2 日 (30 cycle) / **ロールバック**: フックファイル `rm`

---

### S2: xfrm flush pre-suspend (xfrm 残留関与の検証)

**目的**: charon-nm が論理 teardown 完了済でも残る可能性のある xfrm state/policy (特に `nm-xfrm-N` netdev 紐付 software bundle) を pre で flush。

**実装**: `/etc/systemd/system-sleep/56-xfrm-flush` pre で:
```sh
ip xfrm state flush
ip xfrm policy flush
```

**判定**: 0 hang/30 cycle → xfrm 残留関与 → 上流 fix backport (074509 留意 b) / 1+ hang → **S3 へ**

**所要**: 1〜2 日 (30 cycle) / **ロールバック**: フックファイル `rm`

---

### S3: bnep 明示 teardown (H2 検証)

**目的**: non-freezable `bnep_session` kthread が freeze 窓に in-flight になる仮説 (H2) を、pre で BNEP セッションを明示的に閉じて検証。

**実装**: `/etc/systemd/system-sleep/57-bnep-down` pre で:
```sh
nmcli -t -f UUID,TYPE con show --active | awk -F: '$2=="bluetooth"{print $1}' | \
  xargs -r -n1 nmcli con down
bluetoothctl disconnect
sleep 1
```

**判定**: 0 hang/30 cycle → bnep 経路寄与 → 上流に「bnep_session を freezable 化」パッチ提案 / 1+ hang → **S4 へ**

**所要**: 1〜2 日 (30 cycle) / **ロールバック**: フックファイル `rm`

---

### S4: DPM_WATCHDOG 有効カーネル (どの device で stuck か特定)

**目的**: S1〜S3 すべて hang or S0 で pstore 確証取れず → kernel watchdog に犯人デバイス名を自白させる。

**dev 機での実装**:
1. `cd /home/miminashi/projects/macbookair11-debian/src && apt-get source linux=6.12.94-1` (deb-src 必要、無理なら snapshot.debian.org)
2. 実機 `/boot/config-6.12.94+deb13-amd64` を scp で持ってきて `.config` に
3. `./scripts/config --enable CONFIG_DPM_WATCHDOG --set-val CONFIG_DPM_WATCHDOG_TIMEOUT 60` `--enable CONFIG_PSTORE_RAM` `--set-str CONFIG_LOCALVERSION "+dpmwd1"`
4. `make olddefconfig && make -j$(nproc) bindeb-pkg LOCALVERSION=+dpmwd1`
5. **dev 機で broadcom-sta-dkms が新 ABI で build 通るか先に確認** (同 amd64): `dpkg -i linux-{image,headers}-6.12.94+dpmwd1*.deb && dkms autoinstall -k 6.12.94+dpmwd1-amd64 && dkms status broadcom-sta`
6. 通れば deb を実機に scp → `dpkg -i` → 実機 `dkms autoinstall` 走行確認 → MOK 署名 (dkms が自動)
7. `grub-reboot "Advanced options for Debian GNU/Linux>Debian GNU/Linux, with Linux 6.12.94+dpmwd1-amd64"` で 1 回だけ新カーネル起動 (GRUB default は不変)
8. S1〜S3 のフック群投入状態で 20〜30 cycle 駆動

**判定**: pstore の watchdog backtrace 内の関数名で犯人デバイス特定 (`btusb_suspend` → S5 / `bnep_*` → bnep freezable 化 / `xfrm_*` → fix backport / その他 → S0.5 再考)

**所要**: build 2〜4h + dev 機検証半日 + 実機 hang campaign 2〜3 日 / **ロールバック**: `grub-reboot "Debian GNU/Linux"` (次回起動で stock に戻る) + 撤去時 `apt-get purge`

---

### S5: btusb_suspend URB drain timeout 試作 (修正試作)

**目的**: S1 clean or S4 で btusb 指摘確証後、`btusb_stop_traffic()` の `usb_kill_anchored_urbs` を `usb_wait_anchor_empty_timeout(anchor, 2000)` + 残留 URB は再 kill に置換した修正版で hang 消失を実証 (upstream patch 提案素材作り)。

**dev 機での実装**:
1. ソース取得 (S4 と同じ流儀): `cd /home/miminashi/projects/macbookair11-debian/src && apt-get source linux=6.12.94-1` → `src/linux-6.12.94/` に展開
2. `src/linux-6.12.94/drivers/bluetooth/btusb.c` の `btusb_stop_traffic` の各 anchor について timeout 付き wait → 残留時 fallback kill のロジックを追加
3. **モジュール単独ビルド** (フルカーネル不要)。build tree の準備は次のいずれか:
   - (a) dev 機が同じ Debian/amd64 なら: `apt install linux-headers-6.12.94+deb13-amd64` で実機と同一の headers パッケージを入れる (modules_prepare 済の build tree が `/lib/modules/6.12.94+deb13-amd64/build/` に展開される)
   - (b) または実機から build tree を scp: `scp -r miminashi@macbookair2015.lan:/lib/modules/6.12.94+deb13-amd64/build/ ./build-tree/` (リンク先含めて再帰コピー)
   - その上で: `make -C <build-tree> M=$PWD/src/linux-6.12.94/drivers/bluetooth modules`
4. `modinfo --field=vermagic btusb.ko` で実機 stock kernel と vermagic 完全一致確認 (例: `6.12.94+deb13-amd64 SMP preempt mod_unload modversions`)
5. MOK 鍵で署名 (broadcom-sta-dkms と同じ `/var/lib/dkms/mok.{key,pub}`): `<build-tree>/scripts/sign-file sha256 mok.key mok.pub btusb.ko`
6. 実機 `/lib/modules/6.12.94+deb13-amd64/updates/btusb.ko` に配置 → `depmod -a` → `modprobe -r btusb && modprobe btusb` → `modinfo btusb | grep filename` で updates/ 配下が読まれていることを確認

**判定**: 0 hang/60 cycle + 警告ログ複数 → H4 因果確定 + 修正有効 → upstream bluetooth ML へ patch 提案 + DKMS 化 / 1+ hang → URB drain 単独修正不十分 → S4 結果に戻る

**所要**: ビルド 30 分 + 検証 2〜3 日 / **ロールバック**: `rm /lib/modules/$(uname -r)/updates/btusb.ko && depmod -a && modprobe -r btusb && modprobe btusb`

---

## 判定樹

```
S0 (passive 観測 + pstore 確認)
  ├ pstore 不可          → S0 改修 or S4 段階で対応策
  ├ xfrm 残留所見        → S2 を S1 より優先
  ├ bnep ref 所見        → S3 を優先
  └ ニュートラル          → S0.5
S0.5 (rtcwake で α/β 分離)
  ├ RTC wake 中も hang   → α 確定 → S1
  ├ RTC wake clean × lid open hang → β 確定 → 本ラダー打切 / LID0+i915 へ転回
  └ どちらも clean        → 3 因子相互作用 → cycle 数増やして S1
S1 → 0 hang ? S5 : S2
S2 → 0 hang ? xfrm fix backport : S3
S3 → 0 hang ? bnep freezable 化提案 : S4
S4 backtrace → btusb→S5 / bnep→修正試作 / xfrm→backport / その他→S0.5 再考
S5 → 0 hang ? upstream 提案 + DKMS 化 : S4 結果へ戻る
```

## 全体スケジュール

| Step | 所要 | 手動 lid close | 主リスク |
|---|---|---|---|
| S0   | 1〜2 日 | 30 cycle | pstore 未動作なら S4 で別手段 |
| S0.5 | 半日   | 15〜20 cycle | logind が SW_LID synthetic を無視する場合あり (今回は手動なので影響軽微) |
| S1   | 1〜2 日 | 30 cycle | modprobe -r が busy で失敗 |
| S2   | 1〜2 日 | 30 cycle | active VPN への副作用 |
| S3   | 1〜2 日 | 30 cycle | nmcli down が空回り |
| S4   | 3〜4 日 | 再起動+30 cycle | broadcom-sta DKMS build 失敗 / MOK 署名 / pstore 揮発 |
| S5   | 2〜3 日 | 60 cycle | modversions 不一致 / Secure Boot 拒否 |

**最短** (S0 → S0.5 α → S1 clean → S5 clean): 5〜6 日 + lid close ~140 回。
**最長** (S4 まで): 2 週間級。

## Critical Files (調査・編集対象)

- **読む (src)** — apt-get source の展開先 `src/linux-6.12.94/` 配下:
  - `src/linux-6.12.94/drivers/bluetooth/btusb.c` — `btusb_suspend` / `btusb_stop_traffic` (`:4293-4294` 近辺、S5 で改変)
  - `src/linux-6.12.94/drivers/usb/core/urb.c` — `usb_kill_anchored_urbs` (`:713` 付近、H4 の核)
  - `src/linux-6.12.94/net/bluetooth/bnep/core.c` — `bnep_session` non-freezable kthread (H2)
  - `src/linux-6.12.94/net/xfrm/xfrm_state.c` — xfrm GC (H1 派生)
- **参照する (report)**:
  - `report/2026-06-28_074509_s2idle_btpan_vpn_hang_kernel_source_analysis.md` — 機序仮説 H1/H2/H4 の根拠
  - `report/2026-06-28_141226_s2idle_btvpn_ipad_manual_hang_both_driver_clean_lid_path_required.md` — lid 経路必要条件と α/β 未分離の問題提起
- **新規作成 (実機, 実装フェーズで)**:
  - `/etc/systemd/system-sleep/70-h4-probe` (S0)
  - `/etc/systemd/system-sleep/55-btusb-down` (S1)
  - `/etc/systemd/system-sleep/56-xfrm-flush` (S2)
  - `/etc/systemd/system-sleep/57-bnep-down` (S3)
  - `/lib/modules/6.12.94+deb13-amd64/updates/btusb.ko` (S5)
- **新規作成 (dev 機, S4)**:
  - `src/linux-6.12.94/` (apt-get source の展開先)
  - `linux-image-6.12.94+dpmwd1-amd64*.deb` 一式

## 検証 (各段階共通)

各 S 終了時に次の手順で確認する:
1. **journald**: `journalctl -k -b -1 --since "$(date -d '24 hours ago')"` で当該 cycle の `PM: suspend entry/exit` ペアと freeze 行を確認
2. **suspend_stats**: `cat /sys/power/suspend_stats/{fail,success,last_failed_*}` の delta
3. **pre/post snapshot 突き合わせ**: `/var/log/h4-probe/` から hang サイクルの `.pre` を抽出し残留状態を比較
4. **(S0.5)**: rtcwake / lid open 両条件の発火サイクルを分けて記録
5. **(S4/S5)**: hang 時の pstore (`/sys/fs/pstore/`) から backtrace 抽出
6. **後始末**: 各 S のフックファイル/モジュールを `rm` で除去、`pm_debug_messages` は再起動で消える

最終的に hang が消えた条件 (= 真因がどこか) を確定したら、レポートに当該条件・修正・upstream 提案案を記載し、本ラダーをクローズする。
