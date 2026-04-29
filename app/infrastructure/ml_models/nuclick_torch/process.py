from skimage.morphology import remove_small_objects, remove_small_holes, reconstruction, disk
import warnings
import numpy as np
import concurrent.futures

def _process_single_mask(i, thisMask, nucPoints_i, minSize, minHole, doReconstruction):
    thisMask = remove_small_objects(thisMask, min_size=minSize)
    thisMask = remove_small_holes(thisMask, area_threshold=minHole)
    if doReconstruction and nucPoints_i is not None:
        thisMarker = nucPoints_i[0, :, :] > 0
        try:
            thisMask = reconstruction(thisMarker, thisMask)
        except Exception as e:
            warnings.warn('Nuclei reconstruction error #' + str(i) + ': ' + str(e))
    return i, thisMask

#Returns masks
#preds(no.patchs, 128, 128), nucPoints(no.patchs, 1, 128, 128)
def post_processing(preds, thresh=0.33, minSize=10, minHole=30, doReconstruction=False, nucPoints=None):
    masks = preds > thresh
    out_masks = np.zeros_like(masks)
    
    # Process 2D slices independently in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for i in range(len(masks)):
            nucP = nucPoints[i] if nucPoints is not None else None
            futures.append(
                executor.submit(_process_single_mask, i, masks[i], nucP, minSize, minHole, doReconstruction)
            )
        for future in concurrent.futures.as_completed(futures):
            i, processed_mask = future.result()
            out_masks[i] = processed_mask

    return out_masks    #masks(no.patchs, 128, 128)


#Returns instanceMap
def gen_instance_map(masks, boundingBoxes, m, n):
    instanceMap = np.zeros((m, n), dtype=np.uint16) 
    for i in range(len(masks)):
        thisBB = boundingBoxes[i]
        thisMaskPos = np.argwhere(masks[i] > 0)
        thisMaskPos[:, 0] = thisMaskPos[:, 0] + thisBB[1]
        thisMaskPos[:, 1] = thisMaskPos[:, 1] + thisBB[0]
        instanceMap[thisMaskPos[:, 0], thisMaskPos[:, 1]] = i + 1
    return instanceMap