# ハングを回避しつつ ACPI S3 (deep) sleep を復活できるか — 検証実験プラン

## Context（なぜ今これをやるのか）

MacBook Air 11" (Early 2015) / Debian 13 は、2026-05-31 に「復帰 hang」を理由に
S3 deep → s2idle へ恒久切替した。だが切替を正当化した根拠（「S3 firmware 由来の
hang」説）は、その後の調査で**当時には存在しなかった切り分け方法論を一度も S3 に
適用しないまま**下されたものだった。具体的には:

- **S3 は RTC ストレステストにかけられたことが一度もない。** s2idle では RTC 68/68
  clean が取れ、「真の resume hang」と「wake 配送失敗」を分離できた
  （[2026-06-01](../../../projects/macbookair11-debian/report/2026-06-01_034724_s2idle_hang_rtcwake_discrimination.md)）。
  S3 firmware の suspend/resume が本当に固着するのかは、未測定のまま放棄された。
- **過去の S3 hang 時、システムが生存していたか確認していない。** 当時は即座に電源
  長押しで強制 off しており、「画面が黒いだけでカーネルは生きている（= i915/display
  resume 失敗）」という第3の失敗モードを一度も切り分けていない。総合レポート §8 自身が
  「S3 時代の hang の一部は真の hang でなく wake 配送失敗だった可能性」を認めている
  （[2026-06-18](../../../projects/macbookair11-debian/report/2026-06-18_142303_why_not_s3_deep_sleep.md)）。

**狙い**: 主目的は**待機電力の低減**。s2idle は実測 0.70 W だが、S3 は RAM セルフ
リフレッシュのみで桁違いに低い見込み。S3 を復活できれば夜間バッテリ消費を大幅に
削減できる（lid wake 復活は副次的なボーナス）。

**framing（重要）**: 本プランは「S3 hang は良性だったと確認する」ものではない。
実機で一度も判定されなかった失敗モードを **falsifiable に判定する**もので、結論は
「復活可」も「棄却（s2idle 据え置き）」も等しくあり得る。むしろ電源ボタンの非対称性
（過去 S3 hang は無反応 / s2idle 配送失敗は短押し 3/3 復帰）は「S3 hang は s2idle の
それより重い別現象」を示唆する**反証**であり、A で真の firmware hang が出れば即座に
棄却する。

## 切り分けるべき失敗モード（3 分法）

| モード | 症状 | discriminator |
|---|---|---|
| **(1) 真の firmware hang** | 寝たら RTC でも戻らない・ssh 不通 | RTC ストレス(A)で ENTER 止まり |
| **(2) suspend/resume コード hang** | カーネル経路で固着、ssh 不通 | A で ENTER 止まり（(1)と同挙動／本件では区別不要） |
| **(3) i915/display resume 失敗** | システム生存・画面だけ黒・無反応に見える | **RTC で戻る + ssh 通る + 画面黒**／dmesg に i915 resume エラー |

過去の放棄判断が見落としたのは (3)。元の DC5/DC6 シグネチャ（「DRM 警告直後」「画面
真っ暗」）は (3) と完全に整合する。**ssh 到達性**がこのプロジェクト最大の付加価値となる
discriminator: 各サイクルで「RTC で戻るか」「ssh が通るか」「dmesg に i915 resume
エラーがあるか」を記録する。

## 環境・前提

- 操作対象は ssh 接続先の実機 `macbookair2015.lan`（全コマンド ssh 越し）。
- カーネル `6.12.90+deb13-amd64`、`/sys/power/mem_sleep` = `[s2idle] deep`（deep 選択可）。
- **物理立ち会い必須**（lid 開閉・電源ボタン押下・hang 時の強制 off）。ユーザ合意済み。
- **safety net 維持**: バッテリ連動ハイバネ（S4）と suspend-then-hibernate は据え置き。
  真の firmware hang が出れば fs/データのリスクを伴う強制 off になる点もユーザ合意済み。
- **confound の明示**: S3 時代の cmdline は `i915.enable_dc=0` / `applespi` blacklist /
  `pcie_aspm=off` を含んでいたが、s2idle 切替時に全て除去した。よって今回の S3 再試験は
  **当時と異なるクリーンなベースライン**（DC states 有効）で行う。まず素のベースラインで
  測り、(3) display 失敗が出たら remediation 候補（後述）を当てる。

## 再利用する既存資材（実機に残置済み）

- `/usr/local/sbin/rtcwake-stress.sh` — `rtcwake -m mem -s SECS` を N サイクル、各サイクル
  前後を **sync 付きでディスクログ**に追記（hang→強制再起動を跨いでも「どのサイクルで
  ENTER 止まりか」が残る）。`/sys/power/state` 直書きなので **deep でもそのまま S3 サイクル
  になる**。ladder A でそのまま使う。
- `/usr/local/sbin/pwrbtn-wake-test.sh` — `rtcwake` + elapsed ログ。RTC をフォールバックに
  しつつ lid/電源ボタンの早期 wake を elapsed で判定。ladder B で使う。
- `/usr/local/sbin/check-suspend-resume.sh` — boot 単位で `PM: suspend entry/exit` を数え
  `diff>0` を UNGRACEFUL 判定。各 ladder の cross-check に使う。
- `systemd-run --collect --unit=...` のデタッチ常駐パターン（ssh 切断後も継続）。

## 実験ラダー

### Ladder A — firmware resume の隔離試験（ほぼ無人・ssh 駆動・低リスク先行）

s2idle の 68/68 試験の **S3 版**。RTC は LID0 を一切使わずカーネル RTC で起こすので、
wake 配送経路を切り離して **firmware の suspend/resume そのもの**を試せる。

手順:
1. プリフライト（read-only）: AC online、lid open、`cat /sys/power/mem_sleep`、boot_id。
2. **runtime で deep へ切替（可逆・再起動不要）**: `echo deep | sudo tee /sys/power/mem_sleep`
   → `[deep] s2idle` を確認。cmdline は `mem_sleep_default=s2idle` のままなので、**再起動
   すれば必ず安全な既定（s2idle）に戻る**。
3. `rtcwake-stress.sh` を deep 下で実行（s2idle と対比できるよう同条件）:
   - 第1バッチ: 60 cycle × `-s 90`、第2バッチ: 6 cycle × `-s 1800`。
   - `systemd-run --collect --unit=s3-rtcwake-stress` でデタッチ常駐。
4. **per-cycle 計測の追加**（既存スクリプトに無い分）: 復帰直後に `dmesg` の
   `i915|drm|ACPI|PM: resume` 行をログに退避するワンライナーを stress スクリプトの EXIT
   行直後に追記（または別途 `journalctl -k` を後で照合）。dev 機側からは各バッチ後に ssh
   到達性を確認。
5. 判定:
   - **全 cycle EXIT・ssh OK・i915 resume エラー無し** → S3 firmware suspend/resume は
     現行ベースラインで健全。**→ Ladder B へ**。
   - **どこかで ENTER 止まり（RTC でも戻らない・バッチ後 ssh 不通）** → **モード(1)/(2) 真の
     hang**。これが歴史的な killer。**→ S3 棄却を強く示唆**。remediation（後述）を 1 つだけ
     試すか、即 s2idle へ revert。
   - **全 cycle EXIT するが dmesg に i915/drm resume エラーが残る** → モード(3) display/device
     resume 失敗が RTC 経路でも顔を出している → remediation（`i915.enable_dc=0` 等）の候補。
     無人 A では画面状態を観測できず、display 失敗でもループは EXIT を記録して回り続けるため、
     **A での検出は dmesg 経由**とし、画面黒/ssh 通る の最終確認は立ち会いの Ladder B に委譲する。

### Ladder B — S3 lid wake & 復帰判定（本命の payoff・立ち会い・RTC フォールバック必須）

deep のまま、lid 開閉と電源ボタンで起きるかを試す。S3 は historically lid wake が効いて
いた（= s2idle に対する唯一の実利）。**必ず RTC フォールバックを張る**ので、lid/電源が
駄目でも N 秒で復帰し強制 off は不要。

手順:
1. deep 維持。`pwrbtn-wake-test.sh` 系（`rtcwake -m mem -s 180`）で S3 進入。
2. 画面が消えてから lid を閉→開（または電源ボタン短押し）。`elapsed ≪ 180s` なら早期
   wake 成功、`≈181s` なら RTC フォールバック復帰（= その wake 源は効かなかった）。
3. **復帰プロトコルで失敗モードを分類**（advisor 指摘の ssh 到達性が鍵）:
   - lid/電源で起き、画面も復帰 → 正常（S3 lid wake 成立）。
   - 無反応に見える → **(a)** dev 機から ssh を試す。**ssh 通る + 画面黒 → モード(3)
     display resume 失敗**（hang ではない）。**(b)** ssh 不通 → RTC フォールバックを待つ。
     RTC で戻る → wake 配送失敗（カーネル生存）。RTC でも戻らない → **モード(1) 真の hang**。
4. 実運用経路も確認: `HandleLidSwitch` を一時的に `suspend`（STH の hibernate タイマ
   confound を排除）にして lid close→open の素の S3 サスペンド/レジュームを見る。検証後
   現行の `suspend-then-hibernate` に戻す。

### Ladder C — soak & 待機電力測定（主目的の成否判定）

A/B をパスしたら deep を日常運用に投入し、**主目的＝待機電力**を実測しつつ、復帰イベントを
**分類しながら**カウントする（元の放棄に欠けていたのがこの分類）。

1. **待機電力測定（主目的の成功指標）**: AC を外し、`rtcwake -m mem -s 3600` 前後で
   `/sys/class/power_supply/BAT0/energy_now`（µWh）の差分から W を算出。
   `W = ΔEnergy[Wh] / Δt[h]`。s2idle 0.70 W と比較。
   - **S3 が 0.70 W より有意に低い**（見込み 0.1–0.2 W 台）→ 主目的成立。
   - 改善が乏しければ hang リスクを負う価値が無い → **S3 棄却**。
2. **soak（1–2 週間）**: deep を runtime で維持（永続化はまだしない）。復帰イベントを
   「lid/電源で復帰」「ssh 通る・画面黒(=モード3)」「RTC/hibernate で救済」「強制 off=真の
   hang」に分類して記録。元の hang 率 0.7–0.8 件/週がベースライン。
3. 永続化判断: soak が良好なら `GRUB_CMDLINE_LINUX_DEFAULT` の `mem_sleep_default=s2idle`
   を `=deep` に変更（`update-grub`）。これは soak 合格後にのみ行う最終ステップ。

## remediation 候補（display/firmware 問題が出た場合のみ）

優先順位つき。一度に 1 変数だけ変える:
1. **`i915.enable_dc=0`** — モード(3) display resume 失敗向け。S3 時代に使っていたが
   s2idle 切替時に除去済み。display 失敗が出たら最初に戻す候補。
2. **`acpi_osi=` 系**（例 `acpi_osi=Darwin` / `acpi_osi=!` など）— 唯一温存されたまま
   一度も試されていない候補（Phase B 候補 4）。Apple firmware の SMI/sleep 経路を変える。
   真の firmware hang（モード1）が出た場合の最後の砦。
3. （除外）`i915.enable_psr=0` — 内蔵パネルが PSR 非対応のため無効。

## 安全・可逆性

- 実験中の deep 切替はすべて **runtime（`echo deep`）** で行い、cmdline は s2idle のまま。
  **どの段階でも `echo s2idle | sudo tee /sys/power/mem_sleep` か単純な再起動で既定に戻る。**
- Ladder A は RTC が主 wake、Ladder B は lid/電源を主としつつ **RTC フォールバック**で時間
  上限を区切る（lid/電源が駄目でも自動復帰）。いずれも時間上限が保証され、強制 off は
  「RTC でも戻らない真の hang」時のみに限定される。
- 真の firmware hang のみが強制 off を要する。`rtcwake-stress.sh` の sync ログで hang
  サイクルは強制再起動後も特定可能。
- バッテリ連動ハイバネ・STH は据え置き（soak 中の救済層として機能）。
- logind の一時無害化（`HandlePowerKey=ignore` / `HandleLidSwitch` 変更）は drop-in で行い
  検証後に必ず撤去（[2026-06-03](../../../projects/macbookair11-debian/report/2026-06-03_123439_pwrbtn_wake_premise_verification.md) と同方式）。

## 成功条件（decision matrix）

| 結果 | 判定 |
|---|---|
| A clean + B で lid/電源 wake 成立 + C で待機電力 ≪ 0.70 W かつ真の hang 0 | **S3 復活（永続化）** |
| A で真の firmware hang（モード1）再現 | **S3 棄却**（s2idle 据え置き）。remediation 2 を一度試す余地のみ |
| A clean だが C で待機電力が s2idle と大差なし | **S3 棄却**（主目的不成立、リスクに見合わない） |
| display 失敗（モード3）が remediation 1 で解消 | 条件付き復活（`i915.enable_dc=0` 付き）。待機電力増を再評価 |

## Verification（検証手順と依存関係）

- **依存関係（重要）**: A の RTC 試験が clean でも、それは firmware resume が健全と言う
  だけで、過去 hang がモード(3) display だった線は残る。**A 単独では「復活可」と結論
  できない。** B で lid/display 復帰を、C で待機電力と soak を通して初めて判定する。
- 各 ladder の cross-check は `check-suspend-resume.sh`（boot 単位の suspend/resume 差分）と
  `boot_id` 不変（再起動・強制 off ゼロ）で行う。
- 待機電力は BAT0 `energy_now` の前後差分で算出し s2idle 0.70 W と数値比較。
- ssh 到達性チェックを各 hang 様事象で必ず実施（モード3 の検出が本実験の核心）。

## 実験後の成果物（CLAUDE.md レポートルール）

実験実施後、`report/yyyy-mm-dd_hhmmss_s3_revival_evaluation.md` を作成する（タイムスタンプは
`TZ=Asia/Tokyo date +%Y-%m-%d_%H%M%S`）。前提・目的・環境情報・再現方法・結果・decision を
記載し、本プランファイルを `report/attachment/<レポート名>/plan.md` に添付してリンクする。
関連レポート（2026-06-01 / 2026-06-03 / 2026-06-18 各種）へのリンクも張る。
