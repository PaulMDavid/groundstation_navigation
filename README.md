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

## Teleop panel

The right-hand panel drives the rover through navigation_ws `app_teleop` when the
robot's command source is `ground` (`scripts/teleop_source.sh` there):

- **Autonomous / Manual** set the robot's mode; **STOP** (or space) works whatever the
  source is.
- Hold **W/S** to drive and **A/D** to turn, in Manual, at the slider's share of the
  robot's speed limits. It publishes `/teleop/ground/cmd_vel` at 10 Hz. Releasing the
  keys, or the window losing focus, sends zero. If the GUI or the link dies, the robot's
  deadman stops the rover within 0.5 s.
- Mode, source and whether the robot hears this PC come from the robot's `/teleop/state`.

## Over eduroam: Zenoh

Without the wired link, reach the robot through its Zenoh router instead of DDS. Put
this in `.env`:

```
GS_LINK=zenoh
ROBOT_IP=<orintwo's eduroam address>
```

`./run.sh` then also starts `zenoh_bridge` (client mode, `config/zenoh_bridge_ground.json5`)
and keeps this machine's DDS on loopback (`config/cyclonedds_local.xml`); only the
allowlisted topics cross. No DDS peer list is needed in this mode.
