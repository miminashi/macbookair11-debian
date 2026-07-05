# Phase C-5: dpmwd4 — 停止境界のデバイス実名取得

## Context

Phase C-4 (report 2026-07-05_185344) で、BT-PAN+VPN+radio-off lid-close hang の停止域が「wake 成功後の dpm resume noirq/early 段のデバイス境界」(main.c:627/700/836) と確定した。残る未知は**どのデバイスの境界で止まるか**の実名のみ。dpmwd3 の firmware-safe encoding は容量制約 (user 16 × file 397 = 6352 ≤ mon×mday×hour 8064) で dev チャネルを廃止したため、デバイス名が取れない。

本セッション (Phase C-5) では dpmwd4 = 「resume 側の site 書込みをデバイス書込みに置換する」小改造カーネルをビルド・デプロイし、hang 再演でデバイス実名を取得する。

## 設計 (dpmwd4 encoding)

レポート原案 (user=15 単一マーカー + TRACE_DEVICE/TRACE_RESUME 順序入替) を発展させ、**phase 別 pre/post マーカー方式**を採用する:

- resume 側 3 関数の開始/終了 TRACE (main.c 626-627 / 700 / 791-792 / 836 / 928-929 / 1001) を**デバイス書込みに置換** (site 書込みは削除):
  - `device_resume_noirq`: entry = **user 10**, exit = **user 11**
  - `device_resume_early`: entry = **user 12**, exit = **user 13**
  - `device_resume` (main): entry = **user 14**, exit = **user 15**
  - file フィールド = `hash_string(DEVSEED=7919, dev_name(dev), 397)`
  - 書込み位置は現行 TRACE と同一行位置 (entry は関数冒頭、exit は現 TRACE_RESUME(error) の位置) — C-4 の観測との対応を保つ
- **RTC 書込み回数は dpmwd3 と同一** (1 device × 1 phase あたり 2 回) — pm_trace 摂動を増やさない
- 停止時の読み: user 10-15 → 「どの phase のどの境界か」が user で確定、デバイス実名は boot 時に dpm_list を hash 照合して全一致を列挙 (旧 `show_dev_hash` の要領、mod 397)。user 0-9 → 従来どおり site decode
  - **解釈規則**: pre marker (10/12/14) 停止 = そのデバイスの callback 実行中 or `dpm_wait_for_superior` 待ち (watchdog 60s 沈黙なら後者が濃厚)。post marker (11/13/15) 停止 = そのデバイス完了直後、次デバイスとの間の機構部
- **副作用対応 2 点**:
  - s2idle site の user 10/11/12 (prepare_late done / restore_early entry / s2idle_wake entry) を **≤9 へ付替え** (10→7, 11→8, 12→9。file:line hash が主判別子なので user 重複は可)
  - `generate_pm_trace()` で site 書込みの user を **9 に clamp** (`if (user > 9) user = 9`) — TRACE_SUSPEND(error) の負値 error が unsigned 変換でマーカー域 (例: -1→15) を偽装するのを防ぐ
- 容量検算: 最大 val = 15 + 16×396 = 6351 < 8064 ✓ (encoding 本体・year=2027 署名・min/sec=0 は dpmwd3 のまま)

## 変更ファイル (src/linux-6.12.y、HEAD 7c86c3994 の上に 1 commit)

1. **`drivers/base/power/trace.c`**:
   - `generate_pm_trace_dev(struct device *dev, unsigned int marker)` 新設 (marker 10-15, file=dev_hash%397 で `set_magic_time`)、EXPORT
   - `generate_pm_trace()` に user clamp (≤9) 追加
   - `late_resume_init()`: user 10-15 なら marker 意味を pr_info + dpm_list walk で `dev_info(dev, "hash matches")` 列挙 (旧 show_dev_hash 復活、mod 397)。user ≤9 なら従来 `show_file_hash`
   - `show_trace_dev_match()` 復活 (marker 時のみ一致列挙) — `/sys/power/pm_trace_dev_match` が再び使える
2. **`include/linux/pm-trace.h`**: `TRACE_RESUME_DEVICE(dev, marker)` マクロ追加 (pm_trace_enabled ガード、!CONFIG_PM_TRACE では no-op)
3. **`drivers/base/power/main.c`**: 上記 6 箇所の置換 (suspend 側 1228-1292/1403-1461/1613-1728 は**無変更** — dpmwd3 と比較可能性を保つ)
4. **`drivers/acpi/x86/s2idle.c` / `drivers/acpi/sleep.c`**: TRACE user 10→7, 11→8, 12→9 の 3 箇所付替え

ビルド設定: `CONFIG_LOCALVERSION="-dpmwd4"` (変更後 `rm include/config/auto.conf && make olddefconfig`)、`make -j12 LOCALVERSION= bindeb-pkg` (~35 分)。手順は 182811 レポートの一次ソースどおり。

## 手順

### Phase P: パッチ・照合資材 (開発機、~30 分)

1. サンドボックス経路確保 (ユーザに `/sandbox` 切替を依頼、または allowedDomains)
2. パッチ作成・commit (上記 4 ファイル)
3. **hashcalc.py 更新 + 衝突チェック**: 残存 site の hash 全計算・衝突ゼロ確認、新 cheatsheet 生成。**main.c の 6 箇所置換で行番号がずれ、suspend 側 site (1229/1292/1404/1461/1614/1728) の hash も変わる**ため、cheatsheet は全面再生成が必須
4. **decode.py 更新**: marker (user 10-15) 対応 — 実機のデバイス名スナップショットとの hash 照合機能を追加

### Phase B: ビルド・デプロイ (~50 分)

1. ビルド → deb を scp → `dpkg -i` (dkms wl 自動ビルド確認)
2. 実機 /boot 空き確認 (カーネル 5 本目。逼迫時は dpmwd1 の削除をユーザに提案)
3. `grub-reboot` ワンショット (**grubenv 変更後 sync 必須** — 182811 の教訓) → 再起動 → ゲート (a) 起動 10 項目
4. 問題なければ saved default を dpmwd4 へ (dpmwd3/2/1/stock 残置 = 多段ロールバック可)
5. **デバイス名スナップショット取得**: dpm 対象デバイス名一覧を実機から採取し `/var/log/h4-probe/` と開発機に保存 (offline decode の冗長化。boot 時 kernel 自己 decode が主、これは backup)

### Phase G: 検証ゲート (C-4 と同型、~30 分 + 一晩 soak は任意)

**注意: pm_trace は RTC を上書きするため rtcwake との併用は構造的に不可。ゲート・arm とも wake は物理操作 (キー/lid) のみで行う (C-4 と同じ)。**

- **(t1) encode 較正**: `pm_test=devices` + `pm_trace=1` で 1 cycle → `hwclock -r --utc` の生値を decode.py + デバイス名スナップショットで照合。**期待値 = post-main marker (user=15) + dev hash が実デバイスに一致** (pm_test=devices の resume は全デバイス完走するため最終書込みは必ず post-main。どのデバイスかは async のため非決定でよい。C-3 で site 1001 が成功 cycle 最終値だった事実と同型)。kernel 自己 decode は boot 時にしか走らないため t1 では確認しない (t2 の役割)。照合後 RTC/時刻復旧
- **(t2) boot 越え decode**: t1 の値が warm reboot を生存し、**boot 時の kernel 自己 decode** が marker 意味 + デバイス実名 (`hash matches`) を journal に出すこと
- **(t3) 合成 hang**: kbd/ff_pwr_btn/LNXPWRBN の wake を runtime 無効化 → suspend → 強制電源断 → decode が `3:332 → suspend.c:152` (s2idle_enter 直前、**dpmwd4 でも不変の site**) になること — 電源断経路の実弾検証
- **(t4) noirq/early マーカー (10-13) の実地確認は C-5 arm の smoke cycle に統合**: pm_test=devices は main phase しか通らず、t3 は resume 前に電源断するため、マーカー 10-13 は実 s2idle cycle でのみ発火する。実 cycle の wake は物理キー入力が必要 → ユーザ操作フェーズ冒頭の smoke cycle で「成功 cycle の最終 RTC 値 = marker 15 + 実デバイス照合」を確認してから hang-arm に進む (これが全 phase マーカーの通し検証を兼ねる)
- 任意 (時間があれば): pm_trace=1 のまま一晩実 s2idle → 正常 resume 確認 (C-4 の t4 相当)

### Phase C-5: hang-arm 再演 (ユーザ物理操作フェーズ)

**ゲート通過時点でユーザに物理操作 (iPad テザリング・lid close・強制電源断・WiFi 復旧) に入れるか確認**。入れなければここで区切り、資材残置して次セッションへ。

1. arm: 022842 の手順 + `pm_trace=1` (sysctl/NM autoconnect off/watchers/smoke。**罠: cycle-watcher は smoke を cycle 1 に計上**)。**smoke cycle でゲート t4 を実施** (成功 cycle の最終 RTC 値 = marker 15 + 実デバイス照合 → マーカー 10-15 全 phase の通し検証)
2. wl loaded + `nmcli radio wifi off` + BT-PAN + VPN → lid close cycle 反復
3. hang 時: **≥5 分待機** (watchdog 60s/hung_task 120s の判定窓確保) → 強制電源断 → 電源投入 → WiFi 復旧 (実機コンソールで `nmcli radio wifi on && nmcli con up OpenWrt`)
4. decode: `journalctl -b -k | grep -E "RTC time|Magic|hash matches|no trace data|trace data valid"` → marker + デバイス実名。60 分超放置の hour 汚染は decode.py の -1h 補正
5. **hang の PRE 帰属は unpaired PRE で同定** (`ls -t` 最新は誤帰属の罠、C-4 で実証済)。BT_PAN_VALID (wl_loaded + xfrm SA) を毎回確認
6. 目標: **デバイス実名付き decode を 2 回以上** (1 回でも前進だが、pre/post・phase の再現性を見たい)
7. 統計は「dpmwd4 + pm_trace=1 摂動 arm」として別 pool 記録 (歴史 pool 7.1% と合算しない)

### Phase R: テアダウン・レポート

1. 全ノブ平常化 (pm_trace=0, panic 系 sysctl 0, NM/radio/RTC 復旧 = NTP + `hwclock --systohc`)
2. 証跡恒久化 (/var/log/h4-probe、journal 抜粋、decode 証跡)
3. レポート作成 (`report/` 規約どおり、タイムスタンプは `TZ=Asia/Tokyo date`)。添付: dpmwd4 パッチ / 新 cheatsheet / 更新 decode.py / decode 証跡 / **本プランファイルのコピー** (`report/attachment/<レポート名>/plan.md`)
4. メモリ (s2idle-btvpn-hang-mechanism-ladder) に C-5 結果を追記

## 検証方法 (成功判定)

- ゲート t1-t3 全通過 (+ C-5 smoke での t4) = 計測系がデバイス実名を電源断越しに取得できることの実弾証明
- hang 再現時に `Magic <10-15>:<devhash>` が decode され、dpm_list 照合で候補デバイス名が列挙されること
- 副次: 停止 marker が pre か post か、phase が noirq/early/main のどれかで、C-4 の「機構部停止 vs callback 内停止」の判別が進むこと

## リスク・注意

- **mod 397 のデバイス名衝突**: ~1000 デバイスで 1 hash に平均 2-3 名が衝突しうる → 全一致列挙 + 「noirq/early callback を持つか」で絞る (実機の callback 保有デバイスは限られる)
- async resume のため「最終書込みデバイス = ハング原因デバイス」とは限らない (全スレッド停止時点の最終活動点)。解釈は watchdog 沈黙 (callback 60s 未満) と組み合わせて行う
- pm_trace=1 摂動下の hang 率 ~44% (C-4) は再現に有利だが、機序同一性の留保は維持
- **resume 側の error 値チャネルは marker 置換で消える** (現 TRACE_RESUME(error))。resume エラーは非 hang 時なら journal の `pm_dev_err` で見えるため許容。suspend 側の error チャネルは無変更で残る
- **pm_trace=1 中は rtcwake 使用禁止** (RTC を取り合う)。wake は物理操作のみ
- ロールバック: dpmwd3 が saved default 候補として残るため `grub-reboot`/`grub-set-default` で即戻せる
