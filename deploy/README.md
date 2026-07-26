# Scheduling MediaWhisperer

The tool is built to run unattended: it's resilient per-item (one bad feed can't
sink the run), it exits cleanly, and with `skip_seen` on (the default) each run
only compiles what's new since last time. Point it at a scheduler and forget it.

Use `--log-file` for unattended runs so progress and any per-item errors are
captured with timestamps.

## Option A — cron

```bash
# Edit the paths inside the file first, then:
crontab deploy/crontab.example
```

See [`crontab.example`](crontab.example) for daily and weekly lines.

## Option B — systemd timer (Linux)

```bash
# Copy and edit the unit files (adjust WorkingDirectory / ExecStart paths):
mkdir -p ~/.config/systemd/user
cp deploy/mediawhisperer.service deploy/mediawhisperer.timer ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now mediawhisperer.timer

# Check status / next run / logs:
systemctl --user list-timers mediawhisperer.timer
journalctl --user -u mediawhisperer.service
```

Edit `OnCalendar` in the timer to change the cadence (daily vs. weekly).

## Option C — macOS launchd

Wrap the same command in a `launchd` plist with a `StartCalendarInterval`. The
command to run is identical:

```
/path/to/.venv/bin/mediawhisperer run -c /path/to/config.yaml --log-file /path/to/mediawhisperer.log
```
