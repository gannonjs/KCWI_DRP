from keckdrpframework.primitives.base_primitive import BasePrimitive
from keckdrpframework.models.arguments import Arguments

import math


class CalcPrelimDisp(BasePrimitive):
    """Calculate dispersion based on configuration parameters"""

    def __init__(self, action, context):
        BasePrimitive.__init__(self, action, context)
        self.logger = context.pipeline_logger

    def _perform(self):
        # get binning
        y_binning = self.action.args.ybinsize
        # 0 - compute alpha
        preliminary_alpha = self.action.args.grangle - 13.0 - self.action.args.adjang
        # 1 - compute preliminary angle of diffraction
        preliminary_beta = self.action.args.camangle - preliminary_alpha
        # 2 - compute preliminary dispersion
        preliminary_dispersion = math.cos(preliminary_beta/math.degrees(1.)) / \
            self.action.args.rho / self.config.instrument.FCAM * \
            (self.config.instrument.PIX*y_binning) * 1.e4
        preliminary_dispersion *= math.cos(
            self.config.instrument.GAMMA/math.degrees(1.))
        self.logger.info("Initial alpha, beta (deg): %.3f, %.3f" %
                         (preliminary_alpha, preliminary_beta))
        self.logger.info("Initial calculated dispersion (A/binned pix): %.3f" %
                         preliminary_dispersion)
        self.context.prelim_disp = preliminary_dispersion

        log_string = CalcPrelimDisp.__module__ + "." + CalcPrelimDisp.__qualname__
        self.action.args.ccddata.header['HISTORY'] = log_string
        self.logger.info(log_string)

        return self.action.args
    # END: class CalcPrelimDisp()

