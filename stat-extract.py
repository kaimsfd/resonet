import re
import statistics
import matplotlib.pyplot as plt
import numpy as np
from sklearn import preprocessing


with open('imgeater16.log', 'r') as file:
    iter_res = []
    for line in file:
        # Define regular expression pattern to extract res estimate"
        pattern = r"(\d+) Resolution estimate:\s+(\d+\.\d+)"
        
        # Search for the pattern in the current line
        match = re.search(pattern, line)
        
        # If a match is found, extract the values
        if match:
            iter = float(match.group(1))
            resolution_estimate = float(match.group(2))
            iter_res.append([iter, resolution_estimate])

iter_res = sorted(iter_res, key=lambda x: x[0])
iter_res = [inner_list[1] for inner_list in iter_res]
#iter_res = [x + 1 for x in range(300)]
# iter_res.append(statistics.median(iter_res))
# iter_res.append(statistics.median(iter_res))
iter_res = np.array(iter_res).reshape(22, 30)
iter_res[1::2, :] = iter_res[1::2, ::-1]

# Define colormap
cmap = plt.get_cmap('coolwarm')
cmap_flipped = cmap.reversed()

plt.imshow(iter_res, aspect='auto', cmap=cmap_flipped)
#plt.gca().invert_yaxis()
plt.colorbar().set_label('Resolution (Angstrom)')
plt.xlabel('Col Number')
plt.ylabel('Row Number')
plt.title('Grid Scan')
plt.show()

# # Plot the values with the colormap
# plt.figure(figsize=(8, 6))
# plt.scatter(range(len(raw)), raw)
# plt.gca().invert_yaxis()
# plt.title('Resolution per image')
# plt.xlabel('Image Number')
# plt.ylabel('Resolution (Angstrom)')
# plt.show()

# print('mean:', "%.2f" % statistics.mean(iter_res))
# print('median:', "%.2f" % statistics.median(iter_res))
# print('max:', "%.2f" % max(iter_res))
# print('min:', "%.2f" % min(iter_res))
# print('std:', "%.2f" % statistics.stdev(iter_res))
# print('number of vals:', iter_res.size)
