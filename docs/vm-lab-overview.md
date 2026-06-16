# VM Lab Overview

## Network Roles

- Ubuntu workload client: creates benign DNS, HTTP, SMB, TCP, and database
  traffic.
- Debian file server: provides SSH and SMB targets for normal client behavior.
- App/DB server: provides HTTP endpoints and PostgreSQL demo data.
- Kali or test attacker: generates scan traffic for validation.
- pfSense router: provides the capture point for server-zone traffic.
- Monitor VM: runs Zeek conversion, feature generation, model inference, and
  dashboard delivery.
- Dashboard VM: receives and displays detection events.

## Default Server Zone

```text
App/DB:  10.10.20.10
IoT lab: 10.10.20.20-24
Debian:  10.10.20.30
```

## Realtime Capture Defaults

```text
Router SSH: ndr-router
Router interface: em2
Target network: 10.10.20.0/24
Capture chunk: 60 seconds
Model window: 10 seconds
Dashboard URL: http://127.0.0.1:8000
```
