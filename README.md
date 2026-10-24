# groundstation_navigation

Ground station tools for the navigation team.

## Bringup panel

A window that shows the robot's staged Nav2 bringup (see `app_bringup_manager`
in navigation_ws): one row per stage with a status light, every health check
with its live value, container state, and the logs of whatever failed.

- **BRING UP / RECOVER** — starts everything, or restarts from the first stage
  that isn't ready. It is not an emergency stop.
- **Stop all** — stops every bringup container on the robot.

```bash
./run.sh
```

Needs Docker and a wired connection to the robot's switch. The DDS config uses
`enp63s0`; if your wired interface is named differently, put `GS_IFACE=<name>`
in a `.env` file next to `docker-compose.yaml`. Your laptop's IP must be in the
peer list of `config/cyclonedds.xml` here *and* in navigation_ws
`src/config/dds/cyclonedds.xml` on the robot.

"No contact with bringup manager" means no status message for 3 s: the robot
is off, the manager container isn't running, or DDS can't reach it.
