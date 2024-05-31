# Source code for resonet (Deep residual networks for crystallography trained on synthetic data)

Herein are Python tools for training [ResNets](https://en.wikipedia.org/wiki/Residual_neural_network) to analyze and interpret diffraction images.

Tutorial and installation info can be found [here](https://smb.slac.stanford.edu/~resonet/).

## Fork-Specific Changes

This repo was forked from the original, which can be found here: https://github.com/dermen/resonet. 

The changes made to this repo, along with the reasons behind the changes, are as follows:
- Added h5 support. The original repo could not take h5 as input, only cbf. Threading implementation was also changed to accommodate h5 processing.
- Changed non-pilatus downsample size and maxpool layer size to be the same as pilatus. This is a temporary fix. The way the original repo implemented non-pilatus downsample size and maxpool layer size did not work on some occasions.
- Added multi-gpu support. The original image_eater script was only acessing one cuda device. The new script distributes available cuda devices across threads.

Only three files have been changed from the base repo:
- scripts/image_eater.py
- utils/predict.py
- README.md
- stat-extract.py (new file; not present in base repo)

stat-extract.py extracts statistical information, and produces plots from logfiles of resonet results. For grid scan plotting, the shape of the array needs to be specified. Arrays do not need to be reshaped for producing line and scatter plots. The resolution estimates are first added to a list which stores the order of the res estimates along with their values. This is important because multi-threading can mixup the ordering of res estimates, so we need to reorder them after processing.

Testing results can be found here: https://dlsltd-my.sharepoint.com/:x:/g/personal/kai_mansfield_diamond_ac_uk/EQIGMZ8S1AtPoFRRVjCV1l4BRy7Bgu9yPiHCqsP6zJ8Rsg.
