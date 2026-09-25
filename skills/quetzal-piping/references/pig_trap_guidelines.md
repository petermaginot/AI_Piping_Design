# Guidelines for pig launcher and receiver design
Pig traps are piping assemblies intended to launch or receive pipeline pigs.

## Pressure class and schedule
As with all piping components, pig traps will have a design pressure that influences the pressure class and schedules selected for components and pipe. The pig trap design guidelines should include the desired pressure class for all flanges and socket/threaded fittings and the schedule of all sizes of pipe to be used. There may be cases where a reducing fitting has a mismatch in schedules required of its two sizes. In these cases, the more conservative schedule will be required for these fittings. For example, if Sch-XS is specified for 2" and Sch-STD is specified for 3", 2" x 3" reducers should be specified as Sch-XS.

## General pig trap arrangement
Most common pig traps have this layout: [Trap_diagram.svg](Trap_diagram.svg)

Traps should have an inlet isolation valve and a kicker valve. Most traps also have a bypass valve to allow flow around the trap while the trap is open. Traps generally have a high point vent to vent air or gases and a low point drain to drain liquids from.

The minor barrel is the part of the pig trap constructed of pipe the same diameter as the main pipeline through which the pig travels. For launchers, there is sometimes no dedicated minor section, with the reducer welded directly to the flange that attaches to the trap valve. For receivers, the minor barrel should be at least as long as the length of the longest pig to be run in the pipeline, so that the pig does not stall until it is fully past the trap valve.

The major barrel is the part of the pig trap constructed of pipe larger than the main pipeline through which the pig is run. For a launcher, it is generally the length of the longest pig to be run in the line (with some exceptions noted below). For a receiver, it should be at least the length from the pig's nose to the last sealing cup on the pig, so the sealing cups end up entirely in the oversize section and don't obstruct the flow of fluid after the pig is trapped. The inner diameter of the major barrel should be at least 20% larger than the inner diameter of the main pipeline, and is generally constructed of the most commonly available pipe size above that threshold.

The kicker line is generally built off a branch connection of a tee fitting off the major barrel. Pig bars are generaly installed in the kicker branch to prevent the pig from being sucked into the kicker line (these are not currently modeled in Quetzal). The size of the kicker line may be less than that of the main line but should be adequate to prevent excessive pressure drop and erosional velocities at the expected flow rate.

## Equalization lines
Some launchers are constructed with a small-diameter equalization line connecting the major and minor barrels. Having this line open during pressurization of the trap prevents the pig from moving before desired when launching. For receivers, this line allows any trapped pressure behind the pig to be vented before opening. Similarly, some traps are equipped with drains on both the major and minor barrels to allow liquids both in front of and behind the pig to be drained before removing the pig. 

## Closures
Pig traps are equipped with a closure mechanism on the oversize section to allow the pig to be removed. Closures can be simple blind flanges that are unbolted/bolted each time a pig is run or specialty devices that can be quickly opened and closed. Quetzal's default objects can only model blind flange closures, but quick-closure vendors can supply drawing files for other varieties.

## Pull ports
Some pig launchers are equipped with a pull port on the minor barrel. This port allows a rope to be attached to the front of a pig to pull it in rather than pushing it in, and is a common way of inserting heavy inline inspection tools. These ports can range in size from 2" - 4", and can be constructed from a Thread-O-Ring (TOR) fitting, weldolet + flange, or reducing tee + flange. The pull port is generally placed as close to the trap valve as weld spacing allows to allow as long a pig as possible to be pulled into the trap. Pull ports also allow you to reduce the length of the major barrel while still allowing long diameter inline inspection tools to be run by taking advantage of minor barrel + reducer length.