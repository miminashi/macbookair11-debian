> **注記 (2026-09-18、本体による)**: この文書の「Discriminator」節の結論 (lid close→suspend の約 91 秒遅延が発症を分ける) は採用しない。遅延はリークで `modprobe -r wl` が固まった**結果**である。真因と判別子は、非同期復号の蓄積 (レポート本文) を参照すること。イベントの一覧と件数は、事実の記録として有効。

# VPN (nm-xfrm) teardown events vs netdev refcount leak — boots -3, -2, -1

Analysis date: 2026-09-18. Read-only journalctl analysis on macbookair2015.lan, boots -3 (3c0832391a75, 2026-08-06..08-21), -2 (42613d4ae9e3, 2026-08-22..09-18), -1 (a7607c1d7f13, 2026-09-18 15:33..16:19). Boot 0 (current) has zero `unregister_netdevice`, zero `interface .* deleted`, zero `interface change for bypass policy` events — not relevant.

## Method

Every event where the strongSwan `charon-nm` full-tunnel VPN ("GSNet") had an active `nm-xfrm-*` interface and its underlying carrier device (`wlp3s0` or `enx*`) disappeared produces a log line:

```
charon-nm: NN[IKE] interface change for bypass policy for fe80::/64 (from <dev> to nm-xfrm-N)
```

This line only fires when the fe80::/64 link-local bypass policy has to move off a vanishing carrier device, so it is a complete, purpose-built marker for "underlying device went away while VPN was up". Grepping it across the three boots gives every candidate event (38 total: boot -3 = 15, boot -2 = 21, boot -1 = 2). Reverse-direction lines (`from nm-xfrm-N to <dev>`, a device *reappearing*) were excluded — they are not loss events.

For each candidate, the interface-deleted timestamps for `<dev>` and `nm-xfrm-N`, `IKE_SA delete failed`, `error uninstalling route installed with policy`, `sme.c:848` WARN, `Lid closed`/USB-unplug context, and any subsequent `unregister_netdevice: waiting` were correlated with a small offline script (no state was changed on the remote host; only `journalctl` reads were performed).

## Top-level split (38 candidate events)

| Outcome of the reroute attempt | Count | Leaked |
|---|---|---|
| **MOBIKE successful reroute** (an alternate path — usually the other of wlp3s0/enx — was already available; xfrm interface persists, no delete, no retransmit-timeout) | 30/38 (79%) | 0/30 |
| **"Giving up" hard teardown** (no alternate path; `deleting IKE_SA` → 3 failed retransmits ("Network is unreachable") → `giving up after 3 retransmits` / `proper IKE_SA delete failed, peer not responding` → `error uninstalling route installed with policy` → nm-xfrm interface deactivated+deleted) | 8/38 (21%) | **3/8 (37.5%)** |

Total leak rate over all candidate events: 3/38 ≈ 7.9%. Conditional on actually hitting the "giving up" hard-teardown path (the only path any leak occurred on): 3/8 = 37.5%. Zero leaks were ever seen in a successful-MOBIKE event.

## Discriminator (evidence-backed conclusion)

Within the 8-event "giving up" cohort, the clean, 100%-consistent separator is **the time gap between the underlying device's `interface X deleted` and the VPN's `interface nm-xfrm-N deleted`**, which is itself governed by whether the kernel actually entered suspend quickly:

| Event | Gap (dev-delete → xfrm-delete) | `PM: suspend entry` delay after `Lid closed` | Leak |
|---|---|---|---|
| boot-3 2026-08-21 17:30:37 (wlp3s0) | **12.8 s** | **91.6 s** | **YES** |
| boot-2 2026-09-18 14:51:21 (enx) | **14.3 s** | **91.8 s** | **YES** |
| boot-1 2026-09-18 16:13:30 (wlp3s0) | **12.8 s** | **91.7 s** | **YES** |
| boot-2 2026-09-16 21:41:11 (enx) | 29.8 s | 1.0 s | no |
| boot-3 2026-08-14 16:42:14 (enx) | 123.3 s | ~1.5 s | no |
| boot-3 2026-08-12 14:22:21 (enx) | 245.2 s | 2.2 s | no |
| boot-1 2026-09-18 15:48:52 (enx) | 284.0 s | 2.1 s | no |
| boot-2 2026-08-24 00:27:04 (enx) | 306.6 s | 2.1 s | no |

**All 3 leaks: gap ≈ 12.8–14.3 s and suspend-entry delay ≈ 91.6–91.8 s. All 5 non-leaks: gap ≥ 29.8 s (mostly 2–5 min) and suspend-entry delay ≤ 2.2 s.** The two numbers are two views of the same mechanism:

- In the **non-leak** cases, real kernel suspend (`PM: suspend entry (deep)`) engages within 1–3 s of the device disappearing, which freezes charon's retransmit timers mid-sequence. The "giving up" / route-uninstall / xfrm-delete only plays out for real *after* resume (hence the large gap), by which time the device teardown race is long over and safe.
- In the **leak** cases, kernel suspend does *not* engage quickly — it is delayed by a strikingly consistent ~91–92 s (looks like a fixed ~90 s systemd unit/hook timeout being hit). During that whole window the machine stays fully awake, and charon's entire failed-teardown sequence (delete → 3 retransmits → give up, ~13–14 s) runs to completion in real, un-paused execution *while* the underlying device's own kernel unregistration (`modprobe -r wl` unregistering `wlp3s0`, or the USB core's real disconnect path for `enx`) is concurrently in flight. That un-paused race is what corrupts the netdev refcount. Evidence that the ~91 s delay is a *symptom*, not an independent cause: in the boot-1 16:13 leak, `unregister_netdevice: waiting for wlp3s0` is already being logged at 16:13:42 — 3 s before charon even finishes "giving up" (16:13:45) and 77 s before `PM: suspend entry` finally happens (16:15:02). The stuck `modprobe -r wl` (part of the `45-wl-unload` pre-sleep hook) is almost certainly what blocks the sleep sequence for ~90 s until some default unit timeout kills it and lets suspend proceed anyway, with the leak already permanent.

Secondary markers, present but **not discriminating**:
- `IKE_SA delete failed, peer not responding` and `error uninstalling route installed with policy`: present in **all 8/8** giving-up events (leak and non-leak alike) — a necessary precondition of entering the risky path at all, but doesn't separate leak from non-leak within that path.
- `interface change for bypass policy ... to nm-xfrm-N`: present in **38/38** candidate events by construction (it's how the candidate list was built) — universal, not discriminating.
- `sme.c:848` cfg80211 WARNING: present in 2/3 leaks (both `wlp3s0`-carrier events: boot-3 08-21, boot-1 16:13) but absent in the `enx`-carrier leak (boot-2 09-18 14:51). Also appears in at least 1 clean MOBIKE-success non-leak event (boot-2 09-15 23:19:18) with no failure and no leak. It's simply a frequent artifact of `wl`/cfg80211 WiFi-teardown races (noted in the task background) and by itself predicts neither the giving-up path nor the leak.
- Whether charon vs NetworkManager tears the VPN down: in every teardown observed, it is **charon-nm's own `[KNL]` plugin** that reacts autonomously to the kernel/netlink notification of the underlying device's disappearance (`deleting IKE_SA`, retransmit/give-up, route uninstall, xfrm delete) — NetworkManager only manages the physical device's sleep/removal state and never issues an explicit "disconnect VPN" command in these traces.

## The 3 leak events in detail

### Leak 1 — boot -3, 2026-08-21 17:30:37 JST, wlp3s0, lid-close sleep
```
17:30:37.670  systemd-logind: Lid closed.
17:30:37.880  charon-nm: interface change for bypass policy for fe80::/64 (from wlp3s0 to nm-xfrm-1102441)
...            deleting IKE_SA / 3 retransmits, all "Network is unreachable"
~17:30:50      interface wlp3s0 deleted                       (45-wl-unload modprobe -r wl)
17:30:50.66    giving up after 3 retransmits / proper IKE_SA delete failed, peer not responding
               error uninstalling route installed with policy 192.168.83.1/32 === 0.0.0.0/0 out
               interface nm-xfrm-1102441 deleted                (gap from wlp3s0-delete ≈ 12.8 s)
17:32:09.329  kernel: PM: suspend entry (deep)                  (91.6 s after Lid closed — LATE)
(then, every ~10 s, forever)
kernel: unregister_netdevice: waiting for wlp3s0 to become free. Usage count = N
kernel: unregister_netdevice: waiting for nm-xfrm-1102441 to become free. Usage count = -8
```
(This is the event already documented in memory as the WiFi×VPN netdev-refcount corruption that led to the 8/21 5-hour battery-drain.)

### Leak 2 — boot -2, 2026-09-18 14:51:21 JST, enxce6023bad528 (iPhone tether unplug)
```
14:51:21.434  kernel: apple-mfi-fastcharge 1-1: USB disconnect, device number 14
14:51:21.454  charon-nm: interface enxce6023bad528 deleted
14:51:21.522  charon-nm: 10[IKE] deleting IKE_SA GSNet[3] between 172.20.10.5[macbookair2015]...160.16.210.47[160.16.210.47]
14:51:21.527  charon-nm: 05[NET] error writing to socket: Network is unreachable
14:51:21.540  charon-nm: 12[IKE] interface change for bypass policy for fe80::/64 (from enxce6023bad528 to nm-xfrm-1860628)
14:51:23.528  retransmit 1 ... Network is unreachable
14:51:26.200  systemd-logind: Lid closed.                        (~4.8 s AFTER the USB unplug, separate trigger)
14:51:26.226  charon-nm: interface wlp3s0 deactivated              (concurrent WiFi sleep teardown begins)
14:51:26.329  retransmit 2 ... Network is unreachable
14:51:28.002  charon-nm: interface wlp3s0 deleted                  (wl unload, unrelated bystander device — does NOT leak here)
14:51:30.248  retransmit 3 ... Network is unreachable
14:51:31.586  kernel: unregister_netdevice: waiting for enxce6023bad528 to become free. Usage count = 12   (already stuck BEFORE giving-up is even logged)
14:51:35.736  charon-nm: giving up after 3 retransmits / proper IKE_SA delete failed, peer not responding
14:51:35.737  charon-nm: error uninstalling route installed with policy 192.168.83.1/32 === 0.0.0.0/0 out
14:51:35.755  charon-nm: interface nm-xfrm-1860628 deleted            (gap from enx-delete ≈ 14.3 s)
14:52:57.961  kernel: PM: suspend entry (deep)                        (91.8 s after Lid closed — LATE)
(then, every ~10 s, forever)
kernel: unregister_netdevice: waiting for enxce6023bad528 to become free. Usage count = 12
kernel: unregister_netdevice: waiting for nm-xfrm-1860628 to become free. Usage count = -10
```
No `sme.c:848` in this event — wlp3s0's own unload proceeded cleanly; the stuck device is `enx`, not `wlp3s0`.

### Leak 3 — boot -1, 2026-09-18 16:13:30 JST, wlp3s0, lid-close sleep
```
16:13:30.521  systemd-logind: Lid closed.
16:13:30.781  charon-nm: 12[IKE] interface change for bypass policy for fe80::/64 (from wlp3s0 to nm-xfrm-1147959)
16:13:30.782  charon-nm: 14[IKE] old path is not available anymore, try to find another
16:13:30.785  charon-nm: 14[IKE] no route found to reach 160.16.210.47, MOBIKE update deferred
16:13:30.801  charon-nm: 05[IKE] deleting IKE_SA GSNet[2] between 192.168.1.13[macbookair2015]...160.16.210.47[160.16.210.47]
16:13:30.807  kernel: WARNING: CPU: 3 PID: 9424 at net/wireless/sme.c:848 __cfg80211_connect_result+0x8be/0x8d0 [cfg80211]
16:13:30.821  charon-nm: 09[NET] error writing to socket: Network is unreachable
16:13:32.228  charon-nm: 11[KNL] interface wlp3s0 deleted                (45-wl-unload modprobe -r wl)
16:13:32.821 / 35.622 / 39.541  retransmit 1/2/3 ... Network is unreachable
16:13:42.320  kernel: unregister_netdevice: waiting for wlp3s0 to become free. Usage count = 3   (already stuck BEFORE giving-up is logged)
16:13:45.029  charon-nm: 10[IKE] giving up after 3 retransmits / proper IKE_SA delete failed, peer not responding
16:13:45.029  charon-nm: 10[KNL] error uninstalling route installed with policy 192.168.83.1/32 === 0.0.0.0/0 out
16:13:45.056  charon-nm: 06[KNL] interface nm-xfrm-1147959 deleted        (gap from wlp3s0-delete ≈ 12.8 s)
16:15:02.189  kernel: PM: suspend entry (deep)                            (91.7 s after Lid closed — LATE)
(then, every ~10 s, until boot -1 ends at 16:19:28)
kernel: unregister_netdevice: waiting for wlp3s0 to become free. Usage count = 3
kernel: unregister_netdevice: waiting for nm-xfrm-1147959 to become free. Usage count = -1
```

## Representative non-leak "giving up" events (control group)

### boot -1, 2026-09-18 15:48:52 JST — iPhone USB unplug, VPN up, NO LEAK (task's callout event)
```
15:48:52.664  kernel: apple-mfi-fastcharge 1-1: USB disconnect, device number 7
15:48:52.673  charon-nm: interface enxce6023bad528 deleted
15:48:52.692  kernel: ipheth 1-1:4.2: Apple iPhone USB Ethernet now disconnected
15:48:52.726  charon-nm: 16[IKE] deleting IKE_SA GSNet[1] between 172.20.10.5[macbookair2015]...160.16.210.47[160.16.210.47]
15:48:52.731  charon-nm: 09[NET] error writing to socket: Network is unreachable
15:48:52.765  charon-nm: 02[IKE] interface change for bypass policy for fe80::/64 (from enxce6023bad528 to nm-xfrm-8295772)
15:48:54.730 / 57.531 / 49:01.450  retransmit 1/2/3 ... Network is unreachable
15:49:00.773  systemd-logind: Lid closed.                       (~8 s after unplug, separate trigger — same overlap shape as Leak 2)
15:49:00.786  charon-nm: interface wlp3s0 deactivated
15:49:02.416  charon-nm: interface wlp3s0 deleted                (wl unload, again a bystander)
15:49:02.896  kernel: PM: suspend entry (deep)                    (2.1 s after Lid closed — FAST; machine genuinely sleeps here)
15:53:35.65   kernel: Freezing user space processes               (resume/next-cycle activity begins ~4m33s later)
15:53:36.717  charon-nm: interface nm-xfrm-8295772 deleted        (gap from enx-delete ≈ 284.0 s — "giving up"/route-uninstall only completed AFTER resume)
```
No `unregister_netdevice` ever appears for this event. This is the closest structural twin of Leak 2 (same enx-unplug-then-lid-close-then-wl-unload shape, same failed-retransmit/giving-up chain) — the only material difference is that kernel suspend actually engaged within ~2 s here, instead of being delayed ~92 s as in the 3 leaks.

### boot-3, 2026-08-12 14:22:21 / 2026-08-14 16:42:14; boot-2, 2026-08-24 00:27:04 / 2026-09-16 21:41:11
All four are lid-close events where `PM: suspend entry (deep)` follows `Lid closed` within 1.0–2.2 s; the charon `deleting IKE_SA` → retransmit → `giving up` → route-uninstall-error → xfrm-delete chain is paused by the real suspend and only completes after the corresponding `Lid opened` / suspend-exit, producing gaps of 123–307 s. No `unregister_netdevice` in any of the four. Example (08-24 00:27:04):
```
00:27:04.129  Lid closed.
00:27:04.303  interface enx98e0d98d205e deleted
00:27:04.422  deleting IKE_SA GSNet[2] ...
00:27:05.818  interface wlp3s0 deleted
00:27:06.219  kernel: PM: suspend entry (deep)      (2.1 s after Lid closed)
00:32:01.947  kernel: PM: suspend exit               (Lid opened 00:32:01.533)
00:32:10.897  giving up after 3 retransmits / proper IKE_SA delete failed, peer not responding
00:32:10.897  error uninstalling route installed with policy 192.168.83.1/32 === 0.0.0.0/0 out
00:32:10.913  interface nm-xfrm-1236358 deleted     (gap ≈ 306.6 s)
```
The 09-16 21:41:11 event differs slightly in that charon used MOBIKE "path probing" (10 attempts) rather than a classic IKE_SA-delete retransmit before giving up ("giving up after 10 path probings"), but the shape is identical: quick suspend entry (1.0 s), long gap (29.8 s) to xfrm delete, no leak.

## Representative successful-MOBIKE (dev_only) non-leak event

### boot-2, 2026-09-15 23:18:58–23:19:24 JST — wlp3s0 roam + lid-close overlap, VPN interface survives, NO LEAK
```
23:18:58.149  charon-nm: 13[IKE] old path is not available anymore, try to find another
23:18:58.149  charon-nm: interface change for bypass policy for fe80::/64 (from nm-xfrm-4200134 to wlp3s0)   (reverse direction: WiFi just reappeared, not disappeared)
23:18:58.291  charon-nm: 15[IKE] requesting address change using MOBIKE ... checking path ...
... (MOBIKE path-probing attempts 1-8, sending on 3 candidate peer addresses each) ...
23:19:18.388  wlp3s0 addresses disappear (WiFi dropping again, likely for lid-close sleep)
23:19:18.464  interface wlp3s0 deactivated
23:19:18.488  charon-nm: interface change for bypass policy for fe80::/64 (from wlp3s0 to nm-xfrm-4200134)
23:19:18.596  kernel: WARNING ... sme.c:848 ...                       (sme.c:848 present, but no failure follows)
23:19:20.795  charon-nm: 06[IKE] path probing attempt 9 / no route found to reach peer, path probing deferred
23:19:23.571  charon-nm: interface wlp3s0 deleted                     (wl unload)
23:19:24.229  kernel: PM: suspend entry (deep)                        (fast, ~0.66 s after wlp3s0-delete)
```
`nm-xfrm-4200134` is never deleted in this event — no `deleting IKE_SA`, no retransmits, no route-uninstall error, no leak. This illustrates the low-risk majority path (30/38): when an alternate carrier is available (or reappears) in time, MOBIKE simply relocates the SA's source address and the VPN tunnel survives the device churn untouched.

## Full candidate-event list (all 38)

### "Giving up" hard-teardown cohort (8 events — the only ones with any leak risk)
| # | Boot | Timestamp (JST) | Device | Trigger | Gap (dev→xfrm delete) | ikefail | routeerr | sme.c:848 | suspend-entry delay | Leak |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | -3 | 2026-08-12 14:22:21 | enx98e0d98d205e | lid-close | 245.2 s | yes | yes | no | 2.2 s | no |
| 2 | -3 | 2026-08-14 16:42:14 | enx98e0d98d205e | lid-close | 123.3 s | yes | yes | no | ~1.5 s | no |
| 3 | -3 | 2026-08-21 17:30:37 | wlp3s0 | lid-close | 12.8 s | yes | yes | **yes** | **91.6 s** | **YES** |
| 4 | -2 | 2026-08-24 00:27:04 | enx98e0d98d205e | lid-close | 306.6 s | yes | yes | no | 2.1 s | no |
| 5 | -2 | 2026-09-16 21:41:11 | enxce6023bad528 | lid-close | 29.8 s | no (path-probing giveup) | yes | no | 1.0 s | no |
| 6 | -2 | 2026-09-18 14:51:21 | enxce6023bad528 | USB unplug + lid-close overlap | 14.3 s | yes | yes | no | **91.8 s** | **YES** |
| 7 | -1 | 2026-09-18 15:48:52 | enxce6023bad528 | USB unplug + lid-close overlap | 284.0 s | yes | yes | no | 2.1 s | no |
| 8 | -1 | 2026-09-18 16:13:30 | wlp3s0 | lid-close | 12.8 s | yes | yes | **yes** | **91.7 s** | **YES** |

### Successful-MOBIKE cohort (30 events, 0 leaks) — timestamps (JST), device → new nm-xfrm
boot -3 (12): 08-07 15:01:09 enx, 08-07 15:35:46 enx, 08-07 15:54:03 enx, 08-07 17:03:10 enx, 08-07 18:22:17 enx, 08-11 16:46:54 enx, 08-11 21:40:44 enx, 08-12 14:32:35 enx, 08-14 14:11:58 enx, 08-14 16:53:18 enx, 08-14 22:53:58 enx, 08-15 17:48:54 enx.
boot -2 (18): 08-24 00:00:12 enx, 08-24 00:38:09 enx, 08-25 15:15:34 enx, 08-25 16:32:31 enx, 08-25 20:49:30 enx, 08-31 21:19:41 enx, 09-07 00:14:12 enx, 09-10 14:20:12 enx, 09-10 22:45:14 enx, 09-13 19:58:09 enx, 09-14 13:39:32 enx, 09-14 22:18:38 enx, 09-14 22:43:59 enx, 09-15 16:32:49 enx, 09-15 23:19:18 wlp3s0 (detailed above, has sme.c:848 but no failure/leak), 09-16 13:39:37 enx, 09-16 22:43:20 enxce6023bad528, 09-16 23:18:17 enxce6023bad528.
boot -1 (0): none — both boot -1 candidates fell into the giving-up cohort.

Totals: boot-3 12 + boot-2 18 + boot-1 0 = 30 successful-MOBIKE events; combined with the 8 giving-up events (boot-3 3, boot-2 3, boot-1 2) that is 30+8=38, matching the 15/21/2 per-boot candidate counts (12+3=15, 18+3=21, 0+2=2).

## Rate estimate

- Total device-disappeared-while-VPN-up events across the 3 boots analyzed: 38.
- Leaks: 3 (one per boot; each boot's leak triggered exactly one `unregister_netdevice` loop that persisted to end of boot — confirmed by the unregister_netdevice line counts: boot-3 3671 lines / boot-2 499 lines / boot-1 69 lines, each fully accounted for by a single continuous 10s-interval loop from the one leak event to boot end).
- Overall rate: 3/38 ≈ 7.9%.
- Rate conditional on hitting the "no alternate path, must hard-teardown" branch: 3/8 = 37.5%.
- Rate conditional on hitting that branch AND kernel suspend being delayed ~90 s: 3/3 = 100% (n=3, all observed instances of the delayed-suspend pattern leaked).
