# NACA0020 wing in IBAMR: implementation decisions

**Purpose.** Port the IB2d NACA0020 case (fish-ib2d `cases/NACA0020_Wing`,
copied at commit `9b21eda`) to IBAMR's IBMethod (springs and target points, 2D).
The reference is SoRoLily (see the IB2d case's `IMPLEMENTATION_DECISIONS.md`).

**Plan (user, 2026-11-06; goal restated 2026-11-09).** The goal is to replicate
SoRoLily as closely as possible. Where IBAMR can do what SoRoLily does, match
SoRoLily; IB2d's choices were compromises forced by its own limits. Values with
no SoRoLily equivalent start from the IB2d case.

**Ground rule: the user decides every aspect of the setup.** Rows marked
**[default]** were chosen by Claude to follow the plan and still await review;
rows marked **D** keep an IBAMR default whose IB2d equivalent is unchecked.

## 1. Status codes

| code | meaning |
|---|---|
| **M** | matched: same value or same model as IB2d |
| **A** | approximated: IBAMR does it differently; the difference is given |
| **S** | matched to SoRoLily instead of IB2d (IB2d could not do it) |
| **D** | IBAMR default kept; the IB2d equivalent is not yet checked |
| **—** | not in this stage |

## 2. Comparison table: IB2d → IBAMR

### 2.1 Fluid and domain

| quantity | IB2d (9b21eda) | IBAMR (this case) | status | notes |
|---|---|---|---|---|
| fluid density | `rho = 1000` | `RHO = 1000` | M | |
| viscosity | 30× water, `mu = 0.030069` | 30× and 1× water (`MU` per run) | **S** at 1× | SoRoLily: water. Each run's value is in its `run_info.json` |
| domain | 1.2 × 1.2 m, doubly periodic | `Lx = 1.2`, real boundaries (`periodic_dimension = 0,0`) | **S** | SoRoLily's box |
| grid | `Nx = 192`, dx = 6.25 mm = chord/32 | `Nx = 192`, `MAX_LEVELS = 1` (no AMR) | M | also SoRoLily's grid |
| free stream | fringe + mean-flow controller (IB2d is periodic only) | SoRoLily's: on every face the normal velocity is fixed to U (cos α, sin α), the tangential one is zero-gradient (`VelocityBcCoefs_0/1`) | **S** | stage 2. SoRoLily `exitBC = false`: the outlet is prescribed too |
| angle of attack | 0° → 15° at 5 s, 0.1 s cubic smoothstep | same, written in the boundary formulas | M (and S) | checked against `wing_case.aoa_rad` |
| initial flow | at rest, then a 0.02 s ramp to U (avoids clamp ringing) | u = U everywhere at t = 0 (`VelocityInitialConditions`) | **S** | SoRoLily's start. Watch the clamp ringing that made IB2d use a ramp |
| advection | central differences, skew-symmetric | `CUI`, `SKEW_SYMMETRIC` | **S** (approx.) | SoRoLily: limited QUICK. `CENTERED` (IB2d's) was used in stages 1-2b |
| advection time stepping | IB2d's scheme (to check) | `ADAMS_BASHFORTH` | D | IBAMR default |
| viscous time stepping | IB2d's scheme (to check) | trapezoidal rule (Crank–Nicolson) | D | IBAMR default |
| pressure / projection | FFT projection | staggered-grid Krylov solvers | A | different solver, same continuous problem |

### 2.2 Structure

| quantity | IB2d (9b21eda) | IBAMR (this case) | status | notes |
|---|---|---|---|---|
| mesh | `Wing_Geom.py`: outline + Halton fill, ×4, Delaunay | same script, copied | M | |
| stiffness calibration | `stiffness_scale` measured per mesh (`verify_structure.measure_scale`) | same | M | |
| stiffness units | files hold K_phys / ds: IB2d spreads f · ds, ds = Lx/(2 Nx) | files hold K_phys: IBAMR spreads nodal values, not densities (`ibtk/LEInteractor.h`) | M | conversion in `Wing_Geom.write_files` (× ds); same physical springs |
| spring law | F = k (\|D\| − L) D/\|D\| (vectorised in the user-force hook) | `default_spring_force`: K (R − L) | M | native in IBAMR, no hook |
| clamp (rigid LE block) | target points, `update_target = 0`, factor 3 | `.target`, static, damping η = 0 | M | |
| pre-bent start | bent `.vertex`, straight rest lengths | same files | M | |
| delta function | Peskin 4-point (`Supp.give_Delta_Kernel`) | `IB_4` | M | |
| IB time stepping | IB2d's scheme (to check) | midpoint rule | D | IBAMR default |

### 2.3 Run and outputs

| quantity | IB2d (9b21eda) | IBAMR (this case) | status | notes |
|---|---|---|---|---|
| time step | `dt = 2e-4` s | `DT = 2e-4` | M | |
| run length | 10 s (full schedule) | `END_TIME = 10.0` s | M | user, 2026-11-06. In still fluid the 5 s angle switch has no effect (it rotates the free stream) |
| field output | every 0.05 s | `VIZ_INTERVAL = 250` steps (0.05 s): U, P, Ω, div U; structure | M | |
| per-step diagnostics | forces on the clamp, TE position, fluid energy (Python hooks) | none yet; structure positions every 0.05 s (`hier_data_IB2d/X.*`) | — | C++ output in a later stage |

## 3. Still different from SoRoLily (todo)

Reference values: the IB2d case's `IMPLEMENTATION_DECISIONS.md` §3, checked at source.

**To do (IBAMR can match it):**

| item | SoRoLily | here now | what it takes |
|---|---|---|---|
| viscosity | water, μ = 1.0023e-3 Pa·s (Re ≈ 4e4) | 30× water | `MU` in `input2d`. Next run after the 30× one |
| advection | QUICK + median limiter (upwind-biased, bounded) | `CUI` (user, 2026-11-10) | runs at 30× and 1× water pending. `CUI` = bounded cubic upwind (Waterson & Deconinck), same family as limited QUICK; `PPM` (piecewise parabolic) is the alternative |
| outputs | TE y(t); Fx, Fy (Butterworth 1.5 Hz); deformed shape; surface pressure at 30 panels; every 0.01 s | fields and points every 0.05 s | C++ output in `example.cpp` (stage 3). Needed for any comparison |

**To check (may be possible):**

| item | SoRoLily | here now | open question |
|---|---|---|---|
| material damping | Kelvin–Voigt η = 2e3 Pa·s (bending τ = 3η/E = 0.6 s) | none | user, 2026-11-11: the undamped IB wings' tails oscillate much more than SoRoLily's; likely part of the wake difference. SoRoLily can't run undamped (η = 0 and 100 diverge; lowest stable η = 200, run exists at 30×: `sorolily_matched_re/nu30_eta200`). IBAMR: a dashpot per spring (F = k(L−L₀) + c dL/dt) via a custom `IBLagrangianForceStrategy` (it receives point velocities), combined with the standard springs (`IBLagrangianForceStrategySet`). OPEN |
| solid density | 1064.6 kg/m³ | wing mass = fluid (1000) | does IBAMR's IBMethod support massive (penalty-mass) points? |

**Cannot match (method differences, reported as such):**

| item | SoRoLily | here | why |
|---|---|---|---|
| body seen by the fluid | BDIM (smoothed solid region) | IB points + `IB_4` | different immersed-body methods |
| flexible link | Cosserat rod, 4 DOF (curvature only) | calibrated spring mesh (ν ≈ 0.3, not 0.5) | IBMethod only has points, springs, beams, targets. IBFE would be a continuum, still not a rod |
| coupling | loads low-pass filtered (3 Hz pressure, 1.5 Hz forces) before reaching the structure | unfiltered forces spread every step | IB couples fluid and structure directly at every step |
| time step | 0.01 s | 2e-4 s | explicit IB is limited by spring and clamp stiffness |
| clamp | exactly rigid | stiff targets (factor 3) | targets only approach rigid as k → ∞ |

## 4. Stages

| stage | what | status |
|---|---|---|
| 1 | pre-bent wing released in still fluid: geometry, units, springs, clamp | ran 2026-11-06 (job 3702947: 10 s in 39 min, ~47 ms/step) |
| 2 | free stream as SoRoLily: boundary conditions, angle schedule, u = U at start | implemented, not yet run (30× water) |
| 2b | water viscosity (μ = 1e-3), `CENTERED` | ran (job 3708249): reached 10 s (IB2d went NaN below 30×), but grid-scale noise everywhere: central differences at cell Re ≈ 1250 |
| 2c | `CUI` advection at 30× and 1× water | next (user, 2026-11-10) |
| 3 | per-step diagnostics in C++; comparison with IB2d | — |

## 5. Decisions log

| date | decision | what it means, and why |
|---|---|---|
| 2026-11-06 | **Cases live in fish-ibamr; the IB2d Python is copied** (`Wing_Geom.py`, `wing_case.py`, `verify_structure.py`, `case_params.json`, `common/`), from fish-ib2d `9b21eda`. | The IBAMR version can evolve separately; the commit records where it came from. |
| 2026-11-06 | **First reproduce IB2d, then improve.** | Comparing IBAMR with IB2d on the same problem shows whether the port is right. Then each change toward SoRoLily can be judged on its own. |
| 2026-11-06 | **Stage 1: the wing alone in still fluid**, then add the forcing. | Tests the geometry, the unit conversion, the springs and the clamp without the free stream. |
| 2026-11-06 | **Run length 10 s**, as in IB2d. | Same length as the IB2d runs (50,000 steps at dt = 2e-4). |
| 2026-11-09 | **Match SoRoLily wherever IBAMR can** (replaces "reproduce IB2d first"). | IB2d's differences from SoRoLily were workarounds for its limits; SoRoLily is the reference. |
| 2026-11-10 | **Advection `CUI`.** | Bounded upwind-biased scheme of the same family as SoRoLily's limited QUICK; central differences (IB2d's) left grid-scale noise at water viscosity (stage 2b). |
| 2026-11-09 | **Free stream as SoRoLily: prescribed on all four faces**, no fringe or controller. | A periodic box (IB2d) wraps the wake back round and can't drive a flow from its edges. A box with real edges lets the faces set the flow, as SoRoLily does. |

## 6. Run times (10 s of simulated time, 50,000 steps)

| run | code | μ | advection | node (CPU) | cores | simulation wall time | ms/step | source |
|---|---|---|---|---|---|---|---|---|
| Nx192_mu30w (stage 4) | IB2d | 30× | central | scotia07 (Silver 4510) | 1 | 20 min | 24.5 | run record |
| Nx384_mu30w | IB2d | 30× | central | scotia07 (Silver 4510) | 1 | 2 h | 145 | run record (Nx 384) |
| Nx192 at 10×, 3×, 1× | IB2d | — | central | scotia07 | 1 | diverged at 0.65, 0.50, 0.45 s | — | run records |
| naca_3702947 (still fluid, periodic) | IBAMR | 30× | CENTERED | damnii09 (Silver 4114) | 4 | ~30 min | ~36 | estimate: job total − ~8.5 min copy + movie |
| mu30x_centered_3708201 | IBAMR | 30× | CENTERED | scotia06 (Silver 4510) | 4 | ~14 min | ~17 | estimate (as above) |
| mu1x_centered_3708249 | IBAMR | 1× | CENTERED | saxa (Gold 6542Y) | 4 | ~13 min | ~16 | estimate (as above) |
| mu30x_cui_3710111 | IBAMR | 30× | CUI | scotia05 (Silver 4510) | 4 | 15.5 min | 18.6 | run record |
| mu1x_cui_3710112 | IBAMR | 1× | CUI | damnii09 (Silver 4114) | 4 | 36 min | 43.6 | run record |

On the same CPU (scotia, Silver 4510), IBAMR on 4 cores is ~1.3-1.4× faster in wall time than IB2d on 1 core, so per core IB2d is ~3× cheaper on this small grid. The node changes IBAMR's time by ~2.3× (damnii vs scotia), so compare like with like; a benchmark should pin one node type.
