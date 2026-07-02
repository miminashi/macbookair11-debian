# 調査プラン: Bluetoothテザリング+VPN中のlid closeで本日2回ハング

## Context（なぜこの調査をするか）

- **事象**: 2026-06-27 に MacBook Air 11" (Early 2015 / Debian 13) が**2回ハング**。いずれも
  **Bluetoothテザリング + VPN を使用中に lid close** したときに発生（ユーザ報告）。
- **目撃証言（AskUserQuestion で確定）**:
  - 症状 = 「lid を**閉じて一旦スリープには入った**が、**開けたら画面真っ黒・無反応**」
  - 復帰 = 「**電源ボタン長押しで強制電源断が必要**」だった（電源ボタン短押しでは戻らず）
  - VPN/BT = GNOME GUI から接続 → **NetworkManager 管理**（VPN・BT-PAN ともに NM/bnep 経由の可能性大）
  - 実機 = 自宅 LAN に戻せる/オンラインにできる（※調査時点ではまだ NXDOMAIN = オフLAN）
- **症状の意味（切り分けの注意 — ここを誤読しない）**: 確実に言えるのは
  **「強制電源断が必要 = 完全ハング（UNGRACEFUL boot）」**だけ。一方で:
  - **LID0 wake は soak で無効化済み**なので、健全な機体でも **lid 開だけでは起きず真っ黒**（復帰は電源ボタン）。
    つまり「開けたら真っ黒」自体はハングの証拠ではなく、ハングの実証は**電源ボタン短押しでも復帰しなかった**こと。
  - lid close で画面は即ブランクするため、**suspend 完了直前のデッドロック（BT/bnep/VPN teardown 中）**も
    **resume 経路の失敗**も、ユーザ目視では同じ「開けたら真っ黒」に見える（5-31 レポートも
    「ログでも suspend 経路 / resume 経路を区別不能」と明記）。
  - **→ suspend 経路（BT/VPN teardown デッドロック）と resume 経路の両仮説を生かす**。真の切り分けは
    **soak ログの SLEEP 行有無 + `pm_print_times` の最終デバイス行**で行う（Step 1–2）。少なくとも
    「入眠して強制電源断に至った完全ハング」である点は症状と整合。
- **現在の構成（背景）**: 2026-06-20 から **S3(deep) 永続化（可逆）+ 2週間 passive soak** が稼働中
  （`s3-deep-apply.service` enabled / lid close 時 battery は logind STH / LID0 wake は無効化＝復帰は電源ボタン）。
  soak の唯一の go/no-go 残件が「**歴史的 S3 resume hang（週 0.7–0.8 件）の再武装**」。
  本日 2 回は **soak 中間チェックイン日（6/27）にこのリスクが顕在化した可能性**が高い。
  - ただしユーザは **BT テザリング+VPN** という共通条件を挙げている。これは目撃者信号として**重く扱う**。
    過去レポートに BT/VPN 言及が無いのは「**当時調べていない**」だけで「無関係だった」証拠ではない。
- **意図する成果**: (1) 2 回のハングを durable ログで**事実分類**し、(2) BT/VPN 相関の有無を journald で**検査**し、
  (3) 根因に応じた**可逆な対策**を選ぶ（soak 既定の「true hang→s2idle 退避」を**自動発火させない**
  — s2idle も 2026-06-01 にハング実績があり、BT/VPN が真因なら sleep mode は red herring）。

## 関連レポート / メモリ

- [2026-06-20 S3(deep) 永続化+soak 開始](../../projects/macbookair11-debian/report/2026-06-20_045414_s3_deep_persist_soak_start.md)
  — soak ログ形式・true hang 判定・ロールバック手順・STH 2ペア記録の解釈注意の出典
- [2026-05-31 S3 hang により s2idle へ切替](../../projects/macbookair11-debian/report/2026-05-31_132125_s3_hang_switch_to_s2idle.md)
  — hang 史・`check-suspend-resume.sh` の `UNGRACEFUL [S3-HANG]` 判定・「停止位置はログから特定不能」の根拠
- メモリ: `s3-revival-evaluation` / `s2idle-observation-phase`（s2idle でもハング再発）/ `low-battery-hibernate`

---

## Step 0（ユーザ作業・前提）: 実機をオンラインに戻す

`ssh miminashi@macbookair2015.lan` が通る状態にする（自宅 LAN へ）。
以降の **Step 1–3 はすべて read-only**（ログ読み出し・状態確認のみ。設定変更なし）。

---

## Step 1: durable ログで 2 回のハングを事実分類（read-only / 確定診断の核）

ground truth は**ディスク上に残っている**（soak はそのために設計された）。まずこの 1 点を引く:
**「各ハング事象に対応する soak ログの SLEEP 行はあるか、WAKE は無いか」**。

```bash
# 1) soak ログ全体（SLEEP/WAKE/BOOT 行のシーケンス）
ssh miminashi@macbookair2015.lan 'sudo cat /var/log/s3-soak.log'
# 2) 異常終了 boot の特定（強制電源断 = ungraceful な boot 境界が本日 2 件あるはず）
ssh miminashi@macbookair2015.lan 'journalctl --list-boots | tail -20'
# 3) 既存判定器があれば流用（5-31 レポートの UNGRACEFUL [S3-HANG] 判定）
ssh miminashi@macbookair2015.lan 'ls -l /usr/local/sbin/check-suspend-resume.sh /usr/local/sbin/s3-soak-report.sh 2>/dev/null; \
  sudo /usr/local/sbin/s3-soak-report.sh 2>/dev/null | tail -40'
```

**判定（discriminator）**:
- **SLEEP 行あり → 対応 WAKE 無し → 次行が BOOT**: pre フック（`60-s3-soak-log`）までは到達して入眠開始、
  以後 WAKE せず強制電源断 = **true hang** 確定。ただし **SLEEP 行があっても「suspend のより深い段（dpm_suspend）での
  ハング」と「resume 経路のハング」は soak ログだけでは分離できない**（pre フックはどちらの場合も先に走り終える）。
  → 最終的な suspend/resume の別と被疑デバイスは **Step 2 の `pm_print_times` 最終行**で確定する。
- **SLEEP 行が無い**: pre フックも走れなかった＝**入眠ごく初期でのフリーズ**（NM/BT teardown が早期に絡む像）。
  症状（開けたら真っ黒）とは矛盾しない（lid close で画面は即ブランクするため）。この場合も Step 2 へ。
- SLEEP 行の **type / ac / charge_now / gpe70 / drm_err** を 2 件とも記録:
  - `ac=0`（battery）→ lid close は **STH 経路**（30分後 RTC→hibernate 予定）。
    開けたのが 30分以内なら S3 phase の resume 失敗、30分超なら STH→hibernate(S4) 経路の失敗（C-3 安全網の破綻）。
    **STH は hibernate 到達で SLEEP/WAKE が「2ペア」記録される**点に注意（6-20 レポートの解釈注意）。
  - `gpe70`（spurious wake 源 LID0）・`drm_err`（i915/DRM エラー件数）の異常も確認。

---

## Step 2: BT/VPN 相関を journald で検査（目撃者信号の検証）

soak ログは BT/VPN 状態を記録しない（type/ac/gpe70 のみ）。相関検証には**ハングした boot の journald**が要る。
Step 1 で得た各 SLEEP 行のタイムスタンプ＝ハングした boot 番号を使う。

```bash
# ハングした boot（例: -2, -3）の suspend 直前〜末尾を、関与しうるサブシステムで grep
for B in <hang_boot_1> <hang_boot_2>; do
  echo "==== boot $B (kernel) tail ===="
  ssh miminashi@macbookair2015.lan "journalctl -k -b $B | tail -60"   # 最終行がどこで止まったか
  echo "==== boot $B suspend path: NM/BT/bnep/btusb/VPN/pm ===="
  ssh miminashi@macbookair2015.lan "journalctl -b $B | grep -iE 'NetworkManager|bluetooth|bnep|btusb|hci|wireguard|wg-|openvpn|vpn|ModemManager|PM: suspend|pm_print_times|dpm_|firmware' | tail -120"
done
```

**読み筋**:
- **`pm_print_times=1` が有効**（5-23 で永続化）なので、kernel ログの**最後に suspend した device**が出る。
  最終行が `btusb`/`bnep`/`Bluetooth hci` 等で止まっていれば **BT デバイスの suspend/resume hang** の直接証拠。
  最終行が `PM: suspend entry (deep)` だけで device 行が無ければ **S3 firmware 遷移の hang**（5-31 と同じ「可視性ゼロ」像）。
- **対照**: soak ログ中の **clean な suspend/resume サイクル**（BT/VPN を使っていない boot）と比較し、
  「BT-PAN/VPN が active だった boot だけがハングしているか」の分割表を作る（相関の強さを定量化）。
  - 注意: soak ログだけでは各サイクルの BT/VPN active を直接判定できない → 各サイクルの boot の journald で
    `nmcli`/`bnep0`/`wg`/`tun0` の存在を引いて補完する。
- VPN 種別を確定（NM 管理か独立 daemon か）:
  ```bash
  ssh miminashi@macbookair2015.lan 'nmcli -t -f NAME,TYPE,DEVICE con show; \
    systemctl list-units "wg-quick@*" "openvpn*" --all --no-pager; rfkill list'
  ```

---

## Step 3: 根因仮説の確定（Step 1–2 の証拠で分岐）

| 仮説 | 支持証拠 | 含意 |
|---|---|---|
| **A: 再武装された S3(deep) firmware resume hang**（BT/VPN は偶発/交絡） | 最終行 = `suspend entry (deep)` のみ・device 行無し・過去 0.7/週 像と一致・clean サイクルでも稀に出る | soak の go/no-go が **no-go 寄り**。ただし s2idle 退避は史実で再発のため即決しない |
| **B: BT/VPN 絡みのデバイス hang**（suspend 中の bnep/btusb/VPN teardown デッドロック **または** resume 中の再 init hang）、BT/VPN active が誘発 | 最終行が BT/NM/bnep 関連・**BT/VPN active な boot に偏在**・clean サイクルは健全 | sleep mode 非依存。**suspend 前に BT/VPN を畳む**対策が suspend 経路・resume 経路どちらの B でも有効かつ診断になる |
| **C: A+B の複合**（BT/VPN が S3 resume hang を悪化＝USB 再 enum/wake 源増） | 両方の特徴が混在・頻度が BT/VPN 時に跳ね上がる | 対策は B 系（畳む）を先に試す |

---

## Step 4: 対策（Step 3 の確定後に選択 / すべて可逆）

> 設計方針: **soak 既定の「true hang→s2idle 自動退避」は発火させない**。s2idle もハング実績があるため、
> 退避は「畳む対策が無効だった場合の stopgap」に格下げし、まず BT/VPN 相関を**安価かつ可逆に**潰す。

### 即時の行動的 stopgap（システム変更なし・本日から）
診断が済むまでは **lid close 前に手動で VPN/BT を切断**する（`nmcli con down` / GNOME で OFF）か、
**BT テザリング+VPN を使っている間は lid close しない**。これでハング（=強制電源断によるデータ損失リスク）を回避。
（※「AC につなげば安全」は誤り — AC でも suspend には入りハングし得る。確実なのは BT/VPN を切るか suspend させないこと。）

### 対策 B-1（推奨第一手・診断兼治療・可逆）: suspend 前に BT-PAN+VPN を畳む system-sleep フック
既存のフック枠組み（`/usr/lib/systemd/system-sleep/` に `50-kbd-backlight`・`60-s3-soak-log` が共存）に倣い、
**`55-net-teardown`** を追加（pre で down / post で復帰）:
- `pre`: active な NM VPN を `nmcli con down`、BT-PAN を切断、`rfkill block bluetooth`
- `post`: `rfkill unblock bluetooth`（VPN/BT の再接続は任意。手動再接続でも可）
- **狙い**: BT/bnep/VPN を **suspend 突入前のプロセス文脈で安全に畳む**ことで、(1) suspend 中に
  カーネルが dpm_suspend 内で bnep/btusb/VPN を teardown する経路と、(2) resume 時の再 init 経路の
  **両方を回避** → 仮説 B/C（suspend 経路・resume 経路どちらでも）ならハング消失。
  **数日 soak して再発ゼロなら BT/VPN 誘発を確定**。無効なら仮説 A 寄り。
- **可逆**: フック 1 ファイルの追加のみ。`rm` で即原状復帰。

### 対策 A-1（仮説 A 確定時の stopgap・可逆）: soak ロールバック
仮説 A（純 S3 firmware hang）が確定し B-1 が無効なら、6-20 レポートのロールバック手順で s2idle へ一時退避:
```bash
ssh miminashi@macbookair2015.lan '
  sudo systemctl disable --now s3-deep-apply.service
  echo s2idle | sudo tee /sys/power/mem_sleep'
# GRUB は s2idle 据え置きなので再起動で deep 設定は残らない
```
ただし **s2idle 史実ハングのため恒久解にしない**。並行して #2（gpe70 機序）/ device resume 仮説へ転回。

---

## 検証（対策の効果確認）

1. **B-1 投入後**: BT テザリング+VPN を up した状態で `systemctl suspend`（フック発火のため rtcwake 単体不可）
   → 電源ボタンで復帰 → `boot_id` 不変 / `drm_err=0` / soak ログに WAKE 行ペアを確認。
2. **実運用 soak**: 数日、**意図的に BT+VPN+lid close** を繰り返し、`s3-soak.log` と `journalctl --list-boots` で
   true hang 0 件を確認。再発時刻はユーザがメモ（自動ログと突合）。
3. **最終レポート**: `report/` に「BT/VPN+lid close ハング調査」を作成
   （タイムスタンプは `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。分割表・最終行証拠・対策・soak 結果を記載。
   プランモード作業のため本プランファイルを `attachment/.../plan.md` に添付。

## このプランで触る/作るファイル（実機）

- **読むだけ（Step 1–3）**: `/var/log/s3-soak.log`、`journalctl`、`/usr/local/sbin/{check-suspend-resume,s3-soak-report}.sh`、
  `/usr/lib/systemd/system-sleep/{50-kbd-backlight,60-s3-soak-log}`、`nmcli`/`rfkill`
- **新規追加（対策 B-1, 可逆）**: `/usr/lib/systemd/system-sleep/55-net-teardown`
- **既存サービス操作（対策 A-1 stopgap のみ・条件付き）**: `s3-deep-apply.service` の disable + `mem_sleep`
- リポジトリ側: `report/` に最終レポート 1 本（+ プラン添付）

## 未確定で実機到達後に必ず確認する点

- soak ログ・`check-suspend-resume.sh` の**実在と正確なフォーマット**（report 記載ベースで設計済みだが要現物確認）
- 2 件のハング時 **ac=0/1**（battery=STH 経路 / AC=plain suspend）と **開けるまでの経過時間**（30分閾値）
- BT/VPN が **NM 管理か独立 daemon か**（nmcli/systemd で確定）
