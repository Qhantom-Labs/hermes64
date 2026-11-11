# ROBOT capacity: how many robot-kit robots fit in the roof finale

Lane ROBOTS. Room numbers are the roof lane's (`wt-roof/docs/ROOF-BUDGET.md`, measured in the real runtime, `wt-roof 5f909c4f`).
Robot numbers are this lane's, measured on the shipped GLBs and confirmed in a runtime frame.

## Inputs

| Item | Triangles | Source |
|---|---|---|
| `tower_roof_finale` environment (trimmed roof) | 2,026 | ROOF-BUDGET section 3; this lane's capture measured 2,026 |
| Hero (placeholder `fv_scribe`, with shadow) | 732 | ROOF-BUDGET section 2; this lane's capture measured 732 |
| Three bosses (placeholders, with shadow) | 756 + 760 + 766 | ROOF-BUDGET section 2 |
| Captive (placeholder `tavi`, with shadow) | 780 | ROOF-BUDGET section 2 |
| **Five people** | **3,794** | ROOF-BUDGET section 2 |
| **Finale with five people, no robots** | **5,820** | ROOF-BUDGET section 4 (measured) |
| Robot-kit walker | 226 + 12 shadow = **238** | this lane |
| Robot-kit brute | 246 + 12 shadow = **258** | this lane |
| Robot-kit drone | 160 + 12 shadow = **172** | this lane |
| One of each | 668 (mean 222.7) | this lane; runtime frame: nine robots = 2,004 |

For comparison, the roof lane counted 472 per stock robot.

## Answer

**Under the 6,000 room cap, next to the hero, three bosses and the captive: 1 robot, and only a drone.**
5,820 + 172 = 5,992 (8 spare). A walker (6,058) or a brute (6,078) does not fit.

| Setup | Room without robots | Spare | Walkers only | Brutes only | Drones only | Even mix |
|---|---|---|---|---|---|---|
| Finale, five people, cap 6,000 | 5,820 | 180 | 0 | 0 | 1 | 1 (a drone) |
| Finale, five people, `arena` profile 8,000 | 5,820 | 2,180 | 9 | 8 | 12 | 10 (three of each plus a drone; 7,996) |
| Finale, five people, further sky cut (-640, ROOF-BUDGET section 5 option a), cap 6,000 | 5,180 | 820 | 3 | 3 | 4 | 3 (one of each; 5,848) |
| Same, `arena` profile 8,000 | 5,180 | 2,820 | 11 | 10 | 16 | 12 (four of each; 7,852) |
| Finale room with the hero only, cap 6,000 | 2,758 | 3,242 | 13 | 12 | 18 | 14 (four of each, a drone and a walker) |

"Even mix" = as many full walker + brute + drone sets as fit, then the cheapest single robots that still fit.

## What this means for the finale

- The 05C wave rule (at most 3 live robots) does not fit the 6,000 cap with all five people on the roof as the room stands: three robots cost 516 (drones) to 774 (brutes) and 180 is spare.
- It fits in two ways that need no lighter robot: the roof lane's `arena` profile (8,000: up to 10 robots), or the further sky cut (820 spare: one walker, one brute and one drone = 668, or any three walkers = 714; three brutes = 774 also fit).
- With the stock robots (472 each) the roof lane found 0 robots under 6,000 and 4 under 8,000. With the robot-kit robots the same room takes 1 and 10.

## Not verified

- The five-person total (3,794) is the roof lane's measurement of placeholder models. The real hero, CEO and captive models do not exist; their counts decide the real answer.
- The finale with five people and robot-kit robots together was not run. This lane's runtime frame had the hero and nine robots only (4,762 measured = 2,026 + 732 + 2,004), which confirms the per-robot cost, not the five-person scene.
- The further sky cut is the roof lane's estimate (336 + 184 + 120), not a built room.
- Effects, projectiles and UI triangles during a fight are not in any number here.
