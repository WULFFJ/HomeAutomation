import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import time
from kld7 import KLD7
from sklearn.cluster import DBSCAN

# Initialize K-LD7 radar sensor
kld7 = KLD7('COM11')

# Function to get detections from K-LD7 and cluster them
def get_clustered_detections():
    data = kld7.read_PDAT()
    if not data:
        return []

    points = np.array([(target[0], target[1]) for target in data])
    print("Raw points:", points)  # Debug print

    # DBSCAN for clustering with a max distance (eps) parameter
    db = DBSCAN(eps=1.0, min_samples=1)
    db.fit(points)
    
    unique_labels = set(db.labels_)
    clusters = [points[db.labels_ == label] for label in unique_labels]
    centers = [np.mean(cluster, axis=0) for cluster in clusters]

    print("Cluster centers:", centers)  # Debug print

    return centers

# Load background image
img = mpimg.imread('radarbackground.png')

# Initialize plot and set figure size
fig, ax = plt.subplots(figsize=(10, 10))

# Display the background image
ax.imshow(img, extent=[-10, 10, 0, 10], aspect='auto', alpha=1, zorder=0)

# Set plot limits
ax.set_xlim(-10, 10)
ax.set_ylim(0, 10)
ax.grid(False)

# Set custom tick labels for x-axis only
ax.set_xticks(np.arange(-10, 11, 2))
ax.set_xticklabels(np.arange(-10, 11, 2))

# Initialize scatter plot with larger dots
sc = ax.scatter([], [], color='yellow', s=200, zorder=2)  # s=200 sets size, adjust as needed

# Function to update plot
def update_plot():
    detections = get_clustered_detections()
    if detections:
        x, y = zip(*detections)
        print("Plotting points:", list(zip(x, y)))  # Debug print
        sc.set_offsets(np.c_[x, y])
    plt.pause(0.05)

plt.show(block=False)

while True:
    update_plot()
    time.sleep(0.1)
