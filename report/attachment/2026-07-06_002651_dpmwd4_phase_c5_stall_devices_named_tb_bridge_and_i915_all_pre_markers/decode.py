#!/usr/bin/env python3
"""dpmwd4 firmware-safe pm_trace decoder (marker-aware).

Usage:
  decode-dpmwd4.py "2027-12-23 15:04:22" [--devlist devices.txt]

RTC 生値 (hwclock -r --utc または journal の RTC 行) を decode する。
kernel 側 (dpmwd4) と同一ロジック:
  year==2027 が署名。val = mon0 + (mday-1)*12 + hour*336; user=val%16; file=val//16
  user 0-9  = site 書込み (file = sdbm(line, path) % 397)
  user 10-15 = デバイスマーカー (file = sdbm(7919, dev_name) % 397)
min:sec は最終 TRACE 書き込みからの経過時間 (60 分超は hour 汚染 → -1h 補正候補を提示)。
--devlist: 実機のデバイス名スナップショット (1 行 1 名) と hash 照合して候補実名を列挙。
"""
import sys, re

FILEHASH = 397
USERHASH = 16
DEVSEED = 7919

def sdbm(seed, s, mod):
    h = seed
    for c in s.encode():
        h = ((h << 16) + (h << 6) - h + c) & 0xFFFFFFFF
    return h % mod

# (file, line, user, label) — dpmwd4 の全 .tracedata site
SITES = [
    ("kernel/power/suspend.c", 130, 2,  "s2idle_loop entry"),
    ("kernel/power/suspend.c", 152, 3,  "before s2idle_enter -> asleep in idle (suspend 完遂)"),
    ("kernel/power/suspend.c", 154, 4,  "after s2idle_enter returned"),
    ("kernel/power/suspend.c", 157, 5,  "s2idle_loop exited (wake accepted)"),
    ("kernel/power/suspend.c", 430, 0,  "before platform_suspend_prepare_noirq"),
    ("kernel/power/suspend.c", 434, 1,  "after platform_suspend_prepare_noirq ok"),
    ("kernel/power/suspend.c", 477, 6,  "Platform_wake: before platform_resume_noirq"),
    ("drivers/acpi/x86/s2idle.c", 550, 8,  "acpi_s2idle_prepare_late entry"),
    ("drivers/acpi/x86/s2idle.c", 568, 9,  "prepare_late: before LPS0 entry DSM (LPS0 無しでは発火せず)"),
    ("drivers/acpi/x86/s2idle.c", 592, 7,  "prepare_late done (LPS0 無しでは発火せず)"),
    ("drivers/acpi/x86/s2idle.c", 613, 8,  "acpi_s2idle_restore_early entry"),
    ("drivers/acpi/sleep.c",      761, 9,  "acpi_s2idle_wake entry (wake-check 反復)"),
    ("drivers/base/power/main.c", 1226, 0,  "device_suspend_noirq start"),
    ("drivers/base/power/main.c", 1289, None, "device_suspend_noirq end (user=error)"),
    ("drivers/base/power/main.c", 1401, 0,  "device_suspend_late start"),
    ("drivers/base/power/main.c", 1458, None, "device_suspend_late end (user=error)"),
    ("drivers/base/power/main.c", 1611, 0,  "device_suspend start"),
    ("drivers/base/power/main.c", 1725, None, "device_suspend end (user=error)"),
]

MARKERS = {
    10: "device_resume_noirq entry (pre: このデバイスの callback/wait が目前)",
    11: "device_resume_noirq exit  (post: このデバイス完了、停止はその後の機構部)",
    12: "device_resume_early entry (pre)",
    13: "device_resume_early exit  (post)",
    14: "device_resume entry       (pre, main phase)",
    15: "device_resume exit        (post, main phase) [成功 cycle の最終値]",
}

def load_devlist(path):
    names = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                names.append(line)
    return names

def show(val, devnames, prefix=""):
    user, fh = val % USERHASH, val // USERHASH
    print(f"{prefix}Magic {user}:{fh}")
    if user >= 10:
        print(f"{prefix}  デバイスマーカー: {MARKERS[user]}")
        if devnames:
            hits = [n for n in devnames if sdbm(DEVSEED, n, FILEHASH) == fh]
            if hits:
                for n in hits:
                    print(f"{prefix}    dev hash 一致候補: {n}")
            else:
                print(f"{prefix}    devlist 内に一致なし (スナップショット不足 or hour 汚染)")
        else:
            print(f"{prefix}    (実名は boot 時 kernel decode の 'hash matches' 行、"
                  f"または --devlist で照合)")
        return True
    hits = [(f, l, u, lab) for f, l, u, lab in SITES if sdbm(l, f, FILEHASH) == fh]
    for f, l, u, lab in hits:
        mark = "  ← user コード一致 (確定)" if (u == user or (u is None and user == 0)) else ""
        print(f"{prefix}  {f}:{l} (期待 user={u if u is not None else 'err(通常0)'})  {lab}{mark}")
    return bool(hits)

def decode(y, mon, mday, hour, minute, sec, devnames):
    if y != 2027:
        print(f"year={y} != 2027 → trace data 無し (firmware reset か実時刻)")
        return
    val = (mon - 1) + (mday - 1) * 12 + hour * 12 * 28
    print(f"(経過 {minute:02d}:{sec:02d}; 60 分超なら hour 汚染に注意)")
    if not show(val, devnames):
        print("  既知 site/marker に不一致 → -1h 補正候補:")
        val2 = val - 12 * 28
        if val2 >= 0:
            show(val2, devnames, prefix="  [-1h] ")

if __name__ == "__main__":
    args = sys.argv[1:]
    devnames = []
    if "--devlist" in args:
        i = args.index("--devlist")
        devnames = load_devlist(args[i + 1])
        del args[i:i + 2]
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", " ".join(args))
    if not m:
        sys.exit("usage: decode-dpmwd4.py 'YYYY-MM-DD HH:MM:SS' [--devlist devices.txt] (RTC/UTC)")
    decode(*(int(g) for g in m.groups()), devnames)
