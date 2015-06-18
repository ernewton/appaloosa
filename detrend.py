'''
Hold the detrending method(s) to use.

1) Write a sliding local polynomial smoother
2) translate softserve (?)

'''
import numpy as np
from pandas import rolling_median, rolling_mean
from scipy.optimize import curve_fit
from gatspy.periodic import LombScargleFast
from scipy import signal


def rolling_poly(time, flux, error, order=3, window=0.5):
    '''
    Fit polynomials in a sliding window
    Name convention meant to match the pandas rolling_ stats

    Parameters
    ----------
    time : 1-d numpy array
    flux : 1-d numpy array
    error : 1-d numpy array
    order : int, optional
    window : float, optional

    Returns
    -------
    '''

    # This is SUPER slow... maybe useful in some places (LLC only?).
    # Can't be sped up much w/ indexing, because needs to move fixed
    # windows of time...

    smo = np.zeros_like(flux)

    w1 = np.where((time >= time[0] + window / 2.0) &
                  (time <= time[-1] + window / 2.0 ))[0]

    for i in range(0,len(w1)):
        x = np.where((time[w1] >= time[w1][i] - window / 2.0) &
                     (time[w1] <= time[w1][i] + window / 2.0))

        fit = np.polyfit(time[w1][x], flux[w1][x], order,
                          w = (1. / error[w1][x]) )

        smo[w1[i]] = np.polyval(fit, time[w1][i])

    return smo


def GapFlat(time, flux, order=3):
    '''

    Parameters
    ----------

    Returns
    -------
    '''
    _, dl, dr = FindGaps(time) # finds right edge of time windows

    tot_med = np.median(flux) # the total from all quarters

    flux_flat = np.array(flux, copy=True)

    for i in range(0, len(dl)):
        krnl = float(dl[i]-dr[i]) / 100.0
        if (krnl < 10.0):
            krnl = 10.0
        flux_sm = rolling_median(flux[dl[i]:dr[i]], krnl)

        indx = np.isfinite(flux_sm)

        fit = np.polyfit(time[dl[i]:dr[i]][indx], flux_sm[indx], order)

        flux_flat[dl[i]:dr[i]] = flux[dl[i]:dr[i]] - \
                                 np.polyval(fit, time[dl[i]:dr[i]]) + \
                                 tot_med
    return flux_flat


def QtrFlat(time, flux, qtr, order=3):
    '''
    step thru each unique qtr
    fit 2nd order poly to smoothed version of qtr
    return flat lc

    ignore long/short cadence, deal with on front end
    '''

    uQtr = np.unique(qtr)

    tot_med = np.median(flux) # the total from all quarters

    flux_flat = np.ones_like(flux) * tot_med

    for q in uQtr:
        # find all epochs within each Qtr, but careful w/ floats
        x = np.where( (np.abs(qtr-q) < 0.1) )

        krnl = float(len(x[0])) / 100.0
        if (krnl < 10.0):
            krnl = 10.0

        flux_sm = rolling_median(flux[x], krnl)

        indx = np.isfinite(flux_sm) # get rid of NaN's put in by rolling_median.

        fit = np.polyfit(time[x][indx], flux_sm[indx], order)

        flux_flat[x] = flux[x] - np.polyval(fit, time[x]) + tot_med

    return flux_flat


def FindGaps(time, maxgap=0.125, minspan=3.0):
    '''

    Parameters
    ----------

    Returns
    -------
    '''
    # assumes data is already sorted!
    dt = time[1:] - time[:-1]
    gap = np.where((dt >= maxgap))[0]

    # remove gaps that are too close together

    # add start/end of LC to loop over easily
    gap_out = np.append(0, np.append(gap, len(time)))

    right = np.append(gap + 1, len(time)) # right end of data
    left = np.append(0, gap + 1) # left start of data

    return gap_out, left, right


def _sinfunc(t, per, amp, t0, yoff):
    return np.sin((t - t0) * 2.0 * np.pi / per) * amp  + yoff


def FitSin(time, flux, error, maxnum=5, nper=20000,
           minper=0.1, maxper=30.0, plim=0.1,
           debug=False):
    '''

    Parameters
    ----------
    time:
    flux:
    error:
    maxnum:
    nper:
    minper:
    maxper:
    plim:
    debug:

    Returns
    -------
    '''
    _, dl, dr = FindGaps(time) # finds right edge of time windows

    # minper = 0.1 # days
    # maxper = 30. # days

    periods = np.linspace(minper, maxper, nper)

    flux_out = np.array(flux, copy=True)
    sin_out = np.zeros_like(flux) # return the sin function!

    # now loop over every chunk of data and fit N periods
    for i in range(0, len(dl)):
        # total baseline of time window
        dt = max(time[dl[i]:dr[i]]) - min(time[dl[i]:dr[i]])

        if debug is True:
            print('window (i): '+str(i)+'.  time span (dt):'+str(dt))

        medflux = np.median(flux[dl[i]:dr[i]])
        ti = time[dl[i]:dr[i]]

        for k in range(0, maxnum):
            # Use Jake Vanderplas faster version!
            pgram = LombScargleFast(fit_offset=False)
            pgram.optimizer.set(period_range=(minper,maxper))
            pgram = pgram.fit(time[dl[i]:dr[i]],
                              flux_out[dl[i]:dr[i]] - medflux,
                              error[dl[i]:dr[i]])

            df = (1./minper - 1./maxper) / nper
            f0 = 1./maxper
            pwr = pgram.score_frequency_grid(f0, df, nper)

            freq = f0 + df * np.arange(nper)
            per = 1./freq

            pok = np.where((per < dt) & (per > minper))
            pk = per[pok][np.argmax(pwr[pok])]
            pp = np.max(pwr)

            if debug is True:
                print('trial (k): '+str(k)+'.  peak period (pk):'+str(pk)+
                      '.  peak power (pp):'+str(pp))

            if (pp > plim):
                # fit sin curve to window and subtract
                p0 = [pk, 3.0 * np.nanstd(flux_out[dl[i]:dr[i]]-medflux), 0.0, 0.0]
                try:
                    pfit, pcov = curve_fit(_sinfunc, ti, flux_out[dl[i]:dr[i]]-medflux, p0=p0)
                except RuntimeError:
                    pfit = [pk, 0., 0., 0.]
                    if debug is True:
                        print('Curve_Fit no good')

                flux_out[dl[i]:dr[i]] = flux_out[dl[i]:dr[i]] - _sinfunc(ti, *pfit)
                sin_out[dl[i]:dr[i]] = sin_out[dl[i]:dr[i]] + _sinfunc(ti, *pfit)

        # add the median flux for this window BACK in
        sin_out[dl[i]:dr[i]] = sin_out[dl[i]:dr[i]] + medflux

    return sin_out


def MultiBoxcar(time, flux, error, numpass=3, kernel=2.0,
                sigclip=5, pcentclip=5, returnindx=False,
                debug=False):
    '''

    Parameters
    ----------
    time : numpy array
    flux : numpy array
    error : numpy array
    numpass : int, optional
        the number of passes to make over the data. (Default is 3)
    kernel : float, optional
        the boxcar size in hours. (Default is 2.0)
    sigclip : int, optional
        Number of times the standard deviation to clip points at
        (Default is 5)

    Returns
    -------
    The smoothed light curve
    '''

    _, dl, dr = FindGaps(time) # find edges of time windows

    flux_sm = np.array(flux, copy=True)
    # time_sm = np.array(time, copy=True)
    # error_sm = np.array(error, copy=True)

    # for returnindx = True
    indx_out = []

    for i in range(0, len(dl)):
        # the data within each gap range
        time_i = time[dl[i]:dr[i]]
        flux_i = flux[dl[i]:dr[i]]
        error_i = error[dl[i]:dr[i]]
        indx_i = np.arange(dl[i], dr[i]) # for tracking final indx used

        exptime = np.median(time_i[1:]-time_i[:-1])
        nptsmooth = int(kernel/24.0 / exptime)
        if debug is True:
            print('i = '+str(i))
            print('# of smoothing points: '+str(nptsmooth))

        if (nptsmooth < 4):
            nptsmooth = 4

        # now take N passes of rejection on it
        for k in range(0, numpass):
            # rolling median in this data span with the kernel size
            flux_i_sm = rolling_median(flux_i, nptsmooth, center=True)
            indx = np.isfinite(flux_i_sm)

            diff_k = (flux_i[indx] - flux_i_sm[indx])
            lims = np.percentile(diff_k, (pcentclip, 100-pcentclip))

            # iteratively reject points
            # keep points within sigclip (for phot errors), or
            # within percentile clip (for scatter)
            ok = np.logical_or((np.abs(diff_k / error_i[indx]) < sigclip),
                               (lims[0] < diff_k) * (diff_k < lims[1]))

            if debug is True:
                print('k = '+str(k))
                print('number of accepted points: '+str(len(ok[0])))

            time_i = time_i[indx][ok]
            flux_i = flux_i[indx][ok]
            error_i = error_i[indx][ok]
            indx_i = indx_i[indx][ok]

        flux_sm[dl[i]:dr[i]] = np.interp(time[dl[i]:dr[i]], time_i, flux_i)

        indx_out = np.append(indx_out, indx_i)

    if returnindx is False:
        return flux_sm
    else:
        return np.array(indx_out, dtype='int')
