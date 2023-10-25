
import os
import re
import glob
import pandas
from torch.utils.data import Dataset, DataLoader
import torch
import numpy as np
import h5py
from resonet.sims import paths_and_const

from PIL import Image


class PngDset(Dataset):

    def __init__(self, pngdir=None, propfile=None, quad="A", start=None, stop=None,
                 dev=None, invert_res=False, transform=None, convert_res=False, use_float=True,
                 reso_only_mode=True):
        """

        :param pngdir: path to folder resmos2 containing PNG files
        :param propfile: path to property file num_reso_mos_B_icy1_icy2_cell_SGnum_pdbid_stolid.txt
        :param quad: 'A','B','C' or 'D', image quadrant to use
        :param start: lower bound for range of PNGs to load
        :param stop: upper bound for range of PNGs to load
        :param dev: pytorch device string e.g.  'cuda:0'
        :param invert_res: whether to invert the resolution
        :param transform: whether to apply image transformations
        :param convert_res: whether to convert resolution labels to radii
        :param use_float: convert tensors to single precision. This is necessary for MSELoss
        :param reso_only_mode: labels only include resolution
        """
        if pngdir is None:
            pngdir = "."
        if propfile is None:
            propfile = "num_reso_mos_B_icy1_icy2_cell_SGnum_pdbid_stolid.txt"
        if dev is None:
            dev = "cuda:0"
        
        self.use_float = use_float

        self.transform = transform

        self.fnames = glob.glob(os.path.join(pngdir, "*%s.png" % quad))
        assert self.fnames
        self.nums = [self.get_num(f) for f in self.fnames]
        self.img_sh = 546, 518

        self.prop = pandas.read_csv(
            propfile,
            delimiter=r"\s+",
            names=["num", "reso", "mos", "B", "icy1", "icy2", "cell1", \
                   "cell2", "cell3", "SGnum", "pdbid", "stolid"])

        self.unique_pdb = self.prop.pdbid.unique()
        self.pdbid_map = {pdb: i for i,pdb in enumerate(self.unique_pdb)}
        self.prop.loc[:, "pdbid"] = [self.pdbid_map[pdb] for pdb in self.prop.pdbid]

        self.unique_stol = self.prop.stolid.unique()
        self.stolid_map = {stol: i for i,stol in enumerate(self.unique_stol)}
        self.prop.loc[:, "stolid"] = [self.stolid_map[stol] for stol in self.prop.stolid]

        self.prop["rad"] = self._convert_res2rad(self.prop.reso)
        self.prop["one_over_rad"] = 1/self.prop.rad
        self.prop["one_over_reso"] = 1/self.prop.reso

        if convert_res:
            self.prop.loc[:, "reso"] = self._convert_res2rad(self.prop.reso)

        if invert_res:
            self.prop.loc[:,"reso"] = 1/self.prop.reso

        self.reso_only_mode = reso_only_mode
        if reso_only_mode:
            self.labels = self.prop[["num", "reso"]]
        else:
            self.labels = self.prop
        self.dev = dev  # pytorch device ID

        Ntotal = len(self.fnames)
        if start is None:
            start = 0
        if stop is None:
            stop = Ntotal
        assert start >= 0
        assert stop <= Ntotal
        assert stop > start
        self.start = start
        self.stop = stop

    def _convert_res2rad(self, res):
        """
        :param res: resolutions (in Angstroms) from the resmos2 labels
        :return: corresponding radii
        """
        detdist = 200 # mm
        pixsize = 0.075 # mm
        pixsize = pixsize*4  # downsample term
        wavelen = 0.977794  # angstrom
        # from Braggs law, we know:
        theta = np.arcsin(wavelen*.5/res)

        # from trig we know
        rad = np.tan(2*theta)*detdist/pixsize
        return rad

    @staticmethod
    def get_num(f):
        s = re.search("sim_[0-9]{5}", f)
        num = f[s.start(): s.end()].split("sim_")[1]
        return int(num)

    @property
    def dev(self):
        return self._dev

    @dev.setter
    def dev(self, val):
        self._dev = val

    def __len__(self):
        return self.stop - self.start

    def __getitem__(self, i):
        assert self.dev is not None, "Set the dev (torch device) property first!"

        img = Image.open(self.fnames[i+self.start])
        img_dat = np.reshape(img.getdata(), self.img_sh).astype(np.float32)

        num = self.nums[i+self.start]
        img_lab = self.labels.query("num==%d" % num)
        if self.reso_only_mode:
            img_lab = img_lab.reso
        img_dat = torch.tensor(img_dat[:512,:512][None]).to(self.dev)
        img_lab = torch.tensor(img_lab.values).to(self.dev)
        # Apply image transform here
        if self.transform:
            img_dat = self.transform(img_dat)
        if self.use_float:
            img_dat = img_dat.float()
            img_lab = img_lab.float()
        return img_dat, img_lab


class H5SimDataDset(Dataset):

    def __init__(self, h5name, dev=None, labels="labels", images="images",
                 start=None, stop=None, label_sel=None, use_geom=False, transform=None,
                 half_precision=False, use_sgnums=False):
        """

        :param h5name: hdf5 master file written by resonet/scripts/merge_h5s.py
        :param dev: pytorch device
        :param labels: path to labels dataset
        :param images: path to images dataset
        :param start: dataset index to begin
        :param stop: dataset index to stop
        :param label_names: optional list of labels to select. This requires that the dataset
            specified by labels has names. this can alternatively be a list of numbers
            specifying the indices of the labels dataset
        :param use_geom: if the `geom` dataset exists, then use each iter should return 3-tuple (labels, images, geom)
            Otherwise, each iter returns 2-tuple (images,labels)
            The geom tensor can be used as a secondary input to certain models
        :param use_sgnums:
        """
        if label_sel is None:
            label_sel = [0]
        elif all([isinstance(l, str) for l in label_sel]):
            label_sel = self._get_label_sel_from_label_names(h5name, labels, label_sel)
        else:
            if not all([isinstance(l, int) for l in label_sel]):
                raise TypeError("label_sel should be all int or all str")
        self.nlab = len(label_sel)
        self.label_sel = label_sel
        self.labels_name = labels
        self.images_name = images
        self.h5name = h5name
        self.use_sgnums = use_sgnums
        self.transform = transform
        self.half_precision = half_precision
        self.has_geom = False  # if geometry is present in master file, it can be used as model input
        # open to get length quickly!
        with h5py.File(h5name, "r") as h:
            self.num_images = h[self.images_name].shape[0]
            self.has_geom = "geom" in list(h.keys())
        if use_geom and not self.has_geom:
            raise ValueError("Cannot use geometry if it is not present in the master files. requires `geom` dataset")
        self.use_geom = use_geom and self.has_geom

        self.dev = dev  # pytorch device ID
        if start is None:
            start = 0
        if stop is None:
            stop = self.num_images
        assert start >= 0
        assert stop <= self.num_images
        assert stop > start
        self.start = start
        self.stop = stop

        self.h5 = None  # handle for hdf5 file
        self.images = None  # hdf5 dataset
        self.labels = None  # hdf5 dataset
        self.geom = None  # hdf5 dataset
        self.ops_from_pdb = None
        self.pdb_id_to_num = None
        self.sgnums = None
        self._setup_sgmaps()

    def _setup_sgmaps(self):
        if not self.use_sgnums:
            return
        else:
            assert paths_and_const.SGOP_FILE is not None
            assert os.path.exists(paths_and_const.SGOP_FILE)
        self.ops_from_pdb = np.load(paths_and_const.SGOP_FILE, allow_pickle=True)[()]
        self.pdb_id_to_num = {k: i for i, k in enumerate(self.ops_from_pdb.keys())}

    @staticmethod
    def _get_label_sel_from_label_names(fname, dset_name, label_names):
        label_sel = []
        with h5py.File(fname, "r") as h:
            labels = h[dset_name]
            if "names" not in labels.attrs:
                raise KeyError("the dataset %s in file %s has no `names` attribute" % (dset_name, fname))
            names = list( labels.attrs["names"])
            for name in label_names:
                if name not in names:
                    raise ValueError("label name '%s' is not in 'names' attrs of  dset '%s' (in file %s)" % (name, dset_name, fname))
                idx = names.index(name)
                label_sel.append(idx)
        #TODO what about label_sel ordering?
        return label_sel

    def open(self):
        self.h5 = h5py.File(self.h5name, "r")
        self.images = self.h5[self.images_name]
        assert self.images.dtype in [np.float16, np.float32]
        if self.images.dtype!=np.float32:
            raise ValueError("Images should be type float32!")
        self.labels = self.h5[self.labels_name][:, self.label_sel]
        lab_dt = self.labels.dtype
        if not self.half_precision and lab_dt != np.float32:
            self.labels = self.labels.astype(np.float32)
        elif self.half_precision and lab_dt != np.float16:
            self.labels = self.labels.astype(np.float16)
        if self.use_geom:
            geom_dset = self.h5["geom"]
            self.geom = self.get_geom(geom_dset)
            geom_dt = self.geom.dtype
            if not self.half_precision and geom_dt!=np.float32:
                self.geom = self.geom.astype(np.float32)
            elif self.half_precision and geom_dt != np.float16:
                self.geom = self.geom.astype(np.float16)

        if self.use_sgnums:
            self.get_sgnums()

    def get_sgnums(self):
        pdbmap = {i: os.path.basename(f) for i,f in
                   enumerate(self.h5[self.labels_name].attrs['pdbmap'])}
        pdb_i = list(self.h5[self.labels_name].attrs['names']).index('pdb')
        pdb_id_per_img = [pdbmap[i] for i in self.h5['labels'][:, pdb_i].astype(int)]
        self.sgnums = [self.pdb_id_to_num[p] for p in pdb_id_per_img]

    def get_geom(self, geom_dset):
        ngeom = geom_dset.shape[-1]
        inds = list(range(ngeom))
        if "names" in geom_dset.attrs:
            names = list(geom_dset.attrs["names"])

            try:
                inds = [names.index("detdist"),
                        names.index('pixsize'),
                    names.index('wavelen'),
                    names.index("xdim"),
                    names.index("ydim")]
            except ValueError:
                pass
        geom = geom_dset[()][:, inds]
        return geom

    @property
    def dev(self):
        return self._dev

    @dev.setter
    def dev(self, val):
        self._dev = val

    def __len__(self):
        return self.stop - self.start

    def __getitem__(self, i):
        assert self.dev is not None
        if self.images is None:
            self.open()
        img_dat, img_lab = self.images[i + self.start], self.labels[i + self.start]
        if len(img_dat.shape) == 2:
            img_dat = img_dat[None]
        if self.half_precision and not self.images.dtype==np.float16:
            #print("Warning, converting images from float32 to float16. This could slow things down.")
            img_dat = img_dat.astype(np.float16)
        img_dat = torch.tensor(img_dat).to(self.dev)
        # if we are applying image augmentation
        if self.transform:
            img_dat = self.transform(img_dat)
        img_lab = torch.tensor(img_lab).to(self.dev)
        if self.use_geom:
            geom_inputs = self.geom[i+self.start]
            geom_inputs = torch.tensor(geom_inputs).to(self.dev)
            return img_dat, img_lab, geom_inputs
        elif self.use_sgnums:
            sgnums = self.sgnums[i+self.start]
            sgnums = torch.tensor(sgnums).to(self.dev)
            return img_dat, img_lab, sgnums
        else:
            return img_dat, img_lab

    def nlab(self):
        return self.nlab


class H5SimDataMPI(H5SimDataDset):

    def __init__(self, mpi_comm, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.com = mpi_comm

    def __getitem__(self, i):
        assert self.dev is not None
        img_dat, img_lab = self.images[i + self.start][None], self.labels[i + self.start]
        return img_dat, img_lab
        #img_dat = torch.tensor(img_dat).to(self.dev)
        #img_lab = torch.tensor(img_lab).to(self.dev)
        #return img_dat, img_lab


class H5Loader:
    def __init__(self, dset, comm, batch_size=8, shuffle=True):
        self.shuffle = shuffle
        self.dset = dset
        self.comm = comm
        self.bs = batch_size
        self.i_batch = 0  # batch counter
        self.samp_per_batch = None
        self.batch_data_holder = None
        self.batch_label_holder = None
        self._set_batches()

    def __iter__(self):
        return self

    def __next__(self):

        self.i_batch += 1
        if self.i_batch < len(self.samp_per_batch):
            return self.get_batch()
        else:
            self._set_batches()
            self.i_batch = 0
            raise StopIteration

    def _set_batches(self):
        nbatch = int(len(self.dset) / self.bs)

        if self.comm.rank == 0:
            batch_order = np.random.permutation(len(self.dset))
            self.samp_per_batch = np.array_split(batch_order, nbatch)
        self.samp_per_batch = self.comm.bcast(self.samp_per_batch)
        max_size = max([len(x) for x in self.samp_per_batch])
        self.batch_data_holder = np.zeros((max_size, 1, 512, 512))
        self.batch_label_holder = np.zeros((max_size, 1))

    def get_batch(self):
        assert self.i_batch < len(self.samp_per_batch)
        nsamp = len(self.samp_per_batch[self.i_batch])
        for ii, i in enumerate(self.samp_per_batch[self.i_batch]):
            if i % self.comm.size != self.comm.rank:
                continue
            data, label = self.dset[i]
            self.batch_data_holder[ii] = data
            self.batch_label_holder[ii] = label
        self.batch_data_holder = self._reduce_bcast(self.batch_data_holder)
        self.batch_label_holder = self._reduce_bcast(self.batch_label_holder)
        dat = torch.tensor(self.batch_data_holder[:nsamp])
        lab = torch.tensor(self.batch_label_holder[:nsamp])
        return dat, lab

    def _reduce_bcast(self, arr):
        return self.comm.bcast(self.comm.reduce(arr))


if __name__=="__main__":

    train_imgs = PngDset(start=2000, stop=9000)
    train_imgs_validate = PngDset(start=2000, stop=3000)
    test_imgs = PngDset(start=1000, stop=2000)

    train_tens = DataLoader(train_imgs, batch_size=16, shuffle=True)
    train_tens_validate = DataLoader(train_imgs_validate, batch_size=16, shuffle=True)
    test_tens = DataLoader(test_imgs, batch_size=16, shuffle=True)

    imgs, labs = next(iter(train_tens))
    print(imgs.shape, labs.shape)
