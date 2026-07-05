FILEHASH = 397
USERHASH = 16

def sdbm(seed, s, mod):
    h = seed
    for c in s.encode():
        h = ((h << 16) + (h << 6) - h + c) & 0xFFFFFFFF
    return h % mod

sites = [
    # (file, line, user, label)
    ("kernel/power/suspend.c", 130, 2,  "s2idle_loop entry"),
    ("kernel/power/suspend.c", 152, 3,  "before s2idle_enter (= asleep/wake-lost if final)"),
    ("kernel/power/suspend.c", 154, 4,  "after s2idle_enter returned"),
    ("kernel/power/suspend.c", 157, 5,  "s2idle_loop exited (wake accepted)"),
    ("kernel/power/suspend.c", 430, 0,  "before platform_suspend_prepare_noirq"),
    ("kernel/power/suspend.c", 434, 1,  "after platform_suspend_prepare_noirq ok"),
    ("kernel/power/suspend.c", 477, 6,  "Platform_wake: before platform_resume_noirq"),
    ("drivers/acpi/x86/s2idle.c", 550, 8,  "acpi_s2idle_prepare_late entry"),
    ("drivers/acpi/x86/s2idle.c", 568, 9,  "prepare_late: before LPS0 entry DSM"),
    ("drivers/acpi/x86/s2idle.c", 592, 10, "prepare_late done"),
    ("drivers/acpi/x86/s2idle.c", 613, 11, "acpi_s2idle_restore_early entry"),
    ("drivers/acpi/sleep.c",      761, 12, "acpi_s2idle_wake entry (wake-check iteration)"),
    ("drivers/base/power/main.c", 627, 0,  "device_resume_noirq start"),
    ("drivers/base/power/main.c", 700, None, "device_resume_noirq end (user=error)"),
    ("drivers/base/power/main.c", 792, 0,  "device_resume_early start"),
    ("drivers/base/power/main.c", 836, None, "device_resume_early end (user=error)"),
    ("drivers/base/power/main.c", 929, 0,  "device_resume start"),
    ("drivers/base/power/main.c", 1001, None, "device_resume end (user=error) [success-cycle final]"),
    ("drivers/base/power/main.c", 1229, 0,  "device_suspend_noirq start"),
    ("drivers/base/power/main.c", 1292, None, "device_suspend_noirq end (user=error)"),
    ("drivers/base/power/main.c", 1404, 0,  "device_suspend_late start"),
    ("drivers/base/power/main.c", 1461, None, "device_suspend_late end (user=error)"),
    ("drivers/base/power/main.c", 1614, 0,  "device_suspend start"),
    ("drivers/base/power/main.c", 1728, None, "device_suspend end (user=error)"),
]

rows = []
seen = {}
collisions = []
for f, line, user, label in sites:
    h = sdbm(line, f, FILEHASH)
    key = h
    if key in seen:
        collisions.append((seen[key], (f, line)))
    else:
        seen[key] = (f, line)
    rows.append((f, line, user, h, label))

print(f"{'file':30s} {'line':>5s} {'user':>4s} {'filehash':>8s}  Magic(user:file)  RTC(UTC mon/day/hour)  label")
for f, line, user, h, label in rows:
    u = user if user is not None else 0
    n = u + USERHASH * h
    mon = n % 12; n2 = n // 12
    mday = n2 % 28 + 1; n3 = n2 // 28
    hour = n3 % 24
    ustr = str(user) if user is not None else "err"
    print(f"{f:30s} {line:5d} {ustr:>4s} {h:8d}  {u}:{h:<9d} 2027-{mon+1:02d}-{mday:02d} {hour:02d}:00  {label}")

print()
if collisions:
    print("COLLISIONS:")
    for a, b in collisions:
        print(f"  {a} <-> {b}")
else:
    print("No filehash collisions among the 24 sites (mod 397).")
