from keckdrpframework.primitives.base_img import BaseImg
from kcwidrp.primitives.kcwi_file_primitives import kcwi_fits_reader, \
    kcwi_fits_writer
from kcwidrp.core.bokeh_plotting import bokeh_plot
from kcwidrp.core.bspline import Bspline
from bokeh.plotting import figure
from bokeh.models import Range1d

import os
import time
import numpy as np


class MakeMasterSky(BaseImg):
    """Make master sky image"""

    def __init__(self, action, context):
        BaseImg.__init__(self, action, context)
        self.logger = context.pipeline_logger

    def _pre_condition(self):
        """
        Checks if we can create a master sky
        :return:
        """
        return True

    def _perform(self):
        """
        Returns an Argument() with the parameters that depends on this operation
        """
        self.logger.info("Creating master sky")

        suffix = self.action.args.new_type.lower()

        # get root for maps
        tab = self.context.proctab.n_proctab(
            frame=self.action.args.ccddata, target_type='ARCLAMP',
            target_group=self.action.args.groupid)
        if len(tab) <= 0:
            self.logger.error("Geometry not solved!")
            return self.action.args

        mroot = tab['OFNAME'][0].split('.fits')[0]

        # Wavelength map image
        wmf = mroot + '_wavemap.fits'
        self.logger.info("Reading image: %s" % wmf)
        wavemap = kcwi_fits_reader(
            os.path.join(os.path.dirname(self.action.args.name), 'redux',
                         wmf))[0]

        # Slice map image
        slf = mroot + '_slicemap.fits'
        self.logger.info("Reading image: %s" % slf)
        slicemap = kcwi_fits_reader(
            os.path.join(os.path.dirname(self.action.args.name), 'redux',
                         slf))[0]

        # Position map image
        pof = mroot + '_posmap.fits'
        self.logger.info("Reading image: %s" % pof)
        posmap = kcwi_fits_reader(
            os.path.join(os.path.dirname(self.action.args.name), 'redux',
                         pof))[0]

        # wavelength region
        wavegood0 = wavemap.header['WAVGOOD0']
        wavegood1 = wavemap.header['WAVGOOD1']
        waveall0 = wavemap.header['WAVALL0']
        waveall1 = wavemap.header['WAVALL1']

        # get image size
        sm_sz = self.action.args.ccddata.data.shape

        # sky masking
        # default is no masking (True = good, False = Mask)
        binary_mask = np.ones(sm_sz, dtype=bool)

        # was sky masking requested?
        if self.config.instrument.skymask:
            binary_mask[0, 0] = False

        # count masked pixels
        tmsk = len(np.nonzero(np.where(binary_mask.flat, False, True))[0])
        self.logger.info("Number of pixels masked = %d" % tmsk)

        finiteflux = np.isfinite(self.action.args.ccddata.data.flat)

        # get un-masked points mapped to exposed regions on CCD
        q = [i for i, v in enumerate(slicemap.data.flat)
             if 0 <= v <= 23 and posmap.data.flat[i] >= 0 and
             waveall0 <= wavemap.data.flat[i] <= waveall1 and
             finiteflux[i] and binary_mask.flat[i]]

        # get all points mapped to exposed regions on the CCD (for output)
        qo = [i for i, v in enumerate(slicemap.data.flat)
              if 0 <= v <= 23 and posmap.data.flat[i] >= 0 and
              waveall0 <= wavemap.data.flat[i] <= waveall1 and
              finiteflux[i]]

        # extract relevant image values
        fluxes = self.action.args.ccddata.data.flat[q]

        # relevant wavelengths
        waves = wavemap.data.flat[q]
        self.logger.info("Number of fit waves = %d" % len(waves))

        # keep output wavelengths
        owaves = wavemap.data.flat[qo]
        self.logger.info("Number of output waves = %d" % len(owaves))

        # sort on wavelength
        s = np.argsort(waves)
        waves = waves[s]
        fluxes = fluxes[s]

        # knots per pixel
        knotspp = self.config.instrument.KNOTSPP
        n = int(sm_sz[0] * knotspp)

        # calculate break points for b splines
        bkpt = np.min(waves) + np.arange(n+1) * \
            (np.max(waves) - np.min(waves)) / n

        # log
        self.logger.info("Nknots = %d, min = %.2f, max = %.2f (A)" %
                         (n, np.min(bkpt), np.max(bkpt)))

        # do bspline fit
        sft0, gmask = Bspline.iterfit(waves, fluxes, fullbkpt=bkpt,
                                      upper=1, lower=1)
        gp = [i for i, v in enumerate(gmask) if v]
        yfit1, _ = sft0.value(waves)
        self.logger.info("Number of good points = %d" % len(gp))

        # check result
        if np.max(yfit1) < 0:
            self.logger.warning("B-spline failure")
            if n > 2000:
                if n == 5000:
                    n = 2000
                if n == 8000:
                    n = 5000
                # calculate breakpoints
                bkpt = np.min(waves) + np.arange(n + 1) * \
                    (np.max(waves) - np.min(waves)) / n
                # log
                self.logger.info("Nknots = %d, min = %.2f, max = %.2f (A)" %
                                 (n, np.min(bkpt), np.max(bkpt)))
                # do bspline fit
                sft0, gmask = Bspline.iterfit(waves, fluxes, fullbkpt=bkpt,
                                              upper=1, lower=1)
                yfit1, _ = sft0.value(waves)
            if np.max(yfit1) <= 0:
                self.logger.warning("B-spline final failure, sky is zero")

        # get values at original wavelengths
        yfit, _ = sft0.value(owaves)

        # for plotting
        gwaves = waves[gp]
        gfluxes = fluxes[gp]
        npts = len(gwaves)
        stride = int(npts / 5000.)
        xplt = gwaves[::stride]
        yplt = gfluxes[::stride]
        fplt, _ = sft0.value(xplt)
        self.logger.info("Stride = %d" % stride)

        # plot, if requested
        if self.config.instrument.plot_level >= 2:
            p = figure(
                title=self.action.args.plotlabel + ' Master Sky',
                x_axis_label='Wave (A)',
                y_axis_label='Flux (e-)',
                plot_width=self.config.instrument.plot_width,
                plot_height=self.config.instrument.plot_height)
            p.circle(xplt, yplt, size=1, line_alpha=0., fill_color='purple',
                     legend_label='Data')
            p.line(xplt, fplt, line_color='red', legend_label='Fit')
            bokeh_plot(p, self.context.bokeh_session)
            if self.config.instrument.plot_level >= 2:
                input("Next? <cr>: ")
            else:
                time.sleep(self.config.instrument.plot_pause)

        # create sky image
        sky = np.zeros(self.action.args.ccddata.data.shape, dtype=float)
        sky.flat[qo] = yfit

        # store original data, header
        img = self.action.args.ccddata.data
        hdr = self.action.args.ccddata.header.copy()
        self.action.args.ccddata.data = sky

        # get master flat output name
        ofn = self.action.args.ccddata.header['OFNAME']
        msname = ofn.split('.fits')[0] + '_' + suffix + '.fits'

        log_string = MakeMasterSky.__module__ + "." + \
            MakeMasterSky.__qualname__
        self.action.args.ccddata.header['IMTYPE'] = self.action.args.new_type
        self.action.args.ccddata.header['HISTORY'] = log_string
        self.action.args.ccddata.header['SKYMODEL'] = (True, 'sky model image?')
        self.action.args.ccddata.header['SKYIMAGE'] = \
            (ofn, 'image used for sky model')
        if tmsk > 0:
            self.action.args.ccddata.header['SKYMSK'] = (True,
                                                         'was sky masked?')
            # self.action.args.ccddata.header['SKYMSKF'] = (skymf,
            # 'sky mask file')
        else:
            self.action.args.ccddata.header['SKYMSK'] = (False,
                                                         'was sky masked?')
        self.action.args.ccddata.header['WAVMAPF'] = wmf
        self.action.args.ccddata.header['SLIMAPF'] = slf
        self.action.args.ccddata.header['POSMAPF'] = pof

        # output master sky
        kcwi_fits_writer(self.action.args.ccddata, output_file=msname)
        self.context.proctab.update_proctab(frame=self.action.args.ccddata,
                                            suffix=suffix,
                                            newtype=self.action.args.new_type)
        self.context.proctab.write_proctab()

        # restore original image
        self.action.args.ccddata.data = img
        self.action.args.ccddata.header = hdr

        self.logger.info(log_string)
        return self.action.args

    # END: class MakeMasterFlat()