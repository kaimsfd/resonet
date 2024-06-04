# Source code for resonet (Deep residual networks for crystallography trained on synthetic data)

Herein are Python tools for training [ResNets](https://en.wikipedia.org/wiki/Residual_neural_network) to analyze and interpret diffraction images.

Tutorial and installation info can be found [here](https://smb.slac.stanford.edu/~resonet/).


## Fork-Specific Changes

This repo was forked from the original, which can be found here: https://github.com/dermen/resonet. 

The changes made to this repo, along with the reasons behind the changes, are as follows:
- Added h5 support. The original repo could not take h5 as input, only cbf. Threading implementation was also changed to accommodate h5 processing.
- Changed non-pilatus downsample size and maxpool layer size to be the same as pilatus. This is a temporary fix. The way the original repo implemented non-pilatus downsample size and maxpool layer size did not work on some occasions.
- Added multi-gpu support. The original image_eater script was only acessing one cuda device. The new script distributes available cuda devices across threads.

Only four files have been changed from the base repo:
- scripts/image_eater.py
- utils/predict.py
- README.md
- stat-extract.py (new file; not present in base repo)

stat-extract.py extracts statistical information, and produces plots from logfiles of resonet results. For grid scan plotting, the shape of the array needs to be specified. For non-grid-scan images, the following lines are not needed:
```
iter_res = np.array(iter_res).reshape(22, 30)
# flip the values of every other column; produce the snake-like ordering for grid scan
iter_res[1::2, :] = iter_res[1::2, ::-1]
```

The resolution estimates are first added to a list which stores the order of the res estimates along with their values. This is important because multi-threading can mixup the ordering of res estimates, so we need to reorder them after processing.


## Dials Env

Use --cmake option when building dials via bootstrap.py
