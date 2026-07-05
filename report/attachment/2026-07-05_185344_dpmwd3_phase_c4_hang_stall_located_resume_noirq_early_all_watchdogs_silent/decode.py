#!/usr/bin/env python3
"""dpmwd3 firmware-safe pm_trace decoder.

Usage: decode.py "2027-12-23 15:04:22"   (hwclock -r --utc の生値、または journal の RTC 行)

kernel 側 (dpmwd3) と同一ロジック:
  year==2027 が署名。val = mon0 + (mday-1)*12 + hour*336; user=val%16; file=val//16 (mod 397)
min:sec は最終 TRACE 書き込みからの経過時間 (60 分超は hour 汚染 = 判定不能)。
"""
import sys, re

FILEHASH = 397
USERHASH = 16

def sdbm(seed, s, mod):
    h = seed
    for c in s.encode():
        h = ((h << 16) + (h << 6) - h + c) & 0xFFFFFFFF
    return h % mod

# (file, line, user, label) — dpmwd3 commit 7c86c3994 の全 .tracedata site
SITES = [
    ("kernel/power/suspend.c", 130, 2,  "s2idle_loop entry"),
    ("kernel/power/suspend.c", 152, 3,  "before s2idle_enter -> asleep in idle (suspend 完遂, wake 喪失側)"),
    ("kernel/power/suspend.c", 154, 4,  "after s2idle_enter returned"),
    ("kernel/power/suspend.c", 157, 5,  "s2idle_loop exited (wake accepted)"),
    ("kernel/power/suspend.c", 430, 0,  "before platform_suspend_prepare_noirq"),
    ("kernel/power/suspend.c", 434, 1,  "after platform_suspend_prepare_noirq ok"),
    ("kernel/power/suspend.c", 477, 6,  "Platform_wake: before platform_resume_noirq"),
    ("drivers/acpi/x86/s2idle.c", 550, 8,  "acpi_s2idle_prepare_late entry"),
    ("drivers/acpi/x86/s2idle.c", 568, 9,  "prepare_late: before LPS0 entry DSM (LPS0 無しでは発火せず)"),
    ("drivers/acpi/x86/s2idle.c", 592, 10, "prepare_late done (LPS0 無しでは発火せず)"),
    ("drivers/acpi/x86/s2idle.c", 613, 11, "acpi_s2idle_restore_early entry"),
    ("drivers/acpi/sleep.c",      761, 12, "acpi_s2idle_wake entry (wake-check 反復)"),
    ("drivers/base/power/main.c", 627, 0,  "device_resume_noirq start"),
    ("drivers/base/power/main.c", 700, None, "device_resume_noirq end (user=error)"),
    ("drivers/base/power/main.c", 792, 0,  "device_resume_early start"),
    ("drivers/base/power/main.c", 836, None, "device_resume_early end (user=error)"),
    ("drivers/base/power/main.c", 929, 0,  "device_resume start"),
    ("drivers/base/power/main.c", 1001, None, "device_resume end (user=error) [成功 cycle の最終値]"),
    ("drivers/base/power/main.c", 1229, 0,  "device_suspend_noirq start"),
    ("drivers/base/power/main.c", 1292, None, "device_suspend_noirq end (user=error)"),
    ("drivers/base/power/main.c", 1404, 0,  "device_suspend_late start"),
    ("drivers/base/power/main.c", 1461, None, "device_suspend_late end (user=error)"),
    ("drivers/base/power/main.c", 1614, 0,  "device_suspend start"),
    ("drivers/base/power/main.c", 1728, None, "device_suspend end (user=error)"),
]

def decode(y, mon, mday, hour, minute, sec):
    if y != 2027:
        print(f"year={y} != 2027 → trace data 無し (firmware reset か実時刻)")
        return
    val = (mon - 1) + (mday - 1) * 12 + hour * 12 * 28
    user, fh = val % USERHASH, val // USERHASH
    print(f"Magic {user}:{fh}  (経過 {minute:02d}:{sec:02d}; 60 分超なら hour 汚染に注意)")
    hits = [(f, l, u, lab) for f, l, u, lab in SITES if sdbm(l, f, FILEHASH) == fh]
    if not hits:
        print(f"  filehash {fh} は既知 site に不一致 (hour 汚染? 経過時間で -1h 補正して再試行を)")
        val2 = val - 12 * 28
        if val2 >= 0:
            u2, f2 = val2 % USERHASH, val2 // USERHASH
            print(f"  [-1h 補正] Magic {u2}:{f2}:")
            for f, l, u, lab in SITES:
                if sdbm(l, f, FILEHASH) == f2:
                    print(f"    {f}:{l} (user={u}) {lab}" + ("  ← user 一致" if u == u2 else ""))
        return
    for f, l, u, lab in hits:
        mark = "  ← user コード一致 (確定)" if (u == user or (u is None and user == 0)) else ""
        print(f"  {f}:{l} (期待 user={u if u is not None else 'err(通常0)'})  {lab}{mark}")

if __name__ == "__main__":
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", " ".join(sys.argv[1:]))
    if not m:
        sys.exit("usage: decode.py 'YYYY-MM-DD HH:MM:SS' (RTC/UTC)")
    decode(*(int(g) for g in m.groups()))
