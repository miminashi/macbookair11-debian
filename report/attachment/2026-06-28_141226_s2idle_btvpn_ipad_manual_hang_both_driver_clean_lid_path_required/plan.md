# Plan: iPad peer での「BT-PAN × VPN × 手動 lid close」再現 → 連続して iPhone driver 自動 (s2idle peer 切り分け 2 段ラン)

## Context

親 [2026-06-28_111259](../../../../projects/macbookair11-debian/report/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md) で「Claude 駆動 `systemctl suspend` 15/15 完走・ハング 0」を確認したが、そこには 2 つの未分離変数が同居していた:

1. **経路差**: 手動 lid-close vs `systemctl suspend` (logind / LID GPE / HandleLidSwitch 系の前段が違う)
2. **peer 差**: 親 063543 のハング 3 件は **iPhone** (peer MAC `CC:60:23:AF:2C:60`, IP `172.20.10.6`)、111259 自動は **iPad** (peer `34:42:62:16:03:F6`, IP `172.20.10.13`)

このため「経路で消えたのか peer で消えたのか」が確定していない。親レポート「次の一手」(行 129–130) は

- まず **iPad peer + 手動 lid close** で再現するか見る → peer 差を分離
- 続けて **iPhone peer + driver 自動** で 15 cycle 回す → 経路差を分離

を提案している。本プランはこれを **1 つのレポートにまとめて連続実施** する。

期待される 2×2 結果と解釈 (既知の角: iPhone+manual=hang/063543、iPad+driver=clean/111259。本プランは残り 2 セルを埋める):

| iPad 手動 | iPhone driver | 解釈 |
|---|---|---|
| ハング | ハング | トリガーは BT-PAN×VPN そのもので peer/経路非依存 (111259 が 15/15 で出なかったのは小標本の運) |
| ハング | クリーン | **lid-close 経路が必要条件** (peer 非依存) — 親 111259 の示唆を強化 |
| クリーン | ハング | **iPhone peer 固有** (BT/Hotspot 挙動差) → 親 063543 の結論を「BT-PAN × VPN × iPhone」に縮める必要 |
| クリーン | クリーン | **iPhone AND manual の両方が必要** な相互作用 (3 因子条件)、まぐれではなく真の AND |

ハングが出れば各実験は**そのサイクルで打ち切り**(`PHASE DONE` 欠落 = signature)、出なければ N まで回しきる。Claude は read-only 監視 + 状況確認役で、suspend 注入や物理操作は行わない (driver 起動を除く)。

## 実験 1: iPad peer + 手動 lid close (10 cycle 目標)

### 操作分担

- **ユーザ**: 物理操作 (WiFi off (GUI で)、BT/VPN up、lid 開閉、ハング時の電源ボタン長押し、再起動、実験 1 終了時の WiFi 再接続)
- **Claude (ssh, read-only)**: 開始前 snapshot、ユーザが「状況確認」と言ったときに ssh が通れば状態取得 (通らなければ「WiFi 再接続してから依頼してほしい」と返す)、ハング後の再起動→自動 wifi 復帰後の判定、終了時 retrospective 集計

### 重要 — 監視の根本制約 (advisor 指摘)

実験中は **WiFi off** で MacBookAir が `172.20.10.x` のホットスポット網に居るため、開発機から `macbookair2015.lan` (mDNS over LAN) は**解決できず ssh が通らない**。よって:

- **per-cycle のリアルタイム PRECHECK は不可能**。「毎サイクル Claude に確認させる」運用は組まない (親 063543 でも同じ理由で sshは「到達可なら」と但し書きされている)
- 代わりに **2 つの durable ローカルログ**で各サイクルを**事後的 (retrospective) に**再構成する:
  - `/var/log/s3-soak.log` — system-sleep フックが SLEEP/WAKE/BOOT を永続化 (sync 済)
  - `journalctl -b N` (N=現在 boot or `-1` で前 boot) — strongSwan の `deleting IKE_SA … 172.20.10.13` 行と bnep/enx98 teardown 行 → **VPN が BT-PAN 経由でアクティブだったことの per-cycle 証拠**
- Claude が ssh を叩けるタイミングは限定:
  1. 実験開始前 (WiFi 接続中、開始 snapshot 取得)
  2. ユーザが WiFi を一時的に GUI で再接続してから「状況確認」と言ったとき (途中経過の retrospective レビュー)
  3. ハング → 強制電源断 → 再起動 → wifi 自動復帰後 (= 自動)
  4. 実験 1 完走時にユーザが WiFi を再接続したとき (実験 1 終了 snapshot + 実験 2 移行準備)

### 前提条件 (Claude が ssh で 1 回確認、開始前)

```bash
ssh miminashi@macbookair2015.lan '
  echo "=== sleep config ==="
  cat /sys/power/mem_sleep                                       # 期待: [s2idle] deep
  grep LID0 /proc/acpi/wakeup                                    # 期待: LID0 *enabled
  systemctl is-enabled s3-deep-apply.service 2>/dev/null         # 期待: disabled
  cat /etc/systemd/system-sleep/60-s3-soak-log 2>/dev/null | \
    grep -E "^(echo deep|#echo deep)" || true                    # 期待: コメント (#echo deep) ＝ deep 強制無効
  echo "=== power ==="
  cat /sys/class/power_supply/ADP1/online                        # 期待: 1 (AC)
  cat /sys/class/power_supply/BAT0/capacity                      # 参考値
  echo "=== bt/peer ==="
  bluetoothctl devices Connected | grep -i pad || echo "iPad not connected yet"
  echo "=== existing soak.log tail ==="
  sudo tail -n 5 /var/log/s3-soak.log                            # 直前境界の基準値
  echo "=== boot info ==="
  cat /proc/sys/kernel/random/boot_id
  uptime -p
  cat /sys/power/suspend_stats | head -20                        # success/fail 開始値
'
```

期待: `mem_sleep=[s2idle]` / `LID0 *enabled` / `s3-deep-apply=disabled` / `60-s3-soak-log` 内の `echo deep` がコメント化 (= 2026-06-28 時点の修正済み状態) / `ADP1/online=1`。
**齟齬があればここで停止してユーザに報告** (例: deep に化けるフックが残っていれば実験 invalid)。

### 各サイクルでユーザが踏む手順 (親 063543 と同じプロトコル)

1. (初回のみ) iPad の Personal Hotspot を ON、Mac で iPad と Bluetooth ペアリング済を確認
2. **WiFi を NM GUI で切断** (この瞬間に ssh は切れる。`nmcli dev disconnect wlp3s0` を ssh で叩く運用は採らない — ssh セッション自身を切ってしまうため)
3. **BT テザリング接続** (`iMiminashiPadPro ネットワーク` を up、PAN iface に `172.20.10.13/28` が付くのを確認)
4. **VPN (GSNet) を up** (BT-PAN 経由でルーティングされていることを確認 — strongSwan の IKE_SA が `172.20.10.13` から張られる)。WiFi off により default route が BT-PAN gw になっているはずなので明示的な経路切替は不要
5. **蓋を閉じる** → s2idle に入る
6. **数秒〜十数秒後に蓋を開ける**
7. 復帰すれば次のサイクルへ (BT/VPN は up のまま保持、毎サイクル張り直さない — 親 063543 と同じ)
8. **復帰しなければ電源ボタン長押し**で強制電源断 → 再起動 → wifi 自動復帰 → Claude に「ハングした」を告げる → ハング判定フェーズへ
9. (希望時のみ) サイクル途中で「状況確認」を依頼したい場合は**ユーザが GUI で wifi を一時的に再接続**してから Claude に依頼 → 確認後にまた wifi off にして再開

### Claude が「状況確認」依頼時に叩くスニペット (親 063543 行 99–108 のものを流用)

```bash
ssh miminashi@macbookair2015.lan '
  echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)  uptime=$(uptime -p) since=$(uptime -s)"
  echo "ac=$(cat /sys/class/power_supply/ADP1/online) cap=$(cat /sys/class/power_supply/BAT0/capacity)% mem_sleep=$(cat /sys/power/mem_sleep)"
  sudo tail -n 6 /var/log/s3-soak.log
  nmcli -t -f NAME,TYPE,DEVICE con show --active | grep -Ei "bluetooth|vpn"
  sudo journalctl -b 0 -g "PM: suspend (entry|exit)" -o cat | sort | uniq -c'
```

**到達不能なら判定保留**:「suspend 中かハングか不明、wifi を一時 ON にしてから再依頼してほしい」とユーザに返す (親 063543 の運用ルール — `ssh 不通だけではハング判定しない`)。

### 条件成立の retrospective 検証 (driver 無しの手動運用に必須 — advisor 指摘)

driver 経由の 111259 は PRE 行に `panup=ok / pan_ip / vpnup=ok / xfrm_src` を sync で永続化していたため「条件成立サイクル」を per-cycle で立証できた。**手動運用ではこれが取れない**。よって**事後 (retrospective) に journald から各サイクルの条件成立を再構成する**。これをやらないと「クリーン 10/10」と出ても**条件未成立で空回りしていただけ**の可能性を排除できない (= 結果が無意味になる)。

```bash
# 各サイクル境界 (s3-soak.log の SLEEP 時刻 ±数秒) で以下が記録されているか確認
ssh miminashi@macbookair2015.lan '
  sudo journalctl -b 0 -g "deleting IKE_SA GSNet" -o short-iso | grep "172.20.10.13"   # VPN が BT-PAN 経由だった証拠 (各 SLEEP 直前にあるはず)
  sudo journalctl -b 0 -g "enx98e0d98d205e|bnep" -o short-iso                            # BT-PAN teardown が走った証拠
'
```

期待: N サイクルなら N 件 (誤差 ±1) の `IKE_SA delete` 行と enx98/bnep teardown 行が記録される (親 063543 表 §2 と同じ要領)。**1 サイクルでも欠けていればそのサイクルは「条件未成立で無効」扱い**し、有効サイクル数を分母に再集計する。

### deep vs s2idle 連続 gate (continuous、advisor 指摘 — 過去の最大ミスへの対策)

過去の最悪ミス (memory) は「s2idle と思っていた実体が deep だった」(soak フックの `echo deep` 残存で毎 suspend が deep に化けた)。**開始前 1 回チェックでは再発を防げない**。各サイクルで s2idle 維持を確認する:

- **正常サイクル**: `sudo journalctl -b 0 -g "PM: suspend entry" -o cat` を retrospective に叩き、**全エントリが `(s2idle)`** であることを確認 (1 件でも `(deep)` があれば実験 invalid → 中断 → フック再点検)
- **ハングサイクル**: 当該 entry 行は journald flush 前に停止して残らないため、親 063543 と同じ 4-pronged 根拠で s2idle 確定:
  1. `/sys/power/mem_sleep` の選択が `[s2idle]`
  2. `/etc/systemd/system-sleep/60-s3-soak-log` の `echo deep` がコメント化
  3. 同 boot の他 suspend 全てが `(s2idle)`
  4. soak ログ最終 SLEEP 行が `type=suspend` (mode=s2idle と判定)

### ハング判定 (Claude、強制電源断後)

```bash
ssh miminashi@macbookair2015.lan '
  echo "=== boot signature ==="
  echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"      # 直前値と比較 → 変化していればリブート確定
  uptime -p                                                    # 短ければ強制電源断直後
  echo "=== s3-soak.log: SLEEP/WAKE pair check ==="
  sudo tail -n 6 /var/log/s3-soak.log                          # 最後の SLEEP に対応する WAKE が無く、BOOT が次行に来ているか
  echo "=== PM entry/exit count (current boot) ==="
  sudo journalctl -b 0 -g "PM: suspend (entry|exit)" -o cat | sort | uniq -c
  echo "=== suspend_stats ==="
  cat /sys/power/suspend_stats | head -25                      # success/fail 差分
  echo "=== last visible lines before hang (previous boot) ==="
  sudo journalctl -b -1 -n 50 -o short-monotonic | tail -30   # 停止位置 (期待: kbd-backlight-sleep が最終)
'
```

True hang 確定の 3 点セット:
- s3-soak.log: 最後の SLEEP に対応する WAKE 行欠落 + 次行が BOOT
- `PM: suspend entry` が `PM: suspend exit` より 1 多い
- 前 boot の最終可視行が `kbd-backlight-sleep: pre/suspend:` 周辺 (親 063543 と同じ signature)

### 終了条件 (実験 1)

- ハング 1 件発生 → 実験 1 終了 (peer 差なしで再現 = 親 063543 結論強化)、レポートにシグネチャ記録 → 実験 2 へ
- 10 cycle 全完走 → 実験 1 終了 (iPad peer ではクリーン = peer 差の可能性) → 実験 2 へ

## 実験 2: iPhone peer + driver 自動 (15 cycle、駄目押し)

### 実験 1 → 実験 2 の移行ステップ (advisor 指摘 — wifi up が必須)

driver 起動には ssh 必須 → ssh は wifi 経由 → 実験 1 終了時点は wifi off。よって以下の順で移行する:

1. **ユーザ**: iPad の Personal Hotspot を OFF → BT 切断 → **WiFi を GUI で再接続** (LAN 復帰 → ssh が通るようになる)
2. **ユーザ**: iPhone の Personal Hotspot を ON → MacBookAir 側で iPhone との BT ペアリング・接続を確認 (まだ WiFi は ON のまま)
3. **Claude**: ssh で iPhone 接続確認 (BT peer MAC が iPhone の `CC:60:23:AF:2C:60` になっていること、`bluetoothctl devices Connected`)
4. **Claude**: driver を BTVPN 引数で起動 → **driver が自身で wifi を切断して blind 運用に入る** (= 111259 と同じ振る舞い)

### 操作分担

- **ユーザ**: 物理 (iPad との BT 切断 → WiFi 再接続 → iPhone の Personal Hotspot ON → iPhone とペアリング確認)
- **Claude (ssh)**: BT 接続確認 / dry-run 起動 / 本番 driver 起動 / ハング時 再起動後の状況確認

### 前提条件確認 (Claude が ssh で実施)

iPhone NM 接続名 = `iMiminashiSE ネットワーク`、期待 PAN IP `172.20.10.6/28` (親 063543 と同じ)。
PAN iface 名は hci0 MAC 由来で iPad と同じ `enx98e0d98d205e` のはず (再確認)。

```bash
ssh miminashi@macbookair2015.lan '
  nmcli -t -f NAME,TYPE con show | grep -i bluetooth
  bluetoothctl devices Connected
  sudo nmcli con up "iMiminashiSE ネットワーク"
  ip -4 -o addr show | grep enx
'
```

### Dry-run (N=0) で機構検証

`susp-btvpn-driver.sh` (v3、既に `/usr/local/bin/` に配置済) を **iPhone 用 引数** で N=0 起動:

```bash
ssh miminashi@macbookair2015.lan '
  sudo systemd-run --unit=susp-btvpn-iphone-dry --collect \
    /usr/local/bin/susp-btvpn-driver.sh DRY 0 on 30 15 \
      "iMiminashiSE ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
'
sleep 15
ssh miminashi@macbookair2015.lan '
  sudo tail -n 10 /var/log/susp-test.log | grep DRYRUN
'
```

期待: `DRYRUN PRECHECK panup=ok pan_ip=172.20.10.6 vpnup=ok xfrm_src=172.20.10.6` (PAN IP が iPhone 系の `.6` に落ちることを確認)。

### 本番 (N=15)

```bash
ssh miminashi@macbookair2015.lan '
  sudo systemd-run --unit=susp-btvpn-iphone --collect \
    /usr/local/bin/susp-btvpn-driver.sh BTVPN 15 on 30 15 \
      "iMiminashiSE ネットワーク" enx98e0d98d205e GSNet 160.16.210.47 wlp3s0
'
```

起動直後に **driver 自身が wifi 切断** → 実機は LAN 外で blind 運用に入る。ハング時は強制電源断 → 再起動で wifi 自動復帰 → ssh 再開を待つ (driver 設計、親 111259 行 85 で未実証だった経路がここで初実証される可能性)。

### 完走 / ハング判定 (実験 2)

正常完走: `susp-test.log` に `PHASE DONE phase=BTVPN`、15 ITER の PRE/POST 完備、`s3-soak.log` 15 SLEEP/WAKE ペア。
ハング: PRE あり POST 無しの最終 iteration、`s3-soak.log` SLEEP→BOOT、boot_id 変化。
ssh が再開したら Claude が状況確認スクリプトで判定。

## 重要なファイル (流用、編集しない)

- driver 本体: `/usr/local/bin/susp-btvpn-driver.sh` (実機、既に v3 配置済 — `report/attachment/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang/susp-btvpn-driver.sh` と同内容)
- ログ:
  - `/var/log/susp-test.log` (driver 追記、PHASE START / ITER PRE/POST / PHASE DONE)
  - `/var/log/s3-soak.log` (system-sleep フック追記、SLEEP / WAKE / BOOT)
  - `journalctl -b 0` (実時間の補助、ハング後は `-b -1` で停止位置を見る)
- system-sleep フック (実機 `/etc/systemd/system-sleep/60-s3-soak-log`): **deep 強制行がコメント化** されていること、これが s2idle 維持の前提
- 関連レポート: 親 [111259](../../../../projects/macbookair11-debian/report/2026-06-28_111259_claude_driven_systemctl_suspend_btvpn_no_hang.md)、孫 [063543](../../../../projects/macbookair11-debian/report/2026-06-28_063543_s2idle_btpan_vpn_lid_close_hang_manual_repro.md)、ひ孫 [021019](../../../../projects/macbookair11-debian/report/2026-06-28_021019_s2idle_bt_tethering_suspend_repro.md)

このプランで編集する成果物は **新規レポート 1 本** のみ:
- ファイル名 (例): `report/yyyy-mm-dd_hhmmss_s2idle_btvpn_ipad_manual_then_iphone_driver.md`
- timestamp は実験開始時に `TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S` で取得
- attachment ディレクトリ `report/attachment/<同名>/` に下記をコピー:
  - 本プラン (`plan.md`)
  - 実験 2 driver の `susp-test.log` 抜粋
  - 実験 1+2 の `s3-soak.log` 実験窓抜粋
  - ハング発生時は前 boot の `journalctl -b -1` 抜粋 (`hang-journal-excerpts.log`)
  - 実験 1 の Claude 集約ログ (開始 snapshot / 状況確認 / retrospective IKE_SA 検証 / `PM: suspend entry (s2idle)` 件数 / ハング判定 を 1 ファイルに集約)

## 検証 (end-to-end)

- 実験 1 終了時 (retrospective): s3-soak.log の SLEEP/WAKE ペア (10 ペア期待 or 途中で SLEEP→BOOT) + journal の `deleting IKE_SA … 172.20.10.13` 件数 ≒ SLEEP 件数 (条件成立サイクル数) + suspend_stats 差分 (success +N or +K with fail)
- 実験 2 終了時: susp-test.log に 15 PRE/POST 揃い + PHASE DONE + s3-soak.log 15 ペア、または途中切れ (driver の PRE で `xfrm_src=172.20.10.6` が per-cycle 立証されている)
- 全体: `PM: suspend entry (s2idle)` 件数と `exit` 件数の差 = ハング件数と一致すること、かつ全 entry が `(s2idle)` (1 件でも `(deep)` があれば実験 invalid)
- レポート完成時: Discord webhook 通知が `report/*.md` の Write で自動発火 (CLAUDE.md 記載のフック動作)

## 留意

- 実験 1 中、**BT/VPN は初回だけ up してそれ以降は up 状態を維持**する (親 063543 と同じ。「サイクル毎に張り直す」と driver の自動経路と被って独立性が落ちる)。蓋を閉じている間に NM が論理 teardown するのは親 063543 の観察から既知 (suspend 前に IKE_SA delete と bnep teardown が完走) — これは仕様で、復帰後は NM が自動で再 up する想定
- 実験 1 でハングが出たら**実験 2 の dry-run までは進めるが、本番ランをやるか**はユーザの判断ポイント (ハングが peer 非依存と分かれば iPhone 駄目押しの限界価値は下がる) — Claude はその時点でユーザに確認する
- `GSNet` の `password-flags=0` は 111259 で設定済のはず (実機状態は driver 起動時に判明) — `nm-strongswan-auth-dialog: cannot open display` が出たら headless con up 不可なので実験 2 を中断
- 実験 1 で「VPN を BT 経由で張る」のは GNOME GUI からだと手数が多い。ユーザが nmcli で `nmcli con up "iMiminashiPadPro ネットワーク" && nmcli con up GSNet` を 1 行で叩く方が早い (希望に任せる)
- ハング誘発を物理操作で行う以上、強制電源断による I/O ロス・dirty fs の可能性あり。実験 1 開始前にユーザが大きな書き込み作業をしていないことを暗黙の前提とする
