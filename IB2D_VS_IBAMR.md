# IB2d vs IBAMR: what changes

Both use the immersed boundary (IB) method: Lagrangian points carry the structure's forces, and a delta function spreads them onto the Eulerian fluid grid and interpolates the fluid velocity back. IBAMR's **IBMethod** uses the same structure model as IB2d (points, springs, beams, target points). Most other things differ. Facts below are for IBAMR 0.19.0 and the IB2d version pinned in fish-ib2d.

## At a glance

| | IB2d | IBAMR |
|---|---|---|
| **What it is** | Python (or MATLAB) scripts | C++ library. Each case is your own small C++ program, `example.cpp`, compiled and linked against IBAMR |
| **Running a case** | edit `input2d`, run `python main2d.py` | compile once (`cmake`), then `mpirun -np N ./main2d input2d`. Recompile only when the C++ changes |
| **Input file** | flat `key = value  % comment` | nested blocks (`Name { ... }`), `//` comments, variables and arithmetic allowed |
| **Install** | `pip install` a few packages | a stack: MPI → PETSc → SAMRAI (+ HDF5, Silo, Boost; libMesh optional) → IBAMR. The `autoibamr` script builds it all (~1 h) |
| **Parallel** | 1 core | MPI over many processes: Slurm `--ntasks=N`, then `mpirun -np N` |
| **Fluid grid** | one uniform grid | SAMRAI patches, with optional adaptive refinement (`MAX_LEVELS = 1` = uniform, as in IB2d) |
| **Boundaries** | doubly periodic only | periodic, walls, inflow/outflow (per face) |
| **Pressure solve** | FFT projection | staggered-grid Krylov solvers (PETSc/hypre) |
| **Advection** | central differences, skew-symmetric, fixed | a setting: `PPM` (upwind, the usual choice), `CENTERED` (as IB2d), `CUI`, … |
| **Time stepping** | fixed scheme | settings: advection (Adams–Bashforth default), viscosity (Crank–Nicolson default), structure (midpoint rule default) |
| **Delta function** | Peskin 4-point | a choice: `IB_3`, `IB_4` (= IB2d's), `IB_6`, B-splines, … |
| **Customising** | Python hooks: user forces, external forcing, moving targets | C++ in `example.cpp`: register force functions, body forces, extra output |
| **Output** | VTK files, one per field and frame | VisIt formats: fluid in SAMRAI/HDF5 (`dumps.visit`), structure in Silo (`lag_data.visit`), one file per MPI process. Plus whatever `example.cpp` writes |
| **Viewing output** | VisIt, ParaView or Python on the VTK files | VisIt (it stitches the per-process files); Python needs custom readers |
| **Restarts** | — | built in (`restart_dump_interval`) |
| **Other structure models** | — | IBFE (finite-element solid, needs libMesh), CIB/ConstraintIB (rigid or prescribed bodies), IIM (surfaces), … |

## Traps when porting a model

- **Stiffness units differ by ds.** IB2d treats Lagrangian forces as densities and spreads `f · ds`, with a *global* ds = Lx / (2 Nx). So its files hold K_phys / ds. IBAMR spreads plain nodal forces ("values, NOT densities", `ibtk/LEInteractor.h`), so its files hold K_phys = K_IB2d × ds. The spring law is the same, F = K (|D| − L).
- **The 5th column of `.spring` means something else.** In IB2d it's a nonlinearity degree. In IBAMR it's a force-function index, so drop it.
- **Everything else in the structure files carries over:** `.vertex`, `.spring` (4 columns), `.target`, zero-based indices.
- **Hooks become C++.** Anything IB2d did through Python while the simulation runs needs C++ in IBAMR. Geometry generation and post-processing can stay Python.
- **"IB2d" in IBAMR's output names** (`viz_IB2d/`, `IB2d.log`) means "IB in 2D". It has nothing to do with the IB2d code.

## On the ICF cluster (our setup)

- **Install:** IBAMR is installed in `~/autoibamr`, built by `fish-ibamr/install/build_ibamr.sbatch`. libMesh is off until `libtirpc-dev` (the XDR headers) is installed, because IBAMR requires libMesh *with* XDR.
- **AVX-512 nodes only:** PETSc's downloaded OpenBLAS is tuned to the build node's CPU (AVX-512), so runs must avoid the `landonia` nodes: `--exclude=landonia[03,05,08,11,21,23,25],crannog03,damnii10`. `install/probe_avx512.sh` rechecks the nodes.
- **Compile on a compute node,** with `--cpus-per-task` for the parallel build. Run with `--ntasks` for MPI.
- **Movies:** VisIt is unpacked in `~/opt/visit`. `ibamr_examples/make_vorticity_movie.py` renders vorticity in SoRoLily's colours.
