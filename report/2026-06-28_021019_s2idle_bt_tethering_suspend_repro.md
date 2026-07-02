# s2idle + BTテザリングでの suspend ハング再現実験 — および「s2idle ロールバック不完全」の発見

- **実施日時**: 2026年6月28日 02:10 (JST)
- **位置づけ**: [2026-06-27 事故調査レポート](2026-06-27_072510_bluetooth_vpn_lid_close_hang.md)の結論（**S3(deep) は no-go → s2idle へロールバック**）を受けた**追試**。ユーザ報告「s2idle に戻したのに BT テザリングで 3 回目くらいの suspend でハングした」を、手動 suspend ループで切り分ける。

## 結論（先に要約）

1. **ユーザが体験した「s2idle でのハング」は、実体としてはまだ deep モードのハングだった。** ロールバックは**不完全**で、`60-s3-soak-log` system-sleep フックに残っていた「毎 suspend 前に `echo deep > /sys/power/mem_sleep` ＋ `LID0` 凍結」のコードが、**実際の suspend を毎回 deep に化けさせていた**。真の s2idle は本日の本実験まで一度も走っていなかった。
2. このフックの強制 deep/LID0 を無効化し、**初めて `PM: suspend entry (s2idle)` を実証**。
3. **真の s2idle 下では、BTテザリング(active BT-PAN)ありでもハングは再現しなかった。**
   - Phase A（BTなし）: **10/10 完走・ハング 0**
   - Phase B（BTあり・PAN実up・アクティブ通信）: **10/10 完走・ハング 0**
   - deep モードでは active BT-PAN で **~3 suspend 以内**にハングしていた（6/27 レポート）のと**明確な対照**。
4. **ただし本実験は全て AC 給電・s2idle・各10サイクル**。前回ハングが集中した **battery/STH 経路は未検証**であり、10サイクルは小標本。「s2idle なら絶対安全」とは言えない（後述の留意）。

## 添付ファイル

- [手動 suspend ループのログ (susp-test.log)](attachment/2026-06-28_021019_s2idle_bt_tethering_suspend_repro/susp-test.log)
- [実験期間の soak ログ抜粋 (s3-soak.log の SLEEP/WAKE)](attachment/2026-06-28_021019_s2idle_bt_tethering_suspend_repro/s3-soak-experiment-window.log)
- [再現ドライバ v2 (susp-test-driver.sh)](attachment/2026-06-28_021019_s2idle_bt_tethering_suspend_repro/susp-test-driver.sh)

## 前提・目的

- **事象（ユーザ報告）**: 6/27 レポートの結論で s2idle にロールバック後、**BTテザリングを使うと 3 回目くらいの suspend でハング**した。
- **目的**: 「BTテザリングなし 10回」「BTテザリングあり 10回」の手動 suspend を実機で繰り返し、s2idle 下で BTテザリングがハングを誘発するかを切り分ける。
- **前提**: 6/27 レポートの最新結論は「根因は BT 非依存の内在的 **S3-deep** hang、BT-PAN は増悪 stressor、S3 deep は no-go → s2idle へロールバック」。本実験はそのロールバックが実効していることが前提だったが、**前提自体が崩れていた**（下記「調査結果1」）。

## 環境情報

- 機種: MacBook Air 11" (Early 2015) / OS: Debian 13 (trixie) / カーネル `6.12.94+deb13-amd64`
- スリープ: 実験開始時 `/sys/power/mem_sleep` = `[s2idle] deep`、GRUB `mem_sleep_default=s2idle`（恒久）、`s3-deep-apply.service` = **disabled**、`LID0 S4 *enabled`（凍結解除済み）。
- system-sleep フック: `50-kbd-backlight`, `60-s3-soak-log`（※後者に残存していた deep 強制を本実験で無効化）。`55-net-teardown`（btusb unload 保険）は撤去済み。
- 電源: AC 給電（`ADP1/online=1`）、バッテリ 87%。
- **Bluetooth/テザリング**: `btusb`(USB)/`hci0`、NM 接続 `iMiminashiSE ネットワーク`(type=bluetooth)、peer `CC:60:23:AF:2C:60`。PAN = `enx98e0d98d205e`（旧 bnep0）、IP `172.20.10.6/28`、GW `172.20.10.1`。
- 操作対象は ssh 接続先の実機 `macbookair2015.lan`。本セッションは `/sandbox` 無効でサンドボックス外から ssh。

## 調査結果

### 1. ロールバックは「不完全」だった（最重要の発見）

ロールバック設定（GRUB=s2idle / `s3-deep-apply.service` disabled / LID0 凍結解除）は入っていたが、起動直後 `[s2idle]` 選択だったにもかかわらず、**最初の suspend で実モードが deep になった**:

```
# スモークテスト（BTなし1回）の journal
kernel: PM: suspend entry (deep)   ← s2idle のはずが deep!
```

原因は `60-s3-soak-log`（"ログ専用" のはずのフック）の `pre` 節に残っていた強制コード:

```sh
# drift 防止: 毎 suspend 前に deep + LID0 無効を再アサート(ガード付き=冪等)
echo deep > /sys/power/mem_sleep 2>/dev/null
if grep -q 'LID0.*\*enabled' /proc/acpi/wakeup; then echo LID0 > /proc/acpi/wakeup; fi
```

これにより、**毎 suspend ごとに silently deep へ再切替＋LID0 を再凍結**していた。

- soak ログの WAKE 行が起動後も `lid=*disabled` を示し続けたのは、起動毎ではなく**毎 suspend で再凍結**されていたため。
- **副作用: ロールバック期間中は lid 開けでの復帰(lid-open wake)も壊れていた。** 起動直後は `LID0 *enabled` でも、最初の suspend で フックが LID0 を再凍結するため、以降は蓋を開けても復帰せず電源ボタンが必要な状態だった（凍結解除したつもりが実効していなかった）。
- **ユーザが「s2idle に戻したのに BT でハングした」と感じた現象は、実体としては deep モードのハング**だった（6/27 レポートの #1〜#4 と同じ S3-deep hang signature）。直近の 6-28 01:24:27 のハング（強制電源断 01:26:18）も、journal で `PM: suspend entry (deep)` ＋ active BT-PAN(bnep0/enx98e0)を確認済み。
- なお boot -1 では、フックの毎 suspend 強制とは別に **19:35 に手動の `sudo tee /sys/power/mem_sleep`／`tee /proc/acpi/wakeup`** も走っており（journal）、当該 boot は二重に deep へ固定されていた。結論は変わらないが「どれだけ確実に deep だったか」の傍証。

#### 対処
- フックの当該 2 行を行頭 `#` で無効化（ログ機能は維持）。
- ランタイムで `echo s2idle > /sys/power/mem_sleep`、`LID0` トグルで wake を再有効化。
- 再スモークで **`PM: suspend entry (s2idle)` を確認**、かつ以後 mem_sleep `[s2idle]`／`LID0 *enabled` が**全サイクルで維持**されることを確認。

> 補足の落とし穴: フックのバックアップを**同じ `system-sleep/` ディレクトリ内に実行属性付きで置いた**ところ、systemd-sleep がその `.bak`（旧ロジック入り）も実行して deep を再アサートし続けた。`.bak` を `/root/sleep-hook-backups/` へ退避して解消。**system-sleep ディレクトリにはバックアップを置かない**こと。

### 2. 実験結果 — s2idle では BTテザリングありでもハングしなかった

| Phase | 条件 | サイクル | 結果 |
|---|---|---|---|
| A | **BTなし** / AC / s2idle | 10 | **10/10 完走・ハング 0** |
| B (v2) | **BTあり**（PAN実up `panup=ok`・gateway へ持続 ping＝active 通信）/ AC / s2idle | 10 | **10/10 完走・ハング 0** |

裏付け（独立記録との突合）:
- boot0 の `PM: suspend entry = 28` / `PM: suspend exit = 28`（全 suspend に exit 対応＝**ハングなし**）。28 = 診断中の壊れた smoke 2回(deep) + 修正後 smoke 1回(s2idle) + Phase A 10 + Phase B v1 5 + Phase B v2 10。内訳は s2idle=26 / deep=2（deep は修正前の壊れた smoke のみ）。
- `/sys/power/suspend_stats`: `success=28 fail=0 last_failed_dev=（空）`（boot0 累計、上記 28 と一致）
- soak ログ（独立フック）: 実験窓の WAKE **30 件すべて `drm_err=0`**。※この「30」は **時間窓 `2026-06-28T0[12]:` ベース**の集計で boot0 の 28 resume に加え **boot -1 末尾**（01:20 の resume + 01:24:27 の既存ハング SLEEP）を含むため、boot0 の 28 とは母数が異なる（等号ではない）。drm エラーが全件 0 であることの確認が主眼。SLEEP=31/WAKE=30 の差分 1 は boot -1 の 01:24:27 ハング（SLEEP のみ・WAKE 無し）であり、本実験中の新規ハングではない。
- 実験全体で **uptime 連続・再起動 0**（ハングなら強制電源断→uptime リセットになる）

#### Phase B の妥当性に関する注意（途中で 1 度やり直した）
- 初版(v1)は「PAN を一度上げて 10 回ループ」する設計だったが、**resume 後に NM が BT を自動再接続せず**（`unmanaged-sleeping` のまま）、cycle 2 以降は **PAN down のまま suspend** していた＝ active BT-PAN を再現できていなかった。v1 は破棄。
- v2 で**各サイクルの suspend 直前に `nmcli con up` で PAN を再接続し、iface に IPv4 が付くのを確認(`panup=ok`)してから suspend**。全 10 サイクルで `panup=ok pan_ip=172.20.10.6/28` を記録し、**BT PAN が実 up・アクティブ通信中の suspend** を担保した。
- **実使用との対比（代表性の注意）**: 実使用の boot -1（01:20:47）では resume 後 **~14 秒で `bnep0 connected`** し PAN が自動復活していた。一方、本テスト v1 は **`gap=35s`（=14s の再接続所要を上回る猶予）を与えていたにもかかわらず**、cycle 2 以降 **NM が BT 接続を自動再接続せず**（device が `disconnected`／`unmanaged-sleeping` のままで `bnep0 connected` が出ない）、PAN down のまま suspend していた。つまり **タイミング(cadence)不足ではなく、この文脈で NM の autoconnect が発火しなかった** のが原因。v2 は毎サイクル明示的に `nmcli con up` するため、実使用と同等以上に確実に BT を up させた状態で suspend できている（＝Phase B の陰性結果はその分強い）。なお実使用そのものの忠実な再現ではない点は留意。

### 3. deep との対照

6/27 レポートでは **deep モード＋active BT-PAN** で **~3 suspend 以内**にハングが顕在化していた。本実験の **s2idle＋active BT-PAN は 10 サイクル無事**。この対照は、6/27 の「ハングは S3-deep の firmware 遷移中に局在」という観察と整合し、**s2idle ではその経路を踏まないため再現しない**という解釈を支持する（s2idle は CPU/firmware を deep の S3 ステートに落とさない）。

> **証拠品質の非対称性に注意**: deep 側の「~3 suspend 以内」はユーザの**体感ベース**（当該期間は本実験で deep と確定済みなので帰属は妥当だが、対照可能な制御下のカウントではない）、s2idle 側は**制御下の 10/10 という計測データ**。両者の証拠の質は同等ではない。「deep で出たものが s2idle では 10 回出なかった」という相対的陰性シグナルとして読むべきで、deep モードでの正確な期待ハング率と直接比較できる対称データは取得していない。

スケジュール確認: 実機に deep を再アサートする／自動 suspend を注入する **systemd timer・cron は存在しない**（`s3-deep-apply.service` は disabled、GRUB 既定 s2idle、フック修正済み）。よって**次回再起動後も s2idle が維持**される。

## 再現方法

操作はすべて `ssh miminashi@macbookair2015.lan` 経由。ハング時は ssh 切断→**物理電源ボタン長押しでの強制電源断が必須**（実機の前で待機して実施）。

1. **ロールバックの実効化**（本実験で判明した必須前処理）:
   ```bash
   # 60-s3-soak-log フックの強制 deep/LID0 を無効化（ログ機能は残す）
   sudo sed -i \
     -e '\|echo deep > /sys/power/mem_sleep| s|^|# DISABLED-rollback-2026-06-28: |' \
     -e '\|echo LID0 > /proc/acpi/wakeup| s|^|# DISABLED-rollback-2026-06-28: |' \
     /usr/lib/systemd/system-sleep/60-s3-soak-log
   # ランタイム反映
   echo s2idle | sudo tee /sys/power/mem_sleep
   grep -q 'LID0.*\*disabled' /proc/acpi/wakeup && echo LID0 | sudo tee /proc/acpi/wakeup
   ```
   （※フックのバックアップは `system-sleep/` の**外**へ。同ディレクトリ内の実行可能ファイルは全て suspend 時に実行される。）

2. **ドライバ配置**（[susp-test-driver.sh](attachment/2026-06-28_021019_s2idle_bt_tethering_suspend_repro/susp-test-driver.sh)）: 各サイクルで PRE 行を `sync` 永続化 → `rtcwake -m no -s N`（アラームのみ）→ `systemctl suspend`（systemd 経路＝フック発火）→ 復帰後 POST。PAN 名を渡すと毎 suspend 前に `nmcli con up`＋IP 確認。
   ```bash
   sudo cp susp-test-driver.sh /usr/local/bin/; sudo chmod +x /usr/local/bin/susp-test-driver.sh
   ```

3. **Phase A（BTなし）** — detached の transient service で ssh 切断・suspend を生存:
   ```bash
   sudo systemd-run --unit=susp-phaseA --collect \
     /usr/local/bin/susp-test-driver.sh A-noBT 10 off 30 15
   ```

4. **Phase B（BTあり・アクティブ通信）**:
   > 落とし穴: ssh の非対話セッションでは素の `nmcli con up` は polkit に `Not authorized to control networking` で弾かれる。**`sudo nmcli` が必須**（systemd-run でドライバを root 実行する v2 の `pan_up()` も同理由で root 権限前提）。
   ```bash
   sudo nmcli con up "iMiminashiSE ネットワーク"          # PAN を上げる
   sudo systemd-run --unit=bt-ping --collect ping -i 1 172.20.10.1   # 持続 ping（active 通信）
   sudo systemd-run --unit=susp-phaseB --collect \
     /usr/local/bin/susp-test-driver.sh B-BT 10 on 30 12 "iMiminashiSE ネットワーク" enx98e0d98d205e
   ```

5. **監視**（スリープ中は新規 ssh が `No route to host` になるため接続リトライを効かせる）:
   ```bash
   ssh -o ConnectionAttempts=60 -o ConnectTimeout=3 \
       -o ServerAliveInterval=10 -o ServerAliveCountMax=40 miminashi@macbookair2015.lan \
       'timeout 850 bash -c "while systemctl is-active --quiet susp-phaseB; do sleep 5; done"; \
        sudo grep B-BT /var/log/susp-test.log'
   ```

6. **判定**: durable ログ `/var/log/susp-test.log` で「PRE あり・POST 無し」が停止点＝ハング。併せて `journalctl -b 0 -g "PM: suspend entry|exit"` の entry/exit 件数一致、`/sys/power/suspend_stats`、soak ログ `drm_err` を突合。

## 留意・次の一手

- **本実験は AC 給電・s2idle・各10サイクルの範囲の結論**。前回ハングが集中した **battery/STH 経路（lid close → suspend-then-hibernate）は未検証**。さらに、証明済みの直近ハング（6-28 01:24:27）は **VPN(GSNet/IKE)も同時稼働**していたが、本 Phase B は **battery/STH も VPN も落としている**。つまり**ユーザの実条件（battery + lid close + VPN + BT-PAN）こそが未検証**で、最も切り分けたい条件が手つかず。次にやるなら「証明済みハング条件のまま deep→s2idle だけ反転」（battery・lid close→STH・VPN+BT 両アクティブ・s2idle）が筋。「AC s2idle がクリーンなら次に battery/STH」という advisor 助言とも整合。
- 10 サイクルは小標本。s2idle の素のハング率（メモリ記載で 6/01 に s2idle ハングの実績あり）はゼロではない。本結果は「deep で ~3 回以内に出たものが s2idle では 10 回出なかった」という**相対的な強い陰性シグナル**であり、絶対安全の証明ではない。
- **現状の実機**: `[s2idle]` 選択／`LID0 *enabled`／フックの deep 強制無効化済み／`bt-ping` 停止済み＝**意図どおりの s2idle ロールバック状態**で着地。
- 残置物（任意で撤去可）: `/usr/local/bin/susp-test-driver.sh`、退避した `/root/sleep-hook-backups/60-s3-soak-log.bak-*`、`/var/log/susp-test.log`。
