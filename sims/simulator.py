
import os
from copy import deepcopy
from simtbx.diffBragg.utils import ENERGY_CONV
from dxtbx.model import Detector, Panel
import numpy as np
from scipy.spatial.transform import Rotation

from simtbx.nanoBragg import sim_data
from dials.array_family import flex


from resonet.sims import make_sims, make_crystal, paths_and_const


class Simulator:

    def __init__(self, DET, BEAM, cuda=True, verbose=False):
        self.DET = DET
        self.BEAM = BEAM
        # air and water background:
        self.air_and_water = make_sims.get_background(self.DET, self.BEAM)
        # stol of every pixel:
        self.STOL = make_sims.get_theta_map(self.DET, self.BEAM)

        self.nb_beam = make_crystal.load_beam(self.BEAM,
                                      divergence=paths_and_const.DIVERGENCE_MRAD / 1e3 * 180 / np.pi)
        self.cuda=cuda
        self.verbose = verbose

    def simulate(self, rot_mat=None, multi_lattice_chance=0, max_lat=2, mos_min_max=None,
                 pdb_name=None, plastic_stol=None, dev=0, mos_dom_override=None, vary_background_scale=False,
                 randomize_dist=False, randomize_wavelen=False, randomize_center=None):
        """

        :param rot_mat: specific orientation matrix for crystal
        :param multi_lattice_chance:  probabilitt to include more lattices
        :param num_lat: number of lattices (in the event a multiple lattice shot is simulated)
        :param mos_min_max: values for determing the size of the mosaic spread. Should be lower, upper bounds given in degrees 
        :param pdb_name: path to the pdb folder (for debug purposes).
        :param plastic_stol: path to the plastic `sin theta over lambda` file (debug purposes only)
        :param dev: device id (number from 0 to N-1 where N is number of nvidia GPUs available (run nvidia-smi to check)
        :param mos_dom_override: number of mosaic blocks to simulate. If not, will be determined via make_sims.choose_mos function. 
        :return: parameters and simulated image
        """
        if pdb_name is None:
            pdb_name = make_sims.choose_pdb()
        else:
            assert os.path.exists(pdb_name)
            assert os.path.isdir(pdb_name)
        C = make_crystal.load_crystal(pdb_name, rot_mat)
        mos_min = mos_max = None  # will default to values in paths_and_const.py
        if mos_min_max is not None:
            mos_min, mos_max = mos_min_max

        mos_spread, mos_dom = make_sims.choose_mos(mos_min, mos_max)
        C.mos_spread_deg = mos_spread

        if mos_dom_override is not None:
            mos_dom = mos_dom_override
        n_mos = mos_dom//2
        if n_mos % 2 == 1:
            n_mos += 1
        C.n_mos_domains = n_mos

        S = sim_data.SimData()
        S.crystal = C

        if randomize_dist or randomize_center or randomize_wavelen:
            shot_beam = deepcopy(self.BEAM)
            if randomize_wavelen:
                energy_ev = np.random.uniform(10000,13000)
                shot_wavelen = ENERGY_CONV / energy_ev
                shot_beam.set_wavelength(shot_wavelen)

            shot_det = deepcopy(self.DET)
            if randomize_dist:
                curr_dist = self.DET[0].get_distance()
                new_dist = np.random.uniform(200, 300)
                dist_shift = new_dist - curr_dist
                shot_det = shift_distance(shot_det, dist_shift)

            if randomize_center:
                cent_window_mm = 10  # millimeters
                cent_window_pix = int(cent_window_mm/shot_det[0].get_pixel_size()[0])
                new_cent_x, new_cent_y = np.random.uniform(-cent_window_pix, cent_window_pix, 2)
                shot_det = shift_center(shot_det, new_cent_x, new_cent_y)

            air_and_water = make_sims.get_background(shot_det, shot_beam)
            # stol of every pixel:
            STOL = make_sims.get_theta_map(shot_det, shot_beam)

            nb_beam = make_crystal.load_beam(shot_beam,
                                          divergence=paths_and_const.DIVERGENCE_MRAD / 1e3 * 180 / np.pi)

        else:
            air_and_water = self.air_and_water
            STOL = self.STOL
            nb_beam = self.nb_beam
            shot_beam = self.BEAM
            shot_det = self.DET

        S.beam = nb_beam
        S.detector = shot_det
        S.instantiate_nanoBragg(oversample=1)

        if self.verbose:
            S.D.show_params()
            print("Simulating spots!", flush=True)
        if self.cuda:
            S.D.device_Id = dev
            S.D.add_nanoBragg_spots_cuda()
        else:
            S.D.add_nanoBragg_spots()
        spots = S.D.raw_pixels.as_numpy_array()
        use_multi = np.random.random() < multi_lattice_chance
        ang_sigma = 0
        num_additional_lat = 0
        if use_multi:
            num_additional_lat = np.random.choice(range(1,max_lat))
            mats = Rotation.random(num_additional_lat).as_matrix()
            vecs = np.dot(np.array([1, 0, 0])[None], mats)[0]
            #std_angs = 0
            #while (std_angs < 3):
            angs = np.random.uniform(1, 180, num_additional_lat)
            #    std_angs = np.std(angs)
            ang_sigma = np.std(np.append(angs,[0]))
            scaled_vecs = vecs*angs[:, None]
            rot_mats = Rotation.from_rotvec(scaled_vecs).as_matrix()

            nominal_crystal = S.crystal.dxtbx_crystal
            Umat = np.reshape(nominal_crystal.get_U(), (3, 3))
            for i_p, perturb in enumerate(rot_mats):
                if self.verbose:
                    print("additional multi lattice sim %d" % (i_p+1), flush=True)
                Umat_p = np.dot(perturb, Umat)
                nominal_crystal.set_U(tuple(Umat_p.ravel()))
                S.D.Amatrix = sim_data.Amatrix_dials2nanoBragg(nominal_crystal)

                S.D.raw_pixels *= 0
                if self.cuda:
                    S.D.add_nanoBragg_spots_cuda()
                else:
                    S.D.add_nanoBragg_spots()

                spots += S.D.raw_pixels.as_numpy_array()
            spots /= (num_additional_lat+1)

        if self.verbose:
            print("sim random bg", flush=True)
        if plastic_stol is None:
            plastic_stol = np.random.choice(paths_and_const.RANDOM_STOLS)
        else:
            assert os.path.exists(plastic_stol)
        plastic = make_sims.random_bg(shot_det, shot_beam, plastic_stol)

        reso, Bfac_img = make_sims.get_Bfac_img(STOL)

        bg = air_and_water + plastic
        bg_scale = 1
        if vary_background_scale:
            #low_bg_scale = np.random.choice([0.0125, 0.025, 0.05, 0.1, 0.25])
            #norm_bg_scale = np.random.choice([1, 1.25])
            #is_low_bg = np.random.random() < 2/7.  # 2 out of 7 datasets are collected in low background mode
            #bg_scale = low_bg_scale if is_low_bg else norm_bg_scale
            bg_scale = np.random.choice([0.0125, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 1.25])
            if self.verbose:
                print("Scaling background by %.3f" % bg_scale)

        img = spots*Bfac_img*paths_and_const.VOL + bg*bg_scale

        make_sims.set_noise(S.D)

        S.D.raw_pixels = flex.double(img.ravel())
        S.D.add_noise()
        noise_img = S.D.raw_pixels.as_numpy_array().reshape(img.shape)

        param_dict = {"reso": reso,
                      "multi_lattice": use_multi,
                      "ang_sigma": ang_sigma,
                      "bg_scale": bg_scale,
                      "num_lat": num_additional_lat+1,
                      "wavelength": nb_beam.spectrum[0][0],
                      "detector_distance": S.detector[0].get_distance(),
                      "beam_center": S.detector[0].get_beam_centre_px(nb_beam.unit_s0)}

        S.D.free_all()

        return param_dict, noise_img


def reso2radius(reso, DET, BEAM):
    """

    :param reso: resolution of a position on camera in Angstrom
    :param DET: dxtbx detector model
    :param BEAM: dxtbx beam model
    :return: the resolution converted to pixel radii (distance from beam center)
    """
    wavelen = BEAM.get_wavelength()
    detdist = abs(DET[0].get_distance())
    pixsize = DET[0].get_pixel_size()[0]  # assumes square pixel

    theta = np.arcsin(wavelen/2/reso)
    rad = np.tan(2*theta) * detdist/pixsize
    return rad


def shift_center(det, delta_x, delta_y):
    """
    :param det: dxtbx detector model (single panel)
    :param delta_x: beam center shift in pixels (fast dim)
    :param delta_y: beam center shift in pixels (slow dim)
    :return: dxtbx detector model with shifted center
    """
    dd = det[0].to_dict()
    F = np.array(dd["fast_axis"])
    S = np.array(dd["slow_axis"])
    O = np.array(dd['origin'])
    pixsize = det[0].get_pixel_size()[0]
    O2 = O + F * pixsize * delta_x + S * pixsize * delta_y
    dd["origin"] = tuple(O2)
    new_det = Detector()
    new_pan = Panel.from_dict(dd)
    new_det.add_panel(new_pan)
    return new_det

def shift_distance(det, delta_z):
    """
    :param det: dxtbx detector model (single panel)
    :param delta_z: distance shift in millimeters
    :return: dxtbx detector model with shifted center
    """
    dd = det[0].to_dict()
    F = np.array(dd["fast_axis"])
    S = np.array(dd["slow_axis"])
    O = np.array(dd['origin'])
    Orth = np.cross(F,S)
    O2 = O + Orth*delta_z
    dd["origin"] = tuple(O2)
    new_det = Detector()
    new_pan = Panel.from_dict(dd)
    new_det.add_panel(new_pan)
    return new_det
