// IBMethod with the added elastic force in the interpolation of structure point velocity:
// U^{n+1/2} = J u^{n+1/2} + alpha F^{n+1/2},  alpha in 1/(Pa s) (2D)
// --> set alpha=0 to return to original IBMethod

#ifndef included_NewInterpolatorIBMethod
#define included_NewInterpolatorIBMethod

#include <ibamr/IBMethod.h>

#include <ibtk/IBTK_CHKERRQ.h>
#include <ibtk/LData.h>
#include <ibtk/LDataManager.h>
#include <ibtk/ibtk_utilities.h>

#include <petscvec.h>

#include <string>
#include <utility>
#include <vector>

class NewInterpolatorIBMethod : public IBAMR::IBMethod // create subclass
{
public:
    NewInterpolatorIBMethod(std::string object_name, SAMRAI::tbox::Pointer<SAMRAI::tbox::Database> input_db, double alpha)
        : IBMethod(std::move(object_name), input_db), d_alpha(alpha)
    {
    }

    void interpolateVelocity(
        int u_data_idx,
        const std::vector<SAMRAI::tbox::Pointer<SAMRAI::xfer::CoarsenSchedule<NDIM>>>& u_synch_scheds,
        const std::vector<SAMRAI::tbox::Pointer<SAMRAI::xfer::RefineSchedule<NDIM>>>& u_ghost_fill_scheds,
        double data_time) override
    {
        IBMethod::interpolateVelocity(u_data_idx, u_synch_scheds, u_ghost_fill_scheds, data_time);

        // Only run the rest if at half time (B4 interpolation). C1 (new_time) must stay plain J u.
        // Outside a step d_half_time is NaN, so this also returns early then.
        if (d_alpha == 0.0 || !IBTK::rel_equal_eps(data_time, d_half_time)) return;

        for (int ln = 0; ln <= d_hierarchy->getFinestLevelNumber(); ++ln) // loop over grid levels
        {
            if (!d_l_data_manager->levelContainsLagrangianData(ln)) continue;
            Vec F_vec = d_F_half_data[ln]->getVec(); // F^{n+1/2} from B1 force calculation
            int ierr = VecAXPY(d_U_half_data[ln]->getVec(), d_alpha, F_vec); // U_half += alpha*F_half
            IBTK_CHKERRQ(ierr);
        }
    }

private:
    double d_alpha;
};

#endif