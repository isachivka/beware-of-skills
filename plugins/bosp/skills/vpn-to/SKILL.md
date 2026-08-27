---
name: vpn-to
description: >
  Use when the home router's xkeen/xray tunnel should exit through a different WAN —
  switching the VPN between the Rostelecom and NewLink uplinks, or checking which one
  it is on right now. Typically invoked as /vpn-to rt or /vpn-to nw, and also when the
  VPN is slow because one provider's route to the VPS has degraded.
when_to_use: >
  Trigger on: /vpn-to, vpn-to rt, vpn-to nw, switch VPN to Rostelecom, switch VPN to
  NewLink, "переключи впн на ростелеком", "переключи впн на ньюлинк", "через какой
  провайдер сейчас впн", change the tunnel's uplink, xkeen PBR mark, sockopt mark.
allowed-tools: Bash, Read, Edit
---

# Switching which WAN the VPN tunnel exits through

The Keenetic router has two uplinks. Which one **xray itself** dials the VPS over is set by
`streamSettings.sockopt.mark` in the router repo's `configs/04_outbounds.json` — not by any
checkbox in the Keenetic web interface.

| Target | Argument | Uplink | Mark |
|---|---|---|---|
| Rostelecom | `rt`, `rostelecom`, `ростелеком` | `PPPoE0` / ppp0, AS12389 | `0` (no mark → table `main`) |
| NewLink | `nw`, `newlink`, `ньюлинк` | `GigabitEthernet0/Vlan5` / eth2.5, AS42893 | policy `NW` mark, resolve it live |

No argument, or `status` / `?` → just report the current state, change nothing.

## The one rule

**Edit only `~/pets/router` on this Mac. Never edit anything on the router.**

Not `/opt/etc/xray/configs/*` (what xray reads), not `/opt/root/router/*` (the clone).
The dataflow is one-directional: local repo → commit → push → `git pull` on the router →
`./run.sh`. `run.sh` does `rm -rf /opt/etc/xray/configs && cp -r ./configs`, so anything
edited out of band is silently destroyed on the next deploy — and a stale clone silently
reverts a fix that only ever landed live.

## Steps

### 1. Read the current state

```bash
python3 <skill-dir>/switch.py --show --repo ~/pets/router
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 \
  'netstat -tn | grep 194.59.204.177 | awk "{print \$4}" | cut -d: -f1 | sort | uniq -c'
```

`91.122.61.110` = Rostelecom, `146.66.162.121` = NewLink. Report both the repo's intent and
what the tunnel is actually doing — they disagree when a deploy was skipped.

Status-only request: stop here.

### 2. Resolve the target mark

`rt` is always `0`. For `nw`, read the code off the router rather than trusting a constant —
policies get recreated and the marks move:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 \
  "curl -kfsS http://localhost:79/rci/show/ip/policy | jq -r 'to_entries[] | \"\(.value.description) \(.value.mark) \(.value.table4)\"'"
```

Convert the hex mark to decimal (`printf '%d\n' 0x<mark>`). The policy named `NW` permits
only NewLink. As of 2026-08 it is `0xffffaab` = `268434091`; `XKeen` is `0xffffaaa` =
`268434090` and is multipath over both uplinks.

If the repo is already on the target mark, say so and stop — don't restart the tunnel for
a no-op.

### 3. Edit, commit, push

```bash
python3 <skill-dir>/switch.py <mark> --repo ~/pets/router
cd ~/pets/router && git diff
```

The script rewrites the mark lines so exactly one is active, validates that the result still
parses with xray's comment rules, and refuses to write otherwise. Exit code 2 means it was
already on that mark.

Commit and push. Message says which uplink and why:

```bash
git commit -am 'chore(xray): switch tunnel egress to NewLink' && git push
```

### 4. Deploy

**Check the clone is clean before deploying.** `run.sh` copies the clone's working tree, not
the commit, so a hand-edit left in `/opt/root/router` is what actually reaches xray:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'cd /opt/root/router && git status --short'
```

Any output means someone edited the router directly. `git pull` does **not** reliably clear
it: git skips a file whose content is identical at the old and new commit, so a dirty file
survives the pull untouched whenever the net diff across the pulled range is zero for it —
which is exactly what happens when the mark is flipped and flipped back. Discard the edit
before deploying, and tell the user what it was:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'cd /opt/root/router && git --no-pager diff'
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'cd /opt/root/router && git checkout -- configs/04_outbounds.json'
```

Then, **confirming with the user first** — `run.sh` calls `xkeen -restart`, and every
connection in the house drops for a few seconds:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'cd /opt/root/router && git pull && ./run.sh'
```

### 5. Verify

Read the mark back off the live config — this is the authoritative check, and it catches a
deploy that copied something other than what was committed:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'grep -n "^ *\"mark\"" /opt/etc/xray/configs/04_outbounds.json'
```

Then re-run the `netstat` check from step 1. Sockets on the old uplink linger in `LAST_ACK` /
`FIN_WAIT` for a minute after the restart, so count **ESTABLISHED only** — a mix is normal
right after a deploy, a stale ESTABLISHED majority is not:

```bash
ssh -i ~/.ssh/sshs root@192.168.1.1 -p 2022 'netstat -tn | grep 194.59.204.177 | awk "{print \$4, \$NF}" | sed "s/:[0-9]*//" | sort | uniq -c'
```

Confirm the tunnel actually carries traffic — a mark pointing at a dead table blackholes
silently:

```bash
curl -so /dev/null -w 'dl=%{speed_download} B/s\n' --max-time 30 \
  'https://speed.cloudflare.com/__down?bytes=10000000'
```

## Caveats

- The `NW` policy has a paired `from all fwmark 0x... lookup unspec blackhole` rule. If
  NewLink goes down, xray's traffic is blackholed — there is no automatic fallback to
  Rostelecom. Switching back is a deploy, not a failover.
- `run.sh` also restarts node_exporter and rewrites two crontab entries. Expected, not a bug.
- Only the `vless` outbound carries a mark. `direct` and `block` stay unmarked so
  non-proxied traffic keeps using the normal routing table.

## Red flags — stop

- About to `ssh` and edit a file under `/opt/` → wrong direction, go back to `~/pets/router`
- About to run `./run.sh` without having pushed → the router will pull an older commit
- About to run `./run.sh` without checking `git status` in the clone → a hand-edit on the
  router silently wins over the commit, and `git pull` will not always clear it
- Verified the switch by source IP alone → count ESTABLISHED, and read the live config back
- About to hardcode the NewLink mark without reading it off the router → resolve it
- About to restart xkeen when the mark is already correct → nothing to deploy

## Background

Why this exists, the full policy/mark table, and the measurements behind it live in
`~/pets/router/CLAUDE.md`, section "Через какой WAN выходит сам xray (PBR)".
