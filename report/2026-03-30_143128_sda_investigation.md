# sda ディスク調査レポート

- 調査日: 2026-03-30
- 対象ホスト: openwrt-rescue.lan (OpenWrt SNAPSHOT r33681-efb282f97f)
- 調査方法: SSH経由でdmesg、sysfs、dd、smartctl等を使用

## デバイス情報

| 項目 | 値 |
|------|-----|
| モデル | APPLE SSD SM0128G |
| シリアル番号 | S29BNYDG874781 |
| LU WWN Device Id | 5 002538 900000000 |
| ファームウェア | BXW1SA0Q |
| 容量 | 121 GB (113 GiB) / 236,978,176 セクタ |
| インターフェース | SATA 3.0, 6.0 Gb/s (current: 6.0 Gb/s) |
| セクタサイズ | 512B 論理 / 4096B 物理 |
| ATA規格 | ATA8-ACS T13/1699-D revision 4c |
| AHCIコントローラ | ahci 0000:04:00.0, AHCI vers 0001.0300, 32 command slots |
| TRIM | Available |
| ATA Security | Disabled, frozen [SEC2] |

### パーティション構成

| デバイス | 開始セクタ | 終了セクタ | サイズ | タイプ |
|----------|-----------|-----------|--------|--------|
| /dev/sda1 | 40 | 409,639 | 200M | EFI System |
| /dev/sda2 | 409,640 | 236,978,135 | 112.8G | Apple APFS |

GPT Disk ID: D28E89CB-A329-460D-9738-0FCAF53DE76D

## 発見された問題

### 1. メディアエラー（最も深刻）

ddによる読み込みテスト中に **セクタ592（論理ブロック74）で読み取り不能エラー** が発生。

```
[  503.084557] ata1.00: exception Emask 0x0 SAct 0x0 SErr 0x0 action 0x0
[  503.086162] ata1.00: irq_stat 0x40000000
[  503.087621] ata1.00: failed command: unknown
[  503.089072] ata1.00: cmd c8/00:08:50:02:00/00:00:00:00:00/e0 tag 17 dma 4096 in
[  503.089072]          res 51/40:00:50:02:00/00:00:00:00:00/00 Emask 0x9 (media error)
[  503.181543] sd 0:0:0:0: [sda] tag#17 UNKNOWN(0x2003) Result: hostbyte=0x00 driverbyte=DRIVER_OK cmd_age=92s
[  503.183234] sd 0:0:0:0: [sda] tag#17 Sense Key : 0x3 [current]
[  503.184728] sd 0:0:0:0: [sda] tag#17 ASC=0x11 ASCQ=0x4
[  503.186145] sd 0:0:0:0: [sda] tag#17 CDB: opcode=0x28 28 00 00 00 02 50 00 00 08 00
[  503.187679] I/O error, dev sda, sector 592 op 0x0:(READ) flags 0x0 phys_seg 1 prio class 2
[  503.189253] Buffer I/O error on dev sda, logical block 74, async page read
```

- **Sense Key 0x3** = Medium Error（メディアの物理的な問題）
- **ASC=0x11 ASCQ=0x4** = Unrecovered Read Error - Auto Reallocate Failed
  - SSDが不良セクタの自動再割り当て（リアロケーション）を試みたが**失敗**
  - 予備領域が枯渇しているか、再割り当て機構自体が故障している可能性が高い
- エラー位置（セクタ592）はEFIパーティション領域（セクタ40〜409,639）内にある

### 2. コマンドタイムアウトとリンクリセット

```
[  502.494252] ata1.00: NCQ disabled due to excessive errors
[  502.495809] ata1.00: exception Emask 0x0 SAct 0x20000 SErr 0x0 action 0x6 frozen
[  502.497434] ata1.00: failed command: unknown
[  502.498895] ata1.00: cmd 60/08:88:50:02:00/00:00:00:00:00/40 tag 17 ncq dma 4096 in
[  502.498895]          res 40/00:00:00:00:00/00:00:00:00:00/00 Emask 0x4 (timeout)
[  502.502126] ata1: hard resetting link
```

- NCQ（Native Command Queuing）コマンドがタイムアウト
- SATAリンクのハードリセットが必要になった
- リセット後にNCQが自動無効化された

### 3. NCQ自動無効化

```
ata1.00: NCQ disabled due to excessive errors
```

エラーが多すぎてNCQが自動で無効化。NCQ無効化後もDMAモードでメディアエラーが発生。

### 4. 起動時からのATA機能異常

起動時（カーネル初期化時）から以下のエラーが報告されている:

```
[    0.878543] ata1.00: LPM support broken, forcing max_power
[    0.900861] ata1.00: failed to read native max address (err_mask=0x1)
[    0.902112] ata1.00: HPA support seems broken, skipping HPA handling
[    0.925739] ata1.00: failed to enable AA (error_mask=0x1)
[    0.973176] ata1.00: configured for UDMA/133 (device error ignored)
```

| エラー | 意味 |
|--------|------|
| LPM support broken | リンク電源管理が壊れている |
| failed to read native max address | HPA (Host Protected Area) サポートが壊れている |
| failed to enable AA | Auto Activate (NCQ関連) 機能が有効化できない |
| device error ignored | デバイスエラーを無視して強制的に設定 |

これらは起動時から既にSSDのファームウェアまたはハードウェアに問題があることを示している。

### 5. SMART情報の取得不能

smartctl 7.5 による調査を実施。SMARTサブシステム自体が応答しない深刻な状態。

```
root@openwrt-rescue:~# smartctl -s on /dev/sda
SMART Enable failed: scsi error aborted command

root@openwrt-rescue:~# smartctl -a -T permissive /dev/sda
SMART support is: Available - device has SMART capability.
SMART support is: Disabled
Read SMART Data failed: scsi error aborted command
SMART Status command failed: scsi error aborted command
SMART overall-health self-assessment test result: UNKNOWN!
SMART Status, Attributes and Thresholds cannot be read.
Read SMART Log Directory failed: scsi error aborted command
Read SMART Error Log failed: scsi error aborted command
Read SMART Self-test Log failed: scsi error aborted command

root@openwrt-rescue:~# smartctl -x -T permissive /dev/sda
ATA_READ_LOG_EXT (addr=0x00:0x00, page=0, n=1) failed: scsi error aborted command
Read GP Log Directory failed
SMART Extended Comprehensive Error Log (GP Log 0x03) not supported
SMART Extended Self-test Log (GP Log 0x07) not supported
SCT Commands not supported
Device Statistics (GP/SMART Log 0x04) not supported
Pending Defects log (GP Log 0x0c) not supported
ATA_READ_LOG_EXT (addr=0x11:0x00, page=0, n=1) failed: scsi error aborted command
Read SATA Phy Event Counters failed
```

| 項目 | 状態 |
|------|------|
| SMART機能 | Available だが Disabled |
| SMART有効化 | **失敗** (scsi error aborted command) |
| SMARTステータス読み取り | **失敗** |
| SMART属性読み取り | **失敗** |
| SMARTエラーログ | **失敗** |
| SMARTセルフテストログ | **失敗** |
| GP Log Directory | **失敗** |
| SCT Commands | Not supported |
| SATA Phy Event Counters | **失敗** |
| ヘルス自己診断結果 | **UNKNOWN** |

SSD自体がSMARTコマンドを受け付けない（全て `scsi error aborted command` で失敗）ため、SMART属性（ウェアレベリング残量、再割り当て済みセクタ数、総書き込み量等）は一切取得できなかった。これはSSDのファームウェアまたはコントローラが正常に動作していないことを示す。

### 6. I/Oエラーカウンタの推移

ddで約4MBの読み込みテスト（`dd if=/dev/sda of=/dev/null bs=4096 count=1000`）を実施。ddは1ブロックも読めずにI/O待ちでハングした。

| カウンタ | テスト前 | テスト後 | 増加分 |
|----------|----------|----------|--------|
| ioerr_cnt（I/Oエラー数） | 0x4 (4) | 0xa (10) | +6 |
| iodone_cnt（完了I/O数） | 0x3e (62) | 0xb9 (185) | +123 |
| iorequest_cnt（I/O要求数） | 0x3e (62) | 0xb9 (185) | +123 |
| iotmo_cnt（I/Oタイムアウト数） | 0x0 (0) | 0x6 (6) | +6 |

- わずかなテストで **6回のI/Oエラー** と **6回のタイムアウト** が発生
- テスト前から既に4回のI/Oエラーが記録されていた（fdiskによるパーティション読み込み時等）

## 診断結論

**SSDはハードウェアレベルで故障しています。**

1. 不良セクタが存在し、自動再割り当て（リアロケーション）が失敗している
   - 予備領域の枯渇またはリアロケーション機構自体の故障
2. エラーがセクタ592（EFIパーティション領域内）で発生しており、ブートに必要な領域に不良がある
3. 複数のATA機能（LPM, HPA, AA）が正常に動作しない
4. I/Oタイムアウトとリンクリセットが繰り返し発生し、実質的にデータ読み取りが不可能
5. **SMARTサブシステムが完全に応答しない** — SMART有効化もデータ読み取りも全て失敗しており、SSDのファームウェアまたはコントローラレベルの故障が示唆される

## 推奨対応

1. **SSDの交換が必要** — 修理・再利用は推奨しない
2. **データ救出** — 必要であればddrescue等で読み取り可能なセクタからの救出を試みる（ただし状態が悪いため時間がかかり、一部は回復不能の可能性が高い）

## 備考

- smartctl 7.5（smartmontools r5714）を使用したが、SSDがSMARTコマンドを受け付けないため属性データは取得不能であった
- dmesg・sysfs・dd・smartctlの結果を総合してハードウェア故障と判断
- sdb（USB: General UDisk）にもGPTエラー（`GPT: Use GNU Parted to correct GPT errors.`）が報告されているが、今回の調査対象外
