# NACA0020 wing in IBAMR: implementation decisions

**Purpose.** Port the IB2d NACA0020 case (fish-ib2d `cases/NACA0020_Wing`,
copied at commit `9b21eda`) to IBAMR's IBMethod (springs and target points, 2D).
The reference is SoRoLily (see the IB2d case's `IMPLEMENTATION_DECISIONS.md`).

**Plan (user, 2026-11-06).**
1. Reproduce the IB2d setup as closely as possible, so IBAMR and IB2d can be compared on the same problem.
2. Then improve the rows where IB2d could not match SoRoLily (water viscosity first).

**Ground rule: the user decides every aspect of the setup.** Rows marked
**[default]** were chosen by Claude to follow the plan and still await review;
rows marked **D** keep an IBAMR default whose IB2d equivalent is unchecked.

## 1. Status codes

| code | meaning |
|---|---|
| **M** | matched: same value or same model as IB2d |
| **A** | approximated: IBAMR does it differently; the difference is given |
| **D** | IBAMR default kept; the IB2d equivalent is not yet checked |
| **—** | not in this stage |

## 2. Comparison table: IB2d → IBAMR

### 2.1 Fluid and domain

| quantity | IB2d (9b21eda) | IBAMR (this case) | status | notes |
|---|---|---|---|---|
| fluid density | `rho = 1000` | `RHO = 1000` | M | |
| viscosity | 30× water, `mu = 0.030069` | `MU = 0.030069` | M | water comes in plan step 2 |
| domain | 1.2 × 1.2 m, doubly periodic | `Lx = 1.2`, `periodic_dimension = 1,1` | M | |
| grid | `Nx = 192`, dx = 6.25 mm = chord/32 | `Nx = 192`, `MAX_LEVELS = 1` (no AMR) | M | |
| free stream | fringe + mean-flow controller, 0.02 s start-up ramp | none (still fluid) | — | stage 1 tests the structure alone; forcing comes in stage 2 |
| advection | central differences, skew-symmetric | `CENTERED`, `SKEW_SYMMETRIC` | M | IBAMR's usual choice is upwind `PPM`; plan step 2 |
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

## 3. Stages

| stage | what | status |
|---|---|---|
| 1 | pre-bent wing released in still fluid: geometry, units, springs, clamp | implemented, not yet run |
| 2 | free-stream forcing (fringe, controller, angle-of-attack schedule) | — |
| 3 | per-step diagnostics in C++; comparison with IB2d | — |

## 4. Decisions log

| date | decision | what it means, and why |
|---|---|---|
| 2026-11-06 | **Cases live in fish-ibamr; the IB2d Python is copied** (`Wing_Geom.py`, `wing_case.py`, `verify_structure.py`, `case_params.json`, `common/`), from fish-ib2d `9b21eda`. | The IBAMR version can evolve separately; the commit records where it came from. |
| 2026-11-06 | **First reproduce IB2d, then improve.** | Comparing IBAMR with IB2d on the same problem shows whether the port is right. Then each change toward SoRoLily can be judged on its own. |
| 2026-11-06 | **Stage 1: the wing alone in still fluid**, then add the forcing. | Tests the geometry, the unit conversion, the springs and the clamp without the free stream. |
| 2026-11-06 | **Run length 10 s**, as in IB2d. | Same length as the IB2d runs (50,000 steps at dt = 2e-4). |
